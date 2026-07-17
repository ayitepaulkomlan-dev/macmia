"""
cv_sections.py — Détection des blocs/sections d'un CV
========================================================
Combine deux signaux pour découper le texte en sections (Expérience,
Formation, Compétences, Langues, etc.) :

  1. SÉMANTIQUE : reconnaissance de titres de section connus (FR/EN),
     tolérante aux variantes et aux erreurs OCR courantes.
  2. GÉOMÉTRIQUE : changement de mise en forme (ligne nettement plus grande
     / plus grasse que la normale, gap vertical important avant la ligne)
     qui confirme ou révèle une frontière de section même quand le titre
     n'est pas dans la liste connue.

Le résultat ne dépend que des objets Line produits par cv_layout.py
(indépendant de tesseract, testable directement).
"""

from __future__ import annotations
import re
import unicodedata
import numpy as np
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════════════
# Référentiel de titres de section connus (FR + EN), formes canoniques
# ══════════════════════════════════════════════════════════════════════════

SECTION_TITLES = {
    "profil": [
        "profil", "a propos", "about me", "about", "summary", "resume profil",
        "presentation", "qui suis-je", "objectif professionnel", "objectif",
    ],
    "experience": [
        "experience", "experiences", "experience professionnelle",
        "experiences professionnelles", "parcours professionnel",
        "work experience", "professional experience", "employment history",
        "experience pro",
    ],
    "formation": [
        "formation", "formations", "education", "parcours academique",
        "diplomes", "diplome", "cursus", "academic background",
        "formation academique", "etudes",
    ],
    "competences": [
        "competences", "competence", "skills", "competences techniques",
        "competences cles", "savoir-faire", "technical skills",
        "compétences informatiques", "outils", "technologies",
        "hard skills", "soft skills",
    ],
    "langues": [
        "langues", "languages", "langues parlees", "competences linguistiques",
    ],
    "projets": [
        "projets", "projects", "projets academiques", "projets personnels",
        "realisations", "portfolio",
    ],
    "certifications": [
        "certifications", "certification", "certificats", "certificats obtenus",
    ],
    "centres_interet": [
        "centres d'interet", "centres dinteret", "loisirs", "interets",
        "hobbies", "interests", "activites extra-professionnelles",
    ],
    "contact": [
        "contact", "coordonnees", "informations personnelles",
        "personal information", "infos personnelles",
    ],
    "references": [
        "references", "reference",
    ],
    "publications": [
        "publications", "publication",
    ],
}

# Construit une regex tolérante par catégorie
def _normalize(s: str) -> str:
    """Minuscule, sans accents, espaces normalisés — pour matcher malgré l'OCR."""
    s = s.strip().lower()
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'[^a-z0-9\s\'-]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


_NORMALIZED_TITLES = {
    cat: [_normalize(t) for t in titles]
    for cat, titles in SECTION_TITLES.items()
}


def match_section_title(line_text: str, max_words: int = 5) -> str | None:
    """
    Tente de faire correspondre le texte d'une ligne à un titre de section
    connu. Retourne la catégorie ('experience', 'formation', ...) ou None.

    Une ligne candidate à un titre de section est typiquement courte
    (<= max_words mots) — ça évite de matcher un titre au milieu d'une
    phrase plus longue.
    """
    words = line_text.split()
    if len(words) == 0 or len(words) > max_words:
        return None

    norm = _normalize(line_text)
    if not norm:
        return None

    for cat, titles in _NORMALIZED_TITLES.items():
        for t in titles:
            # Match exact, ou la ligne COMMENCE par le titre suivi d'un séparateur
            # de fin (espace, ':', '-') — ex: "Compétences :", "Compétences techniques".
            # On exige que le titre couvre la majorité de la ligne pour éviter
            # qu'un mot du référentiel apparaissant dans une phrase de contenu
            # (ex: "Diplôme d'ingénieur - ENSAM") ne soit pris pour un titre.
            if norm == t:
                return cat
            if norm.startswith(t + ' ') or norm.startswith(t + ':') or norm.startswith(t + '-'):
                # Le titre doit représenter au moins la moitié de la longueur de la ligne
                if len(t) >= len(norm) * 0.5:
                    return cat
    return None


# ══════════════════════════════════════════════════════════════════════════
# Détection géométrique : une ligne "ressemble" à un titre de section
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class SectionBoundaryScore:
    is_title_like: bool
    reasons: list = field(default_factory=list)


def looks_like_section_title(
    line, prev_line, body_avg_height: float, body_gap_median: float,
    height_ratio_threshold: float = 1.15, gap_ratio_threshold: float = 1.8,
) -> SectionBoundaryScore:
    """
    Évalue si une ligne a les caractéristiques visuelles d'un titre de
    section, indépendamment de son contenu textuel :
      - police plus grande que la moyenne du corps de texte
      - tout en majuscules (heuristique forte en CV FR/EN)
      - gap vertical avant la ligne nettement supérieur à l'espacement
        normal entre lignes du document
    """
    reasons = []

    if body_avg_height > 0 and line.avg_height >= body_avg_height * height_ratio_threshold:
        reasons.append("police_plus_grande")

    text = line.text.strip()
    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) >= 0.85 and len(text) >= 3:
        reasons.append("tout_majuscule")

    if prev_line is not None and body_gap_median > 0:
        gap = line.top - prev_line.bottom
        if gap >= body_gap_median * gap_ratio_threshold:
            reasons.append("gap_vertical_important")

    # Lignes courtes (titres de section sont rarement de longues phrases)
    if len(text.split()) <= 5:
        reasons.append("ligne_courte")

    # Décision : un titre de section a une signature TYPOGRAPHIQUE propre
    # (police plus grande et/ou tout en majuscules), pas seulement une ligne
    # courte précédée d'un grand espace — ce dernier cas est très fréquent
    # en bas de page (avant le pied de page) ou simplement entre deux lignes
    # de contenu (ex: une date isolée) et ne doit PAS, à lui seul, déclencher
    # une nouvelle section. On exige donc au moins un signal typographique
    # explicite, en plus d'être une ligne courte.
    has_typographic_signal = "police_plus_grande" in reasons or "tout_majuscule" in reasons
    is_title_like = "ligne_courte" in reasons and has_typographic_signal

    return SectionBoundaryScore(is_title_like=is_title_like, reasons=reasons)


# ══════════════════════════════════════════════════════════════════════════
# Pipeline : lignes ordonnées → blocs de section
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class SectionBlock:
    category: str        # 'experience', 'formation', ... ou 'unknown' / 'header'
    title_raw: str        # texte exact du titre détecté (vide si aucun titre, ex: en-tête)
    lines: list = field(default_factory=list)
    confidence: str = "low"  # 'semantic' (titre reconnu), 'geometric' (visuel seul), 'low'

    @property
    def text(self) -> str:
        return '\n'.join(l.text for l in self.lines if l.text.strip())


def compute_body_stats(lines: list) -> tuple:
    """Calcule la hauteur moyenne des mots et le gap médian entre lignes
    consécutives d'une même colonne, pour servir de référence 'corps de texte'."""
    if len(lines) < 2:
        avg_h = lines[0].avg_height if lines else 10.0
        return avg_h, 10.0

    heights = [l.avg_height for l in lines if l.avg_height > 0]
    avg_h = float(np.median(heights)) if heights else 10.0

    gaps = []
    for i in range(1, len(lines)):
        if lines[i].column == lines[i - 1].column and lines[i].page == lines[i - 1].page:
            gap = lines[i].top - lines[i - 1].bottom
            if gap > 0:
                gaps.append(gap)
    gap_median = float(np.median(gaps)) if gaps else 10.0

    return avg_h, gap_median


def segment_into_blocks(lines: list) -> list:
    """
    Découpe une liste de Line (déjà en ordre de lecture, cf. cv_layout.py)
    en SectionBlock, en combinant reconnaissance sémantique de titres et
    détection géométrique.

    Stratégie :
      - Pour chaque ligne, on teste d'abord le match sémantique (titre connu).
      - Si pas de match sémantique mais que la ligne a les traits visuels
        d'un titre (looks_like_section_title), on ouvre quand même un
        nouveau bloc, catégorie 'unknown', avec le texte de la ligne comme
        titre_raw (utile à afficher au LLM tel quel).
      - Tout le texte avant le premier titre détecté forme un bloc 'header'
        (nom, contact, accroche — ce qui se trouve en haut du CV).
    """
    if not lines:
        return []

    body_avg_height, body_gap_median = compute_body_stats(lines)

    blocks: list = []
    current = SectionBlock(category="header", title_raw="", lines=[], confidence="low")

    # Tant qu'aucun titre de section RECONNU SÉMANTIQUEMENT n'a encore été vu,
    # on est dans l'en-tête du CV (nom, titre du poste, contact). Le nom est
    # très souvent affiché en gros caractères, ce qui ressemblerait à un
    # titre de section sur la seule base géométrique : on n'utilise donc le
    # signal géométrique seul ('unknown') qu'APRÈS avoir quitté l'en-tête,
    # pour ne pas fragmenter le bloc header à tort.
    seen_semantic_section = False

    prev_line = None
    for line in lines:
        if not line.text.strip():
            prev_line = line
            continue

        semantic_cat = match_section_title(line.text)
        geo_score = looks_like_section_title(line, prev_line, body_avg_height, body_gap_median)

        if semantic_cat is not None:
            is_new_section = True
        elif seen_semantic_section and geo_score.is_title_like:
            is_new_section = True
        else:
            is_new_section = False

        if is_new_section:
            # clôt le bloc courant s'il contient quelque chose
            if current.lines:
                blocks.append(current)
            cat = semantic_cat if semantic_cat else "unknown"
            conf = "semantic" if semantic_cat else "geometric"
            current = SectionBlock(category=cat, title_raw=line.text.strip(),
                                    lines=[], confidence=conf)
            current.lines.append(line)
            if semantic_cat is not None:
                seen_semantic_section = True
        else:
            current.lines.append(line)

        prev_line = line

    if current.lines:
        blocks.append(current)

    return blocks
