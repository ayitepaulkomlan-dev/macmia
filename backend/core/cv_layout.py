"""
cv_layout.py — Segmentation du CV en zones visuelles + OCR par zone
====================================================================
Approche correcte :
  1. Tesseract produit un DataFrame avec block_num, par_num, line_num,
     et les coordonnées de chaque mot. On s'en sert pour reconstruire
     les BLOCS visuels (bounding box du block_num), pas les mots isolés.
  2. On classe chaque bloc dans une zone sémantique :
       - "header"   : zone du haut (nom, contact)
       - "col_left" : colonne gauche (ex : Expérience)
       - "col_right": colonne droite (ex : Compétences)
       - "full"     : pleine largeur dans le corps (ex : section unique)
  3. On extrait le texte de chaque bloc soit depuis le DataFrame déjà
     disponible (reconstruction depuis les mots du bloc), soit via un
     crop de l'image originale passé à image_to_string (meilleure qualité
     quand l'image est disponible).

Ne nécessite que pytesseract + Pillow (pas de detectron2, pas de torch).
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════
# Structures
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Block:
    """
    Un bloc visuel : rectangle continu de texte détecté par Tesseract
    (correspond à un block_num unique dans image_to_data).
    """
    block_num: int
    x: int          # bord gauche du bloc
    y: int          # bord haut du bloc
    w: int          # largeur du bloc
    h: int          # hauteur du bloc
    text: str       # texte reconstitué depuis les mots du bloc
    zone: str = ""  # "header" | "col_left" | "col_right" | "full"
    page: int = 1

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def center_x(self) -> float:
        return self.x + self.w / 2

    @property
    def center_y(self) -> float:
        return self.y + self.h / 2

    # Compatibilite avec cv_sections.py (qui attendait des objets Line)

    @property
    def top(self) -> int:
        return self.y

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def left(self) -> int:
        return self.x

    @property
    def avg_height(self) -> float:
        return float(self.h)

    @property
    def column(self) -> int:
        return 1 if self.zone == "col_right" else 0


# ══════════════════════════════════════════════════════════════════════════
# Étape 1 — DataFrame Tesseract → liste de blocs visuels
# ══════════════════════════════════════════════════════════════════════════

def dataframe_to_blocks(df: pd.DataFrame, page: int = 1,
                        min_conf: float = 0) -> list:
    """
    Regroupe les mots du DataFrame (issu de pytesseract.image_to_data)
    par block_num. Chaque groupe forme un bloc visuel dont on calcule
    la bounding box englobante et dont on reconstitue le texte ligne
    par ligne (en respectant l'ordre line_num > word_num).

    Un block_num correspond à une zone rectangulaire continue que
    Tesseract a identifiée comme appartenant ensemble (même colonne,
    même paragraphe, etc.) — c'est ça le "zoning" que tu voulais.
    """
    # Filtre : confiance positive et texte non vide
    clean = df[
        (df['conf'] > min_conf) &
        (df['text'].astype(str).str.strip() != '')
    ].copy()

    if clean.empty:
        return []

    blocks = []
    for block_num, grp in clean.groupby('block_num'):
        if block_num == 0:
            continue  # Tesseract utilise block_num=0 pour les métadonnées

        # Bounding box englobante du bloc
        x = int(grp['left'].min())
        y = int(grp['top'].min())
        right  = int((grp['left'] + grp['width']).max())
        bottom = int((grp['top'] + grp['height']).max())
        w = right - x
        h = bottom - y

        # Reconstruction du texte : on trie par (par_num, line_num, word_num)
        # pour respecter l'ordre de lecture dans le bloc
        sort_cols = []
        for col in ['par_num', 'line_num', 'word_num']:
            if col in grp.columns:
                sort_cols.append(col)
        if sort_cols:
            grp = grp.sort_values(sort_cols)

        # Reconstruction ligne par ligne (on insère un \n entre lignes)
        lines_text = []
        cur_line_key = None
        cur_line_words = []

        for _, row in grp.iterrows():
            line_key = (
                int(row.get('par_num', 0)),
                int(row.get('line_num', 0))
            )
            word = str(row['text']).strip()
            if not word:
                continue
            if line_key != cur_line_key:
                if cur_line_words:
                    lines_text.append(' '.join(cur_line_words))
                cur_line_words = [word]
                cur_line_key = line_key
            else:
                cur_line_words.append(word)

        if cur_line_words:
            lines_text.append(' '.join(cur_line_words))

        text = '\n'.join(lines_text).strip()
        if not text:
            continue

        blocks.append(Block(
            block_num=int(block_num),
            x=x, y=y, w=w, h=h,
            text=text,
            page=page,
        ))

    # Tri par position verticale puis horizontale pour ordre de traitement cohérent
    blocks.sort(key=lambda b: (b.y, b.x))
    return blocks


# ══════════════════════════════════════════════════════════════════════════
# Étape 2 — OCR amélioré par crop d'image (optionnel mais recommandé)
# ══════════════════════════════════════════════════════════════════════════

def ocr_block_from_image(image, block: Block,
                          padding: int = 8,
                          lang: str = 'fra+eng') -> str:
    """
    Extrait le texte d'un bloc en faisant un crop de l'image originale
    autour de la bounding box du bloc, puis en passant ce crop à
    image_to_string (mode paragraphe). Plus précis que la reconstruction
    mot-par-mot depuis le DataFrame, surtout pour les blocs denses.

    image   : objet PIL.Image de la page
    block   : bloc dont on veut le texte
    padding : pixels supplémentaires autour du crop (évite de couper des
              caractères en bord de bloc)
    """
    import pytesseract

    img_w, img_h = image.size
    left   = max(0, block.x - padding)
    top    = max(0, block.y - padding)
    right  = min(img_w, block.right + padding)
    bottom = min(img_h, block.bottom + padding)

    crop = image.crop((left, top, right, bottom))
    text = pytesseract.image_to_string(
        crop, lang=lang,
        config='--psm 6'  # psm 6 = bloc de texte uniforme
    )
    return text.strip()


# ══════════════════════════════════════════════════════════════════════════
# Étape 3 — Classification des blocs en zones sémantiques
# ══════════════════════════════════════════════════════════════════════════

def classify_blocks_into_zones(blocks: list, page_width: int,
                                header_fraction: float = 0.22,
                                is_first_page: bool = True) -> list:
    """
    Attribue une zone sémantique à chaque bloc :
      - "header"    : bloc dans la zone haute de la page (en-tête)
      - "col_left"  : bloc dans la moitié gauche du corps
      - "col_right" : bloc dans la moitié droite du corps
      - "full"      : bloc qui couvre toute la largeur (pleine largeur)

    La détection de la frontière en-tête/corps s'appuie sur le plus grand
    gap vertical dans le tiers supérieur, validé par la présence de blocs
    des deux côtés ensuite (signe de 2 colonnes).

    La frontière gauche/droite est calculée comme le milieu du couloir
    vide horizontal détecté dans le corps.
    """
    if not blocks:
        return blocks

    # --- Limite basse de l'en-tête ---
    page_height_est = max(b.bottom for b in blocks)
    search_limit = page_height_est * 0.50  # cherche dans la moitié supérieure

    # Calcul des gaps entre blocs consécutifs (triés par y)
    sorted_b = sorted(blocks, key=lambda b: b.y)
    header_bottom = 0

    gaps = []
    for i in range(1, len(sorted_b)):
        prev = sorted_b[i - 1]
        cur  = sorted_b[i]
        if cur.y > search_limit:
            break
        gap = cur.y - prev.bottom
        if gap > 0:
            gaps.append((gap, prev.bottom, i))

    if gaps and is_first_page:
        # Plus grand gap dans la zone de recherche
        best_gap, hb_candidate, first_body_idx = max(gaps, key=lambda x: x[0])

        # Validation : des blocs des deux côtés après ce gap ?
        body_sample = sorted_b[first_body_idx:first_body_idx + 4]
        mid = page_width / 2
        left_c  = sum(1 for b in body_sample if b.center_x < mid)
        right_c = sum(1 for b in body_sample if b.center_x >= mid)
        total = left_c + right_c
        if total > 0 and left_c / total >= 0.2 and right_c / total >= 0.2:
            header_bottom = hb_candidate

    # --- Couloir entre colonnes dans le corps ---
    body_blocks = [b for b in blocks if b.y >= header_bottom]
    col_boundary = page_width / 2  # fallback : milieu de la page

    if body_blocks and page_width > 0:
        # Histogramme d'occupation horizontale sur les blocs du corps
        bucket = max(1, page_width // 200)
        n_buckets = page_width // bucket + 1
        occ = np.zeros(n_buckets)
        for b in body_blocks:
            s = b.x // bucket
            e = max(s + 1, b.right // bucket)
            occ[s:min(e, n_buckets)] += 1

        is_empty = occ == 0
        # Cherche le plus grand couloir vide interne
        best_run = (0, 0, 0)  # (length, start_px, end_px)
        cs, cl = None, 0
        for i, empty in enumerate(is_empty):
            if empty:
                if cs is None:
                    cs = i
                cl += 1
            else:
                if cs is not None:
                    s_px = cs * bucket
                    e_px = (cs + cl) * bucket
                    if 0 < s_px and e_px < page_width and cl > best_run[0]:
                        # Vérifie que du contenu existe des deux côtés
                        lc = sum(1 for b in body_blocks if b.center_x < s_px)
                        rc = sum(1 for b in body_blocks if b.center_x >= e_px)
                        tot = len(body_blocks)
                        if tot > 0 and lc/tot >= 0.15 and rc/tot >= 0.15:
                            best_run = (cl, s_px, e_px)
                cs, cl = None, 0

        if best_run[0] > 0:
            _, gap_left, gap_right = best_run
            col_boundary = (gap_left + gap_right) / 2

    # --- Attribution des zones ---
    full_width_threshold = page_width * 0.70  # un bloc > 70% de la page = pleine largeur

    for b in blocks:
        if header_bottom > 0 and b.bottom <= header_bottom:
            b.zone = "header"
        elif b.w >= full_width_threshold:
            b.zone = "full"
        elif b.center_x < col_boundary:
            b.zone = "col_left"
        else:
            b.zone = "col_right"

    return blocks


# ══════════════════════════════════════════════════════════════════════════
# Étape 4 — Pipeline complet : DataFrame (+ image optionnelle) → blocs zonés
# ══════════════════════════════════════════════════════════════════════════

def process_page(df: pd.DataFrame, page_width: int, page_num: int,
                 image=None, min_conf: float = 0,
                 use_image_crop: bool = True) -> list:
    """
    Pipeline complet : DataFrame Tesseract d'une page → liste de Block
    zonés et ordonnés.

    Si `image` (PIL.Image) est fourni et `use_image_crop=True`, chaque
    bloc est ré-OCRisé par crop d'image pour un texte de meilleure qualité.
    Sinon, le texte est reconstruit depuis les mots du DataFrame.

    Ordre de sortie :
      blocs "header"    (haut → bas)
      blocs "col_left"  (haut → bas)
      blocs "col_right" (haut → bas)
      blocs "full"      (haut → bas, dans le corps)
    """
    blocks = dataframe_to_blocks(df, page=page_num, min_conf=min_conf)
    if not blocks:
        return []

    blocks = classify_blocks_into_zones(blocks, page_width, is_first_page=(page_num == 1))

    # OCR par crop si image disponible
    if image is not None and use_image_crop:
        for b in blocks:
            better_text = ocr_block_from_image(image, b)
            if better_text:
                b.text = better_text

    # Rapport de debug
    zone_counts = {}
    for b in blocks:
        zone_counts[b.zone] = zone_counts.get(b.zone, 0) + 1
    print(f"      Blocs détectés : {zone_counts}")

    # Ordre de lecture : header → col_left → col_right → full
    zone_order = {"header": 0, "col_left": 1, "col_right": 2, "full": 3}
    blocks.sort(key=lambda b: (zone_order.get(b.zone, 9), b.y))

    return blocks


# ══════════════════════════════════════════════════════════════════════════
# Utilitaires de sortie
# ══════════════════════════════════════════════════════════════════════════

def blocks_to_text(blocks: list) -> str:
    """
    Concatène les blocs dans l'ordre de lecture en texte plat.
    Chaque bloc est séparé par une ligne vide pour préserver la structure.
    """
    parts = []
    for b in blocks:
        t = b.text.strip()
        if t:
            parts.append(t)
    return '\n\n'.join(parts)


def blocks_to_structured(blocks: list) -> str:
    """
    Produit un texte structuré avec des marqueurs de zone,
    pour alimenter le LLM avec le contexte de provenance de chaque bloc.
    Format :
      ### ZONE : col_left | bloc 1
      texte...
      ### ZONE : col_right | bloc 1
      texte...
    """
    zone_labels = {
        "header":    "EN-TÊTE",
        "col_left":  "COLONNE GAUCHE",
        "col_right": "COLONNE DROITE",
        "full":      "PLEINE LARGEUR",
    }
    parts = []
    zone_counters: dict = {}
    for b in blocks:
        label = zone_labels.get(b.zone, b.zone.upper())
        n = zone_counters.get(b.zone, 0) + 1
        zone_counters[b.zone] = n
        parts.append(f"### {label} — bloc {n} (page {b.page})\n{b.text}")
    return '\n\n'.join(parts)