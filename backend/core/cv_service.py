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
from .cv_sections import segment_into_blocks
from .rncp import RNCP_REFERENTIEL

log = logging.getLogger("macmia.cv")

ANNEE_COURANTE = datetime.now().year

# ── Configuration par variables d'environnement ───────────────────────────────
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
POPPLER_PATH  = os.getenv("POPPLER_PATH", "")
OLLAMA_URL    = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "llama3.1")
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

    try:
        import requests
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        status["ollama"] = True
        status["details"]["ollama"] = {"url": OLLAMA_URL, "models": models, "used": OLLAMA_MODEL}
    except Exception as e:
        status["details"]["ollama"] = f"indisponible ({e}) — extraction en mode dégradé sans LLM"

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

    annees = re.findall(r"\b(19[8-9]\d|20[0-2]\d)\b", text)
    annees_pro = [int(a) for a in annees if 2000 <= int(a) <= ANNEE_COURANTE]
    out["annees_experience"] = max(0, ANNEE_COURANTE - min(annees_pro)) if annees_pro else 0

    niveaux = re.findall(
        r"(?:Bac\s*[+\s]\s*\d|Master\s*\d?|Licence\s*\d?|Doctorat|PhD|Ingénieur|DUT|BTS|MBA|Bachelor)",
        text, re.IGNORECASE,
    )
    out["niveau_etudes"] = niveaux[0].strip() if niveaux else ""
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Étape 3 — LLM : extraction brute (mot pour mot)
# ══════════════════════════════════════════════════════════════════════════════

def _call_ollama(prompt: str, timeout: int = 180) -> dict:
    import requests

    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    r.raise_for_status()
    raw = r.json()["response"]
    clean = raw.strip().replace("```json", "").replace("```", "").strip()
    start, end = clean.find("{"), clean.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(clean[start:end])
    return json.loads(clean)


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

Retourne UNIQUEMENT ce JSON :
{{
  "nom": "Prénom NOM tel qu'écrit",
  "poste_actuel": "titre tel qu'écrit",
  "competences_brutes": ["compétence ou outil copié mot pour mot du CV"],
  "diplomes": [{{"titre": "titre exact", "etablissement": "établissement exact", "annee": 2020}}],
  "langues": [{{"langue": "Français", "niveau": "Natif"}}],
  "resume_profil": "2 phrases résumant le profil"
}}

CV (structuré par sections) :
{structured}
"""


def _extract_with_llm(structured_text: str) -> dict | None:
    try:
        result = _call_ollama(_PROMPT_EXTRACTION.format(structured=structured_text))
        log.info("LLM : %d compétences extraites", len(result.get("competences_brutes", [])))
        return result
    except Exception as e:
        log.warning("LLM indisponible (%s) — bascule sur l'extraction sans LLM", e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Étape 3b — Extraction de secours sans LLM
# ══════════════════════════════════════════════════════════════════════════════

_SECTION_COMP_RE = re.compile(
    r"^(COMP[EÉ]TENCES?(?:\s+(?:INFORMATIQUES?|TECHNIQUES?|ACQUISES?|DIGITALES?))?"
    r"|SKILLS?|OUTILS?|TECHNOLOGIES?)\s*:?\s*$", re.IGNORECASE)
_SECTION_STOP_RE = re.compile(
    r"^(EXP[EÉ]RIENCE|FORMATION|[EÉ]TUDES?|LANGUES?|PUBLICATIONS?|MANAGEMENT|LEADERSHIP"
    r"|B[EÉ]N[EÉ]VOLAT|LOISIRS?|PERMIS|COMP[EÉ]TENCES\s+EN\s+MANAGEMENT)", re.IGNORECASE)
_IGNORE_RE = re.compile(
    r"^(langue|niveaux|comprehension|compréhension|expression|orale|ecrite|écrite|continu|interaction"
    r"|\d{2}/\d{2}/\d{4}|[A-C][12]\b|(ANGLAIS|ALLEMAND|ESPAGNOL)\s+[A-C][12]"
    r"|Domaine.{0,10}d.etudes|Dipl.me final|Th.{1,3}se.{0,5}m.moire|Site web)", re.IGNORECASE)
_DIPLOME_KEYWORDS = re.compile(
    r"(INGENIEUR|INGÉNIEUR|MASTER|BACHELOR|LICENCE|BACCALAUREAT|BACCALAURÉAT|DOCTORAT|PHD"
    r"|DUT|BTS|MBA|ECOLE|ÉCOLE|UNIVERSITÉ|UNIVERSITE|SUPERIEURE|SUPÉRIEURE|NATIONALE|INSTITUT)",
    re.IGNORECASE)


def _extract_without_llm(cv_text_plat: str) -> dict:
    """Repli déterministe : parsing du texte plat quand Ollama est absent."""
    result = {"nom": "", "poste_actuel": "", "competences_brutes": [],
              "diplomes": [], "langues": [], "resume_profil": ""}

    for line in cv_text_plat.split("\n"):
        line = line.strip()
        if line and len(line) < 60 and not any(c in line for c in ["@", "http", "Tel", "|", "/"]):
            result["nom"] = line
            break

    m = re.search(r"(?:MES INFORMATIONS|PROFIL)[^\n]*\n([^\n]{10,150})", cv_text_plat, re.IGNORECASE)
    if m:
        result["poste_actuel"] = m.group(1).strip()

    # Fusion des lignes de continuation dans la section compétences
    merged, buf, in_comp_pre = [], "", False
    for line in cv_text_plat.split("\n"):
        s = line.strip()
        if _SECTION_COMP_RE.match(s):
            if buf: merged.append(buf); buf = ""
            in_comp_pre = True; merged.append(s); continue
        if in_comp_pre and _SECTION_STOP_RE.match(s):
            if buf: merged.append(buf); buf = ""
            in_comp_pre = False; merged.append(s); continue
        if not in_comp_pre:
            if buf: merged.append(buf); buf = ""
            merged.append(s); continue
        is_cont = (buf and not re.search(r"[.;)!?]\s*$", buf)
                   and not re.match(r"^[+\-*•.▪▸►]", s) and s)
        if is_cont:
            sep = "" if buf.endswith("|") or s.startswith("|") else " "
            buf = buf.rstrip() + sep + s
        else:
            if buf: merged.append(buf)
            buf = s
    if buf: merged.append(buf)

    raw_comps, in_comp = [], False
    for s in merged:
        if not s: continue
        if _SECTION_COMP_RE.match(s): in_comp = True; continue
        if in_comp and _SECTION_STOP_RE.match(s): in_comp = False; continue
        if not in_comp or _IGNORE_RE.match(s): continue
        clean = re.sub(r"^[+\-*•.▪▸►\u25ba\u25cf\uf0b7\u2022]\s*", "", s).strip()
        if len(clean) < 3 or len(clean) > 400: continue
        if "|" in clean:
            raw_comps += [p.strip().rstrip(";,.") for p in clean.split("|") if len(p.strip()) > 2]
        else:
            raw_comps.append(clean)

    seen = set()
    for c in raw_comps:
        key = c.lower().strip().rstrip(";,.")
        if key and key not in seen and len(key) > 3:
            seen.add(key)
            result["competences_brutes"].append(c.strip())

    diplome_re = re.compile(r"(\d{2}/\d{2}/\d{4})\s*-\s*\d{2}/\d{2}/\d{4}[^\n]*\n([^\n]{5,120})")
    seen_titres = set()
    for m in diplome_re.finditer(cv_text_plat):
        titre = m.group(2).strip()
        if not _DIPLOME_KEYWORDS.search(titre) or titre.lower() in seen_titres:
            continue
        seen_titres.add(titre.lower())
        annee = re.search(r"\b(\d{4})\b", m.group(1))
        etabl = ""
        for l in cv_text_plat[m.end():].split("\n")[:2]:
            l = l.strip()
            if l and not re.match(r"\d{2}/", l) and len(l) < 100 and not _DIPLOME_KEYWORDS.search(l):
                etabl = l
                break
        result["diplomes"].append({
            "titre": titre, "etablissement": etabl,
            "annee": int(annee.group(1)) if annee else 0,
        })

    if re.search(r"maternelle.{0,20}FRENCH", cv_text_plat, re.IGNORECASE):
        result["langues"].append({"langue": "Français", "niveau": "Natif"})
    lang_re = re.compile(r"^(ANGLAIS|ALLEMAND|ESPAGNOL|ARABE|ENGLISH|GERMAN|ARABIC)\s+([A-C][12])",
                         re.IGNORECASE | re.MULTILINE)
    seen_langs = set()
    for m in lang_re.finditer(cv_text_plat):
        lang = m.group(1).capitalize()
        if lang.lower() not in seen_langs:
            seen_langs.add(lang.lower())
            result["langues"].append({"langue": lang, "niveau": m.group(2).upper()})

    log.info("Sans LLM : %d compétences, %d diplômes, %d langues",
             len(result["competences_brutes"]), len(result["diplomes"]), len(result["langues"]))
    return result


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

    # 3. Regex (contact, niveau, expérience)
    regex_data = _extract_with_regex(cv_text_plat)

    # 4. LLM ou repli
    llm_data, source = None, "regex"
    if use_llm:
        llm_data = _extract_with_llm(structured_text)
        if llm_data:
            source = "llm"
    if llm_data is None:
        llm_data = _extract_without_llm(cv_text_plat)

    # 5. Mapping RNCP
    competences_brutes = llm_data.get("competences_brutes", []) or []
    competences_rncp = map_to_rncp(competences_brutes)

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
        "nom": llm_data.get("nom", ""),
        "poste_actuel": llm_data.get("poste_actuel", ""),
        "email": regex_data.get("email", ""),
        "telephone": regex_data.get("telephone", ""),
        "linkedin": regex_data.get("linkedin", ""),
        "github": regex_data.get("github", ""),
        "localisation": regex_data.get("localisation", ""),
        "niveau_etudes": regex_data.get("niveau_etudes", ""),
        "annees_experience": regex_data.get("annees_experience", 0),
        "resume_profil": llm_data.get("resume_profil", ""),
        "competences_brutes": competences_brutes,
        "competences_rncp": competences_rncp,
        "blocs_rncp": blocs_rncp,
        "diplomes": llm_data.get("diplomes", []) or [],
        "langues": llm_data.get("langues", []) or [],
        "meta": {
            "pages": len(images),
            "blocs_ocr": len(blocks),
            "sections": [
                {"categorie": s.category, "titre": s.title_raw, "confiance": s.confidence}
                for s in sections
            ],
            "caracteres": len(cv_text_plat),
        },
        "texte_brut": cv_text_plat,
    }
