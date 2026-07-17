"""
core/cv_lines.py — Pont entre cv_layout (Block) et cv_sections (Line)
=====================================================================
`cv_layout.dataframe_to_blocks` produit des Block : des rectangles de texte
MULTI-LIGNES ("COMPÉTENCES\\n- Python\\n- SQL...").

`cv_sections.match_section_title` attend au contraire une ligne unique : il
rejette tout texte de plus de 5 mots, pour éviter de prendre un mot du
référentiel apparaissant au milieu d'une phrase pour un titre de section.

Passer des Block directement à `segment_into_blocks` ne détecte donc jamais
aucun titre. Ce module fait la conversion : chaque Block est éclaté en Line,
avec une géométrie interpolée à partir de la boîte englobante du bloc.

L'interpolation suffit aux heuristiques de cv_sections :
  - toutes les lignes d'un bloc reçoivent la même hauteur (hauteur du bloc / n),
    donc aucun faux signal "police plus grande" à l'intérieur d'un bloc ;
  - un bloc ne contenant qu'un titre garde sa hauteur pleine, nettement
    supérieure à celle des lignes de corps de texte : le titre ressort ;
  - le gap vertical entre blocs est conservé, ce qui alimente correctement
    le signal "gap_vertical_important".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Line:
    """Une ligne de texte, avec la géométrie attendue par cv_sections."""
    text: str
    top: int
    height: int
    left: int
    width: int
    column: int = 0
    page: int = 1
    zone: str = ""
    block_num: int = 0

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def avg_height(self) -> float:
        return float(self.height)


def block_to_lines(block) -> list:
    """Éclate un Block en Line, en répartissant sa hauteur sur ses lignes."""
    raw_lines = [l for l in block.text.split("\n") if l.strip()]
    if not raw_lines:
        return []

    n = len(raw_lines)
    line_h = max(1, block.h // n)

    return [
        Line(
            text=raw.strip(),
            top=block.y + i * line_h,
            height=line_h,
            left=block.x,
            width=block.w,
            column=block.column,
            page=block.page,
            zone=block.zone,
            block_num=block.block_num,
        )
        for i, raw in enumerate(raw_lines)
    ]


def blocks_to_lines(blocks: list) -> list:
    """
    Convertit une liste de Block (déjà en ordre de lecture) en liste de Line.
    L'ordre des blocs est préservé : header → col_left → col_right → full.
    """
    lines = []
    for b in blocks:
        lines.extend(block_to_lines(b))
    return lines
