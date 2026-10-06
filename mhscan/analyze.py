"""Analyse des images enregistrées d'un monstie : nom, niveau, noms des gènes (lus dans la légende), bingos.

Fonctionne sur les fichiers du dossier du monstie, ce qui permet aussi de ré-analyser un ancien scan.
"""
import re
from pathlib import Path

import cv2
import numpy as np

from . import ocr

# Bande du nom dans l'image de la fiche (fractions) : lue seule, elle est plus fiable que la fiche entière
# (avec une marge autour du texte : sans elle, l'OCR coupe ou invente des lettres)
NAME_BAND = (0.16, 0.07, 0.80, 0.25)
# Mots de la fiche qui ne sont pas le nom du monstie
_INFO_WORDS = {"EXP", "HP", "ATK", "SPD", "DEF", "INHERIT", "CHANNEL", "BINGO"}


def _sorted_legend(lines: list) -> list:
    """Entrées de la légende dans l'ordre du plateau : ligne par ligne (deux entrées par ligne), de gauche à droite."""
    if not lines:
        return []
    row_height = 40
    return [text for text, x, y in sorted(lines, key=lambda t: (round(t[2] / row_height), t[1]))]


def parse_info(lines: list) -> tuple:
    """(nom, niveau) lus sur la fiche du monstie."""
    level = None
    name = None
    for text, x, y in sorted(lines, key=lambda t: (t[2], t[1])):
        match = re.search(r"Lv\s*(\d+)", text, re.IGNORECASE)
        if match and level is None:
            level = int(match.group(1))
            continue
        word = text.strip()
        if name is None and word and word.upper().strip("!. ") not in _INFO_WORDS and not re.fullmatch(r"[\d,.\s]+", word):
            name = word
    return name, level


def has_bingo(cell: np.ndarray) -> bool:
    """Gène faisant partie d'un BINGO : anneau orange autour de la pastille.
    Mesuré : ≈ 0,62 de pixels orange dans l'anneau pour un bingo, 0 sinon (même pour un gène rouge ou orange,
    dont la couleur reste à l'intérieur de la pastille)."""
    h, w = cell.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    radius = np.hypot(xx - w / 2, yy - h / 2) / min(h, w)
    ring = (radius >= 0.40) & (radius < 0.44)
    orange = cv2.inRange(cv2.cvtColor(cell, cv2.COLOR_BGR2HSV), (8, 170, 170), (22, 255, 255)) > 0
    return float(orange[ring].mean()) > 0.3


def analyze_monstie(folder: Path, record: dict) -> dict:
    """Complète l'enregistrement d'un monstie (name, level, genes[..]["gene"/"bingo"], checks)."""
    checks = []
    name = level = None
    if (folder / "info.png").exists() and ocr.available():
        info = cv2.imread(str(folder / "info.png"))
        name, level = parse_info(ocr.read_lines(info))
        h, w = info.shape[:2]
        x0, y0, x1, y1 = NAME_BAND
        band = info[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        band = cv2.copyMakeBorder(band, 20, 20, 20, 20, cv2.BORDER_REPLICATE)
        name = ocr.read_text(band, 3.0).strip() or name
    if name is None:
        checks.append("nom illisible")
    if level is None:
        checks.append("niveau illisible")

    gene_cells = [cell for row in record["genes"] for cell in row if cell.get("state") == "gene"]
    for row in record["genes"]:
        for cell in row:
            if cell.get("state") == "gene":
                image = cv2.imread(str(folder / cell["image"]))
                cell["bingo"] = bool(image is not None and has_bingo(image))

    legend = []
    if (folder / "legend.png").exists() and ocr.available():
        legend = _sorted_legend(ocr.read_lines(cv2.imread(str(folder / "legend.png"))))
    if len(legend) == len(gene_cells):
        for cell, gene_name in zip(gene_cells, legend):
            cell["gene"] = gene_name
    else:
        checks.append(f"{len(gene_cells)} gène(s) sur le plateau mais {len(legend)} dans la légende")

    record.update(name=name, level=level, legend=legend, checks=checks)
    return record


def identity(record: dict) -> tuple:
    """Clé servant à reconnaître un même monstie d'un scan à l'autre (le niveau peut changer)."""
    genes = tuple(cell.get("gene") or cell.get("state") for row in record["genes"] for cell in row)
    return record.get("name"), genes
