"""
core/cv_columns.py — Découpage d'une page de CV en régions avant OCR
====================================================================
Problème résolu :
    Sur un CV en deux colonnes, Tesseract regroupe fréquemment le contenu
    des deux colonnes dans un même `block_num`. La boîte englobante de ce
    bloc couvre alors toute la largeur utile, et l'OCR de ce crop lit
    HORIZONTALEMENT, en travers des colonnes :

        "EXPERIENCE            COMPETENCES"
        "Ingénieur R&D IA...   - Python"

    Le texte devient inexploitable : les titres de section sont noyés, et
    l'ordre de lecture est faux.

Principe de la correction :
    Une boîte de MOT n'est jamais à cheval sur deux colonnes — seules les
    boîtes de bloc le sont. On se sert donc des mots (et non des blocs)
    comme sonde géométrique pour trouver :
      1. la frontière basse de l'en-tête (bande pleine largeur du haut) ;
      2. le couloir vertical vide qui sépare les colonnes du corps.

    La page est ensuite découpée en régions (en-tête, colonne gauche,
    colonne droite — ou une seule région pleine largeur si le CV est sur
    une colonne), et chaque région est OCRisée séparément. L'ordre de
    lecture devient naturel et les colonnes ne se mélangent plus.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

log = logging.getLogger("macmia.cv.columns")


@dataclass
class Region:
    """Une zone rectangulaire de la page, à OCRiser indépendamment."""
    zone: str          # "header" | "col_left" | "col_right" | "full"
    x: int
    y: int
    w: int
    h: int

    @property
    def box(self) -> tuple:
        return (self.x, self.y, self.x + self.w, self.y + self.h)


def _word_boxes(df: pd.DataFrame, min_conf: float = 30) -> pd.DataFrame:
    """Mots exploitables : confiance suffisante et texte non vide."""
    if df is None or df.empty:
        return pd.DataFrame()
    clean = df[
        (df["conf"] > min_conf)
        & (df["text"].astype(str).str.strip() != "")
    ].copy()
    if clean.empty:
        return clean
    clean["right"] = clean["left"] + clean["width"]
    clean["bottom"] = clean["top"] + clean["height"]
    clean["center_x"] = clean["left"] + clean["width"] / 2
    return clean


# ══════════════════════════════════════════════════════════════════════════════
# Frontière de l'en-tête
# ══════════════════════════════════════════════════════════════════════════════

def detect_header_bottom(words: pd.DataFrame, page_height: int,
                         search_fraction: float = 0.45) -> int:
    """
    Cherche, dans le haut de la page, la plus large bande horizontale sans
    aucun mot : c'est la séparation entre l'en-tête (nom, contact, pleine
    largeur) et le corps en colonnes.

    Renvoie 0 si aucune séparation nette n'est trouvée.
    """
    if words.empty:
        return 0

    limit = page_height * search_fraction
    top_words = words[words["top"] < limit].sort_values("top")
    if len(top_words) < 2:
        return 0

    # Bandes vides entre lignes de mots successives
    best_gap, best_y = 0, 0
    cursor = int(top_words.iloc[0]["bottom"])
    for _, w in top_words.iterrows():
        gap = int(w["top"]) - cursor
        if gap > best_gap:
            best_gap, best_y = gap, cursor + gap // 2
        cursor = max(cursor, int(w["bottom"]))

    # Une séparation d'en-tête est un vide franc : au moins 1,5 % de la hauteur
    if best_gap < page_height * 0.015:
        return 0
    return best_y


# ══════════════════════════════════════════════════════════════════════════════
# Couloir entre colonnes
# ══════════════════════════════════════════════════════════════════════════════

def detect_column_boundary(words: pd.DataFrame, page_width: int,
                           y_min: int = 0,
                           min_corridor_ratio: float = 0.02,
                           central_band: tuple = (0.25, 0.75),
                           min_side_ratio: float = 0.15) -> float | None:
    """
    Détecte le couloir vertical vide séparant deux colonnes, à partir des
    boîtes de mots situées sous `y_min`.

    Garde-fous contre les faux positifs :
      - le couloir doit faire au moins `min_corridor_ratio` de la largeur ;
      - son centre doit tomber dans la bande centrale de la page ;
      - chaque côté doit porter au moins `min_side_ratio` des mots, sinon
        il s'agit d'une simple marge et non d'une seconde colonne.

    Renvoie l'abscisse de la frontière, ou None si le CV est sur une colonne.
    """
    body = words[words["top"] >= y_min]
    if len(body) < 12 or page_width <= 0:
        return None

    # Histogramme d'occupation horizontale, au mot
    bucket = max(1, page_width // 400)
    n_buckets = page_width // bucket + 1
    occ = np.zeros(n_buckets, dtype=int)
    for _, w in body.iterrows():
        s = int(w["left"]) // bucket
        e = max(s + 1, int(w["right"]) // bucket)
        occ[s:min(e, n_buckets)] += 1

    empty = occ == 0

    # Plus longue plage vide interne
    best = None  # (largeur_px, x_debut, x_fin)
    run_start, run_len = None, 0
    for i, is_empty in enumerate(empty):
        if is_empty:
            if run_start is None:
                run_start = i
            run_len += 1
            continue
        if run_start is not None:
            x0, x1 = run_start * bucket, (run_start + run_len) * bucket
            if x0 > 0 and x1 < page_width:
                width_px = x1 - x0
                if best is None or width_px > best[0]:
                    best = (width_px, x0, x1)
        run_start, run_len = None, 0

    if best is None:
        return None

    width_px, x0, x1 = best
    if width_px < page_width * min_corridor_ratio:
        return None

    boundary = (x0 + x1) / 2
    if not (page_width * central_band[0] <= boundary <= page_width * central_band[1]):
        return None

    left_count = int((body["center_x"] < x0).sum())
    right_count = int((body["center_x"] >= x1).sum())
    total = len(body)
    if left_count / total < min_side_ratio or right_count / total < min_side_ratio:
        return None

    log.info("Couloir de colonnes détecté à x=%d (largeur %dpx, %d mots à gauche / %d à droite)",
             boundary, width_px, left_count, right_count)
    return boundary


# ══════════════════════════════════════════════════════════════════════════════
# Découpage de la page en régions
# ══════════════════════════════════════════════════════════════════════════════

def segment_page(df_probe: pd.DataFrame, page_width: int, page_height: int,
                 is_first_page: bool = True) -> list:
    """
    À partir d'une sonde OCR de la page entière, renvoie la liste des régions
    à OCRiser séparément, dans l'ordre de lecture :
        en-tête → colonne gauche → colonne droite
    ou une unique région pleine largeur si le CV n'est pas en colonnes.
    """
    words = _word_boxes(df_probe)
    if words.empty:
        return [Region("full", 0, 0, page_width, page_height)]

    header_bottom = detect_header_bottom(words, page_height) if is_first_page else 0
    boundary = detect_column_boundary(words, page_width, y_min=header_bottom)

    if boundary is None:
        # CV sur une colonne : en-tête + corps, ou page entière
        if header_bottom > 0:
            return [
                Region("header", 0, 0, page_width, header_bottom),
                Region("full", 0, header_bottom, page_width, page_height - header_bottom),
            ]
        return [Region("full", 0, 0, page_width, page_height)]

    regions = []
    if header_bottom > 0:
        regions.append(Region("header", 0, 0, page_width, header_bottom))

    body_h = page_height - header_bottom
    split = int(boundary)
    regions.append(Region("col_left", 0, header_bottom, split, body_h))
    regions.append(Region("col_right", split, header_bottom, page_width - split, body_h))
    return regions
