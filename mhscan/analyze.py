"""Analyse des images enregistrées d'un monstie : nom, noms des gènes (lus dans la légende), bingos.

Fonctionne sur les fichiers du dossier du monstie, ce qui permet aussi de ré-analyser un ancien scan.
"""
import re
from pathlib import Path

import cv2
import numpy as np

from . import ocr

# Bande du nom dans l'image de la fiche (fractions), sans le bord du portrait à gauche
NAME_BAND = (0.16, 0.07, 0.80, 0.25)
NAME_SKIP_LEFT = 0.08
# Une entrée de légende est un vrai nom de gène s'il contient au moins un mot de 3 lettres
# (l'OCR lit parfois l'icône ronde d'un gène sans symbole comme « 0 » ou « O »)
_GENE_NAME = re.compile(r"[A-Za-z]{3}")


def _sorted_legend(lines: list) -> list:
    """Entrées de la légende dans l'ordre du plateau : ligne par ligne (deux entrées par ligne), de gauche à droite."""
    entries = [line for line in lines if _GENE_NAME.search(line[0])]
    row_height = 40
    return [text for text, x, y in sorted(entries, key=lambda t: (round(t[2] / row_height), t[1]))]


def _with_prefix(band: np.ndarray) -> np.ndarray:
    """Ajoute le mot « Nom » devant le nom : l'OCR de Windows ignore les textes trop courts comme « FF »."""
    h = band.shape[0]
    background = tuple(int(v) for v in np.median(band.reshape(-1, 3), axis=0))
    prefix = np.full((h, 190, 3), background, np.uint8)
    cv2.putText(prefix, "Nom", (10, int(h * 0.78)), cv2.FONT_HERSHEY_SIMPLEX, h / 48, (20, 45, 80),
                max(2, h // 22), cv2.LINE_AA)
    return cv2.copyMakeBorder(np.hstack([prefix, band]), 40, 40, 40, 40, cv2.BORDER_REPLICATE)


def read_name(info: np.ndarray):
    """Nom du monstie lu sur sa fiche : deux lectures (avec préfixe, et seule avec une marge), on garde
    la plus longue ; à égalité, celle avec préfixe, qui respecte mieux les majuscules."""
    h, w = info.shape[:2]
    x0, y0, x1, y1 = NAME_BAND
    band = info[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    band = band[:, int(band.shape[1] * NAME_SKIP_LEFT):]
    prefixed = ocr.read_text(_with_prefix(band), 2.0).strip()
    prefixed = prefixed[3:].strip() if prefixed.startswith("Nom") else ""
    alone = ocr.read_text(cv2.copyMakeBorder(band, 20, 20, 20, 20, cv2.BORDER_REPLICATE), 3.0).strip()
    best = max([prefixed, alone], key=len)
    return best or None


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


def analyze_monstie(folder: Path, record: dict, images: dict = None) -> dict:
    """Complète l'enregistrement d'un monstie (name, genes[..]["gene"/"bingo"], legend, checks).
    `images` permet de passer les images déjà en mémoire (nom de fichier -> image) pour éviter de les relire."""
    images = images or {}

    def load(name):
        if name in images:
            return images[name]
        path = folder / name
        return cv2.imread(str(path)) if path.exists() else None

    checks = []
    info = load("info.png")
    name = read_name(info) if info is not None and ocr.available() else None
    if name is None:
        checks.append("nom illisible")

    gene_cells = [cell for row in record["genes"] for cell in row if cell.get("state") == "gene"]
    for cell in gene_cells:
        image = load(cell["image"])
        cell["bingo"] = bool(image is not None and has_bingo(image))

    legend_img = load("legend.png")
    legend = _sorted_legend(ocr.read_lines(legend_img)) if legend_img is not None and ocr.available() else []
    if len(legend) == len(gene_cells):
        for cell, gene_name in zip(gene_cells, legend):
            cell["gene"] = gene_name
    else:
        checks.append(f"{len(gene_cells)} gène(s) sur le plateau mais {len(legend)} dans la légende")

    record.update(name=name, legend=legend, checks=checks)
    record.pop("level", None)
    return record


def identity(record: dict) -> tuple:
    """Clé servant à reconnaître un même monstie d'un scan à l'autre."""
    genes = tuple(cell.get("gene") or cell.get("state") for row in record["genes"] for cell in row)
    return record.get("name"), genes
