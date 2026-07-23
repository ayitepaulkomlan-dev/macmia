"""
core/cv_service.py — Service d'extraction CV (OCR zoné + sections + RNCP)
=========================================================================
Refactor serveur du pipeline `cv_extractor.py` :
  - pas de tkinter, pas de CLI, pas de chemins Windows en dur
  - entrée : bytes du PDF  →  sortie : dict JSON-sérialisable
  - chemins Tesseract/Poppler/Ollama configurables par variables d'env

Pipeline :
  1. PDF → images (pdf2image, 300 DPI)
  2. OCR image_to_data → blocs visuels zonés (cv_layout)
  3. Découpage en sections sémantiques (cv_sections)
  4. Regex sur le texte plat (email, tél, LinkedIn, niveau, expérience)
  5. LLM (Ollama) → compétences brutes, mot pour mot — fallback regex si absent
  6. Mapping sur les blocs RNCP par mots-clés (zéro hallucination)
"""

from __future__ import annotations

import os
import re
import json
import logging
from datetime import datetime
from pathlib import Path

from .cv_columns import segment_page
from .cv_layout import blocks_to_text, dataframe_to_blocks, ocr_block_from_image
from .cv_lines import blocks_to_lines
from .llm import LLM_MODEL, check_llm, generate_json
from .cv_parse import (
    fusionne_diplomes,
    fusionne_langues,
    fusionne_listes,
    parse_competences,
    parse_diplomes,
    parse_langues,
)
from .cv_sections import segment_into_blocks
from .rncp import RNCP_REFERENTIEL

log = logging.getLogger("macmia.cv")

ANNEE_COURANTE = datetime.now().year

# ── Configuration par variables d'environnement ───────────────────────────────
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
POPPLER_PATH  = os.getenv("POPPLER_PATH", "")
# Les réglages du modèle de langue vivent dans core/llm.py
OCR_LANG      = os.getenv("OCR_LANG", "fra+eng")
OCR_DPI       = int(os.getenv("OCR_DPI", "300"))

# Chemins de repli (Linux d'abord — le serveur ; puis Windows pour le dev local)
_TESSERACT_FALLBACKS = [
    # Linux (serveur)
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
    # Windows (poste de développement)
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
]
_POPPLER_FALLBACKS = [
    # Linux (serveur)
    "/usr/bin",
    "/usr/local/bin",
    # Windows (poste de développement)
    r"C:\poppler\Library\bin",
    r"C:\Program Files\poppler\Library\bin",
    os.path.expandvars(r"%USERPROFILE%\Downloads\Release-26.02.0-0\poppler-26.02.0\Library\bin"),
]


class CVExtractionError(Exception):
    """Erreur métier remontée à l'API (message affichable à l'utilisateur)."""


# ══════════════════════════════════════════════════════════════════════════════
# Dépendances système
# ══════════════════════════════════════════════════════════════════════════════

def _install_hint(tool: str) -> str:
    """Consigne d'installation adaptée au système hôte."""
    if os.name == "nt":
        hints = {
            "tesseract": (
                "Tesseract OCR est introuvable. Installez-le depuis "
                "https://github.com/UB-Mannheim/tesseract/wiki (cochez le pack de langue "
                "français), ou indiquez son chemin dans backend/.env : "
                r"TESSERACT_CMD=C:\chemin\vers\tesseract.exe"
            ),
            "poppler": (
                "Poppler est introuvable. Téléchargez-le depuis "
                "https://github.com/oschwartz10612/poppler-windows/releases, puis indiquez "
                "le dossier des binaires dans backend/.env : "
                r"POPPLER_PATH=C:\chemin\vers\poppler\Library\bin"
            ),
        }
    else:
        hints = {
            "tesseract": (
                "Tesseract OCR est introuvable sur le serveur. "
                "Installez-le (apt install tesseract-ocr tesseract-ocr-fra) "
                "ou définissez TESSERACT_CMD dans backend/.env."
            ),
            "poppler": (
                "Poppler est introuvable sur le serveur. "
                "Installez-le (apt install poppler-utils) ou définissez POPPLER_PATH "
                "dans backend/.env."
            ),
        }
    return hints[tool]


def _resolve_tesseract() -> str:
    import pytesseract

    candidates = [TESSERACT_CMD] if TESSERACT_CMD else []
    candidates += _TESSERACT_FALLBACKS
    for path in candidates:
        if path and Path(path).exists():
            pytesseract.pytesseract.tesseract_cmd = path
            log.info("Tesseract : %s", path)
            return path

    # Dernier recours : présent dans le PATH ?
    from shutil import which
    found = which("tesseract")
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        log.info("Tesseract (PATH) : %s", found)
        return found

    raise CVExtractionError(_install_hint("tesseract"))


def _resolve_poppler() -> str | None:
    candidates = [POPPLER_PATH] if POPPLER_PATH else []
    candidates += _POPPLER_FALLBACKS
    for path in candidates:
        if not path:
            continue
        base = Path(path)
        if (base / "pdftoppm").exists() or (base / "pdftoppm.exe").exists():
            log.info("Poppler : %s", path)
            return path

    from shutil import which
    if which("pdftoppm"):
        log.info("Poppler : PATH")
        return None  # pdf2image saura le trouver via le PATH

    raise CVExtractionError(_install_hint("poppler"))


def check_dependencies() -> dict:
    """Diagnostic des dépendances — exposé par /api/cv/health."""
    status = {"tesseract": False, "poppler": False, "ollama": False, "details": {}}

    try:
        path = _resolve_tesseract()
        import pytesseract
        status["tesseract"] = True
        status["details"]["tesseract"] = {
            "path": path,
            "version": str(pytesseract.get_tesseract_version()),
            "langs": pytesseract.get_languages(),
        }
    except Exception as e:
        status["details"]["tesseract"] = str(e)

    try:
        path = _resolve_poppler()
        status["poppler"] = True
        status["details"]["poppler"] = path or "PATH"
    except Exception as e:
        status["details"]["poppler"] = str(e)

    etat_llm = check_llm()
    status["ollama"] = etat_llm["disponible"]
    status["details"]["ollama"] = etat_llm

    return status


# ══════════════════════════════════════════════════════════════════════════════
# Étape 1 — PDF → blocs zonés → sections
# ══════════════════════════════════════════════════════════════════════════════

def _pdf_to_images(pdf_bytes: bytes):
    from pdf2image import convert_from_bytes

    poppler = _resolve_poppler()
    kwargs = {"dpi": OCR_DPI}
    if poppler:
        kwargs["poppler_path"] = poppler
    try:
        images = convert_from_bytes(pdf_bytes, **kwargs)
    except Exception as e:
        raise CVExtractionError(f"Impossible de lire le PDF : {e}") from e

    if not images:
        raise CVExtractionError("Le PDF ne contient aucune page lisible.")
    log.info("PDF converti : %d page(s) à %d DPI", len(images), OCR_DPI)
    return images


def _ocr_zoned_blocks(images: list) -> list:
    """
    OCR page par page, région par région.

    Une sonde OCR sert d'abord à localiser l'en-tête et le couloir entre
    colonnes ; la page est découpée en conséquence, puis chaque région est
    OCRisée séparément. C'est ce qui empêche l'OCR de lire en travers des
    colonnes et de coller « EXPERIENCE » à « COMPETENCES » sur une même ligne.
    """
    import pytesseract

    all_blocks = []
    for i, img in enumerate(images, 1):
        # 1. Sonde géométrique sur la page entière (mots + coordonnées)
        df_probe = pytesseract.image_to_data(
            img, lang=OCR_LANG, config="--psm 1",
            output_type=pytesseract.Output.DATAFRAME,
        )

        # 2. Découpage en régions de lecture
        regions = segment_page(df_probe, img.width, img.height, is_first_page=(i == 1))
        log.info("Page %d : %d région(s) — %s", i, len(regions), [r.zone for r in regions])

        # 3. OCR de chaque région, indépendamment
        for region in regions:
            crop = img.crop(region.box)
            if crop.width < 20 or crop.height < 20:
                continue

            df = pytesseract.image_to_data(
                crop, lang=OCR_LANG, config="--psm 4",  # psm 4 : colonne de texte
                output_type=pytesseract.Output.DATAFRAME,
            )
            blocks = dataframe_to_blocks(df, page=i)

            for b in blocks:
                # Coordonnées ramenées dans le repère de la page
                b.x += region.x
                b.y += region.y
                b.zone = region.zone
                # Ré-OCR par crop, dans le repère de la page cette fois
                better = ocr_block_from_image(img, b, lang=OCR_LANG)
                if better:
                    b.text = better

            all_blocks.extend(blocks)

    # Ordre de lecture : en-tête → colonne gauche → colonne droite → pleine largeur
    zone_order = {"header": 0, "col_left": 1, "col_right": 2, "full": 3}
    all_blocks.sort(key=lambda b: (b.page, zone_order.get(b.zone, 9), b.y, b.x))
    log.info("Total : %d blocs", len(all_blocks))
    return all_blocks


CATEGORY_LABELS = {
    "header": "EN-TÊTE (nom, contact, accroche)",
    "profil": "PROFIL",
    "experience": "EXPÉRIENCE PROFESSIONNELLE",
    "formation": "FORMATION",
    "competences": "COMPÉTENCES",
    "langues": "LANGUES",
    "projets": "PROJETS",
    "certifications": "CERTIFICATIONS",
    "centres_interet": "CENTRES D'INTÉRÊT",
    "contact": "CONTACT",
    "references": "RÉFÉRENCES",
    "publications": "PUBLICATIONS",
    "unknown": None,
}


def _section_text(sections: list, category: str) -> str:
    """Concatène le texte des sections d'une catégorie donnée."""
    return "\n".join(s.text for s in sections if s.category == category)


def _sections_to_prompt_text(sections: list, max_chars: int = 6000) -> str:
    """Sérialise les sections avec des marqueurs ### pour guider le LLM."""
    parts, used = [], 0
    for s in sections:
        label = CATEGORY_LABELS.get(s.category)
        header = label if label else (s.title_raw.upper() or "SECTION")
        chunk = f"### {header}\n{s.text}\n"
        if used + len(chunk) > max_chars and parts:
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# Étape 2 — Regex sur le texte plat
# ══════════════════════════════════════════════════════════════════════════════

def _extract_with_regex(text: str) -> dict:
    out = {}

    email = re.findall(r"[\w\.-]+@[\w\.-]+\.\w{2,4}", text)
    out["email"] = email[0] if email else ""

    # Indicatif optionnellement suivi d'un espace : "+33 6 12 34 56 78" comme "0612345678"
    tel = re.findall(
        r"(?:(?:\+|00)33[\s.\-]?|0)[1-9](?:[\s.\-]?\d{2}){4}|(?:\+|00)\d{1,3}[\s.\-]?\d{6,12}",
        text,
    )
    out["telephone"] = re.sub(r"\s+", " ", tel[0]).strip() if tel else ""

    linkedin = re.findall(r"linkedin\.com/in/[\w\-]+", text, re.IGNORECASE)
    out["linkedin"] = linkedin[0] if linkedin else ""

    github = re.findall(r"github\.com/[\w\-]+", text, re.IGNORECASE)
    out["github"] = github[0] if github else ""

    # [ \t] et non \s : \s engloberait le saut de ligne et avalerait la ligne suivante
    loc = re.findall(r"\b\d{5}\b[ \t,]+[A-ZÀ-Ÿ][A-Za-zÀ-ÿ' \-]{1,40}", text)
    out["localisation"] = loc[0].strip(" ,-") if loc else ""

    niveaux = re.findall(
        r"(?:Bac\s*[+\s]\s*\d|Master\s*\d?|Licence\s*\d?|Doctorat|PhD|Ingénieur|DUT|BTS|MBA|Bachelor)",
        text, re.IGNORECASE,
    )
    out["niveau_etudes"] = niveaux[0].strip() if niveaux else ""
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Expériences professionnelles et ancienneté
# ══════════════════════════════════════════════════════════════════════════════

_EN_COURS = re.compile(
    r"(aujourd\W?hui|présent|present|actuel|en cours|to date|current|now|ce jour)",
    re.IGNORECASE,
)

# Plages de dates : « 2019 - 2021 », « 01/2019 – 12/2021 », « Depuis 2021 », « 2021 — Aujourd'hui »
_YEAR_RANGE = re.compile(
    r"(?:depuis\s+)?"
    r"(?:\d{1,2}[/.]){0,2}(?P<debut>19[8-9]\d|20[0-4]\d)"
    r"(?:\s*(?:[-–—]|à|au|to)\s*"
    r"(?:(?:\d{1,2}[/.]){0,2}(?P<fin>19[8-9]\d|20[0-4]\d)|(?P<encours>[A-Za-zÀ-ÿ' ]{2,14})))?",
    re.IGNORECASE,
)


def _has_year_range(line: str):
    """Une ligne porte-t-elle une plage de dates ouvrant un poste ?"""
    m = _YEAR_RANGE.search(line)
    if not m:
        return None
    if m.group("fin") or "depuis" in line.lower():
        return m
    if m.group("encours") and _EN_COURS.search(m.group("encours")):
        return m
    return None


def _parse_experiences(section_text: str) -> list:
    """
    Relève les postes de la section Expérience à partir de leurs plages de dates.

    La mise en page usuelle d'un CV place l'intitulé AU-DESSUS de la ligne de
    dates, et l'employeur sur cette même ligne :

        Data Analyst
        Société Générale · 2021 — Aujourd'hui
        Analyse de données clients, dashboards Power BI.

    On repère donc les lignes de dates, puis on regarde en arrière pour
    l'intitulé et en avant pour la mission. Ce repli sert quand le modèle de
    langue est absent, et sert de garde-fou : les dates viennent du document,
    jamais d'une reformulation.
    """
    if not section_text.strip():
        return []

    lines = [l.strip() for l in section_text.split("\n") if l.strip()]
    date_idx = [i for i, l in enumerate(lines) if _has_year_range(l)]
    if not date_idx:
        return []

    experiences = []
    for k, i in enumerate(date_idx):
        m = _has_year_range(lines[i])
        debut = int(m.group("debut"))
        fin = int(m.group("fin")) if m.group("fin") else None
        en_cours = fin is None

        # Ce qui reste de la ligne une fois les dates ôtées. Les parenthèses
        # vidées de leur date sont retirées, mais « INSEE (stage) » garde la
        # sienne : on ne rogne que les séparateurs.
        reste = _YEAR_RANGE.sub("", lines[i])
        reste = re.sub(r"\(\s*\)", "", reste)
        reste = reste.strip(" -–—|,·•")

        # Intitulé : la ligne précédente, si elle n'est ni une autre ligne de
        # dates ni une phrase de description (celles-ci se terminent par un point).
        def title_like(idx):
            if idx < 0 or idx in date_idx:
                return ""
            l = lines[idx]
            return l if len(l) < 70 and not l.rstrip().endswith(".") else ""

        prev = title_like(i - 1)

        if reste and prev:
            # « Data Analyst » / « Société Générale · 2021 — 2024 »
            poste, entreprise = prev, reste
        elif not reste and prev:
            # « Consultant Data » / « Accenture » / « Depuis 2022 » :
            # la ligne de dates est seule, l'employeur est juste au-dessus.
            poste, entreprise = title_like(i - 2) or prev, prev if title_like(i - 2) else ""
        elif " — " in reste or " - " in reste or " | " in reste:
            parts = re.split(r"\s+[—\-|]\s+", reste, maxsplit=1)
            poste, entreprise = parts[0], (parts[1] if len(parts) > 1 else "")
        else:
            poste, entreprise = reste, ""

        # Mission : les lignes suivantes, en excluant l'intitulé du poste suivant
        next_date = date_idx[k + 1] if k + 1 < len(date_idx) else len(lines)
        desc_end = next_date - 1 if next_date < len(lines) else next_date
        description = " ".join(lines[i + 1:max(i + 1, desc_end)]).strip()

        experiences.append({
            "poste": poste.strip(),
            "entreprise": entreprise.strip(),
            "debut": debut,
            "fin": fin,
            "en_cours": en_cours,
            "description": description,
        })

    experiences.sort(key=lambda e: e["debut"], reverse=True)
    return experiences


def _normalize_experiences(raw) -> list:
    """
    Met en forme les expériences renvoyées par le modèle de langue.

    Le modèle est libre dans sa réponse : il peut omettre un champ, écrire
    l'année en texte, ou rendre une simple chaîne. On ne garde que les entrées
    dont l'année de début est exploitable — c'est elle qui fonde l'ancienneté,
    elle ne peut pas être approximative.
    """
    if not isinstance(raw, list):
        return []

    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue

        debut = item.get("debut")
        if isinstance(debut, str):
            m = re.search(r"(19[8-9]\d|20[0-4]\d)", debut)
            debut = int(m.group(1)) if m else None
        if not isinstance(debut, int) or not (1980 <= debut <= ANNEE_COURANTE):
            continue

        fin = item.get("fin")
        if isinstance(fin, str):
            m = re.search(r"(19[8-9]\d|20[0-4]\d)", fin)
            fin = int(m.group(1)) if m else None
        if not isinstance(fin, int) or not (1980 <= fin <= ANNEE_COURANTE + 1):
            fin = None

        out.append({
            "poste": str(item.get("poste") or item.get("titre") or "").strip(),
            "entreprise": str(item.get("entreprise") or "").strip(),
            "debut": debut,
            "fin": fin,
            "en_cours": fin is None,
            "description": str(item.get("description") or "").strip(),
        })

    out.sort(key=lambda e: e["debut"], reverse=True)
    return out


def _compute_experience_years(experiences: list, section_text: str) -> int:
    """
    Ancienneté professionnelle = année courante − première année de poste.

    L'année est cherchée dans la seule section Expérience. La chercher dans
    tout le document comptait l'année d'un diplôme ou d'une certification :
    une licence en 2017 et un premier poste en 2021 donnaient 9 ans au lieu
    de 4.
    """
    debuts = [e["debut"] for e in experiences if e.get("debut")]
    if not debuts and section_text.strip():
        debuts = [
            int(y) for y in re.findall(r"\b(19[8-9]\d|20[0-4]\d)\b", section_text)
            if 1980 <= int(y) <= ANNEE_COURANTE
        ]
    if not debuts:
        return 0
    return max(0, ANNEE_COURANTE - min(debuts))


# ══════════════════════════════════════════════════════════════════════════════
# Étape 3 — LLM : extraction brute (mot pour mot)
# ══════════════════════════════════════════════════════════════════════════════

_PROMPT_EXTRACTION = """Tu lis un CV. Le texte ci-dessous est organisé en sections, chacune précédée
d'un marqueur "### NOM_DE_SECTION". Utilise ces marqueurs pour comprendre le contexte
de chaque information (une compétence sous "### COMPÉTENCES" est plus fiable qu'un mot
similaire trouvé sous "### CENTRES D'INTÉRÊT").

Extrais EXACTEMENT ce qui est écrit, mot pour mot.

RÈGLE ABSOLUE : copie les compétences, outils et technologies tels qu'ils apparaissent
dans le CV. N'invente rien. Ne reformule pas. Les marqueurs "###" ne font pas partie
du contenu du CV, ce sont des repères de structure.

RÈGLE LANGUES : pour le niveau, utilise UNIQUEMENT "Natif", "C2", "C1", "B2", "B1", "A2", "A1".
Devant un tableau Europass à plusieurs colonnes, prends la compréhension écrite comme
niveau représentatif. N'écris jamais plusieurs niveaux pour une même langue.

RÈGLE EXPÉRIENCES : ne relève QUE les postes de la section EXPÉRIENCE PROFESSIONNELLE.
"debut" et "fin" sont des années à 4 chiffres. Pour un poste en cours, mets "fin": null.
N'y mets jamais un stage listé sous FORMATION ni une date de diplôme.

Retourne UNIQUEMENT ce JSON :
{{
  "nom": "Prénom NOM tel qu'écrit",
  "poste_actuel": "titre tel qu'écrit",
  "competences_brutes": ["compétence ou outil copié mot pour mot du CV"],
  "experiences": [
    {{"poste": "intitulé exact", "entreprise": "employeur exact", "debut": 2021, "fin": null,
      "description": "mission telle qu'écrite"}}
  ],
  "diplomes": [{{"titre": "titre exact", "etablissement": "établissement exact", "annee": 2020}}],
  "langues": [{{"langue": "Français", "niveau": "Natif"}}],
  "resume_profil": "2 phrases résumant le profil"
}}

CV (structuré par sections) :
{structured}
"""


def _extract_with_llm(structured_text: str) -> dict | None:
    """
    Relevé par le modèle de langue, en complément des règles.

    Un premier appel peut expirer simplement parce que le serveur chargeait le
    modèle en mémoire ; on retente alors une fois, le chargement étant fait.
    Un échec n'est jamais bloquant : le relevé par règles tient lieu de base.
    """
    import requests

    prompt = _PROMPT_EXTRACTION.format(structured=structured_text)
    for tentative in (1, 2):
        try:
            result = generate_json(prompt)
            log.info("LLM (%s) : %d compétences, %d diplômes",
                     LLM_MODEL,
                     len(result.get("competences_brutes") or []),
                     len(result.get("diplomes") or []))
            return result
        except requests.exceptions.Timeout as e:
            if tentative == 1:
                log.warning("LLM : délai dépassé, nouvelle tentative (modèle désormais chargé)")
                continue
            log.warning("LLM indisponible (%s) — relevé par règles seules", e)
        except Exception as e:
            log.warning("LLM indisponible (%s) — relevé par règles seules", e)
            break
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Étape 3b — Relevé par règles, à partir des sections détectées
# ══════════════════════════════════════════════════════════════════════════════

def _extract_par_regles(sections: list) -> dict:
    """
    Relevé déterministe, lu dans les sections isolées par la segmentation.

    C'est la source de vérité de l'extraction : aucun modèle n'intervient, donc
    aucune invention n'est possible. Ce relevé sert à la fois de secours quand
    le modèle de langue est indisponible, et de garde-fou quand il répond — les
    deux relevés étant ensuite fusionnés par union.
    """
    txt_comp = _section_text(sections, "competences")
    txt_form = _section_text(sections, "formation")
    txt_lang = _section_text(sections, "langues")
    txt_head = _section_text(sections, "header")
    txt_exp  = _section_text(sections, "experience")

    competences, comp_restes = parse_competences(txt_comp)
    diplomes, dipl_restes    = parse_diplomes(txt_form)
    langues, lang_restes     = parse_langues(txt_lang)

    # Nom et poste : les deux premières lignes utiles de l'en-tête
    nom, poste = "", ""
    for ligne in [l.strip() for l in txt_head.split("\n") if l.strip()]:
        if any(c in ligne for c in ("@", "http", "www.")) or re.search(r"\d{4}", ligne):
            continue
        if not nom and 2 <= len(ligne) <= 60:
            nom = ligne
        elif not poste and 3 <= len(ligne) <= 90:
            poste = ligne
            break

    log.info("Règles : %d compétences, %d diplômes, %d langues",
             len(competences), len(diplomes), len(langues))

    return {
        "nom": nom,
        "poste_actuel": poste,
        "competences_brutes": competences,
        "experiences": _parse_experiences(txt_exp),
        "diplomes": diplomes,
        "langues": langues,
        "resume_profil": "",
        "non_structure": {
            "competences": comp_restes,
            "formation": dipl_restes,
            "langues": lang_restes,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# Étape 4 — Mapping RNCP par mots-clés (zéro hallucination)
# ══════════════════════════════════════════════════════════════════════════════

def _compile_keyword_patterns() -> dict:
    """
    Pré-compile un motif par mot-clé, encadré de frontières alphanumériques.

    La recherche en sous-chaîne brute confond les termes : le mot-clé « api »
    de BC1 matche au milieu de « FastAPI », ce qui envoie une compétence de
    développement dans le bloc Collecte de données. Les gardes (?<![a-z0-9])
    et (?![a-z0-9]) l'évitent, tout en tolérant les mots-clés à ponctuation
    (« ci/cd », « industrie 4.0 ») que \\b gérerait mal.
    """
    compiled = {}
    for bloc_id, bloc in RNCP_REFERENTIEL.items():
        compiled[bloc_id] = [
            (kw, re.compile(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", re.IGNORECASE))
            for kw in bloc["keywords"]
        ]
    return compiled


_KEYWORD_PATTERNS = _compile_keyword_patterns()


def map_to_rncp(competences_brutes: list) -> dict:
    """
    Assigne chaque compétence au bloc RNCP dont les mots-clés matchent le mieux.
    Aucun LLM : aucune hallucination possible.

    Le score d'un bloc est la somme des longueurs des mots-clés reconnus, et
    non leur nombre : un terme long est plus discriminant qu'un terme court.
    « Machine Learning supervisé » pèse ainsi davantage que « ml », et un
    départage arbitraire entre deux blocs devient beaucoup moins probable.
    """
    result = {bloc_id: [] for bloc_id in RNCP_REFERENTIEL}

    for comp in competences_brutes:
        best_bloc, best_score = None, 0
        for bloc_id, patterns in _KEYWORD_PATTERNS.items():
            score = sum(len(kw) for kw, pat in patterns if pat.search(comp))
            if score > best_score:
                best_score, best_bloc = score, bloc_id
        result[best_bloc or "BC8_metiers_sectoriels"].append(comp)

    return result


def compute_rncp_coverage(competences_rncp: dict) -> dict:
    """
    Mesure la couverture du référentiel RNCP par le profil.

    Le score est la part des 8 blocs sur lesquels au moins une compétence a
    été relevée. C'est une mesure vérifiable, contrairement à une adéquation
    à un objectif métier, qui suppose un objectif — lequel n'existe pas encore
    à ce stade du parcours.

    Les blocs vides ne sont pas un jugement : ce sont les axes sur lesquels
    une formation apportera le plus.
    """
    couverts = [b for b, c in competences_rncp.items() if c]
    total = len(RNCP_REFERENTIEL)
    score = round(len(couverts) / total * 100) if total else 0

    forces = sorted(
        (
            {"id": b, "label": RNCP_REFERENTIEL[b]["label"], "nb": len(c)}
            for b, c in competences_rncp.items() if c
        ),
        key=lambda x: -x["nb"],
    )
    ecarts = [
        {"id": b, "label": RNCP_REFERENTIEL[b]["label"]}
        for b in RNCP_REFERENTIEL
        if not competences_rncp.get(b)
    ]

    return {
        "score": score,
        "blocs_couverts": len(couverts),
        "blocs_total": total,
        "forces": forces[:3],
        "ecarts": ecarts,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Pipeline complet
# ══════════════════════════════════════════════════════════════════════════════

def extract_cv(pdf_bytes: bytes, filename: str = "cv.pdf", use_llm: bool = True) -> dict:
    """
    Extrait un profil structuré depuis les bytes d'un CV PDF.
    Lève CVExtractionError si les dépendances système manquent ou si le PDF est illisible.
    """
    _resolve_tesseract()

    # 1. PDF → images → blocs zonés
    images = _pdf_to_images(pdf_bytes)
    blocks = _ocr_zoned_blocks(images)
    if not blocks:
        raise CVExtractionError(
            "Aucun texte détecté dans le PDF. "
            "S'il s'agit d'un scan de mauvaise qualité, essayez un export PDF natif."
        )

    cv_text_plat = blocks_to_text(blocks)

    # 2. Blocs → lignes → sections sémantiques
    #    L'étape par les lignes est indispensable : cv_sections rejette tout
    #    texte de plus de 5 mots comme titre, donc un Block multi-lignes ne
    #    ferait jamais reconnaître « COMPÉTENCES » ou « EXPÉRIENCE ».
    lines = blocks_to_lines(blocks)
    sections = segment_into_blocks(lines)
    structured_text = _sections_to_prompt_text(sections)

    # 3. Regex (contact, niveau)
    regex_data = _extract_with_regex(cv_text_plat)

    # 4. Relevé par règles — toujours effectué, il fait référence
    regles = _extract_par_regles(sections)

    # 5. Le modèle de langue complète, il ne remplace pas.
    #    La fusion se fait par union : une formation ou une compétence vue par
    #    un seul des deux relevés subsiste. C'est ce qui évite qu'une
    #    information disparaisse parce qu'un seul lecteur l'a manquée.
    llm_data = _extract_with_llm(structured_text) if use_llm else None
    source = "llm+regles" if llm_data else "regles"

    if llm_data:
        donnees = {
            "nom": llm_data.get("nom") or regles["nom"],
            "poste_actuel": llm_data.get("poste_actuel") or regles["poste_actuel"],
            "resume_profil": llm_data.get("resume_profil", ""),
            "competences_brutes": fusionne_listes(
                regles["competences_brutes"], llm_data.get("competences_brutes")),
            "diplomes": fusionne_diplomes(regles["diplomes"], llm_data.get("diplomes")),
            "langues": fusionne_langues(regles["langues"], llm_data.get("langues")),
            "experiences": llm_data.get("experiences"),
        }
    else:
        donnees = dict(regles)

    # 6. Expériences : le LLM les structure, la section les valide.
    #    Les dates viennent toujours du document, jamais d'une reformulation.
    exp_text = _section_text(sections, "experience")
    experiences = _normalize_experiences(donnees.get("experiences"))
    if not experiences:
        experiences = _parse_experiences(exp_text)
    annees_experience = _compute_experience_years(experiences, exp_text)

    # 7. Mapping RNCP + couverture
    competences_brutes = donnees.get("competences_brutes", []) or []
    competences_rncp = map_to_rncp(competences_brutes)
    couverture = compute_rncp_coverage(competences_rncp)

    # Blocs RNCP non vides, enrichis de leur libellé — prêts à afficher
    blocs_rncp = [
        {
            "id": bloc_id,
            "label": RNCP_REFERENTIEL[bloc_id]["label"],
            "competences": comps,
        }
        for bloc_id, comps in competences_rncp.items() if comps
    ]

    return {
        "source": source,                       # "llm" | "regex"
        "filename": filename,
        "nom": donnees.get("nom", ""),
        "poste_actuel": donnees.get("poste_actuel", ""),
        "email": regex_data.get("email", ""),
        "telephone": regex_data.get("telephone", ""),
        "linkedin": regex_data.get("linkedin", ""),
        "github": regex_data.get("github", ""),
        "localisation": regex_data.get("localisation", ""),
        "niveau_etudes": regex_data.get("niveau_etudes", ""),
        "annees_experience": annees_experience,
        "resume_profil": donnees.get("resume_profil", ""),
        "competences_brutes": competences_brutes,
        "competences_rncp": competences_rncp,
        "blocs_rncp": blocs_rncp,
        "couverture_rncp": couverture,
        "experiences": experiences,
        "diplomes": donnees.get("diplomes", []) or [],
        "langues": donnees.get("langues", []) or [],
        "meta": {
            "pages": len(images),
            "blocs_ocr": len(blocks),
            "sections": [
                {"categorie": s.category, "titre": s.title_raw, "confiance": s.confidence}
                for s in sections
            ],
            "caracteres": len(cv_text_plat),
            # Lignes lues dans une section mais qu'aucune règle n'a su structurer.
            # Elles sont remontées plutôt qu'écartées : rien ne doit disparaître
            # en silence, l'utilisateur doit pouvoir constater ce qui a été vu.
            "non_structure": {k: v for k, v in (regles.get("non_structure") or {}).items() if v},
        },
        "texte_brut": cv_text_plat,
    }
