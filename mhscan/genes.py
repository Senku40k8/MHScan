"""Catalogue des gènes et des monsties (données Kiranico, MHS1) et rattachement des monsties scannés.

- nom de gène lu par OCR -> gène du catalogue (corrige les petites fautes : « lodrome », « Rathals », « All—Res ») ;
- type d'attaque d'un monstie lu sur la pastille de son icône (rouge Power, bleu Speed, vert Technical) ;
- espèce devinée grâce à son gène d'espèce, ce qui donne son élément d'attaque.
"""
import difflib
import json
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

DATA = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=None)
def catalog(game: str):
    """(gènes, espèces) du jeu, ou (None, None) si aucune donnée n'est disponible pour ce jeu."""
    genes_path, species_path = DATA / f"{game}_genes.json", DATA / f"{game}_monsties.json"
    if not genes_path.exists() or not species_path.exists():
        return None, None
    genes = json.loads(genes_path.read_text(encoding="utf-8"))["genes"]
    species = json.loads(species_path.read_text(encoding="utf-8"))["monsties"]
    return genes, species


def canonical_gene(game: str, name: str):
    """Nom du gène dans le catalogue correspondant au nom lu, ou None s'il est inconnu."""
    genes, _ = catalog(game)
    if not genes or not name:
        return None
    names = [g["name"] for g in genes]
    cleaned = name.replace("—", "-").replace("–", "-").strip()
    if cleaned in names:
        return cleaned
    match = difflib.get_close_matches(cleaned, names, n=1, cutoff=0.8)
    return match[0] if match else None


def badge_type(tile: np.ndarray):
    """Type d'attaque du monstie d'après la pastille en bas à droite de son icône.
    Vérifié sur 390 monsties : concorde à chaque fois avec l'espèce quand elle est connue."""
    if tile is None:
        return None
    h, w = tile.shape[:2]
    cx, cy, r = int(w * 0.82), int(h * 0.81), int(w * 0.06)
    pixels = cv2.cvtColor(tile[cy - r:cy + r, cx - r:cx + r], cv2.COLOR_BGR2HSV).reshape(-1, 3)
    vivid = pixels[(pixels[:, 1] > 80) & (pixels[:, 2] > 60)]
    if len(vivid) < 10:
        return None
    hue = float(np.median(vivid[:, 0]))
    if hue < 12 or hue > 165:
        return "Power"
    if 35 < hue < 85:
        return "Technical"
    if 95 < hue < 130:
        return "Speed"
    return None


def guess_species(game: str, gene_names: list, attack_type):
    """Espèce dont le gène d'espèce est sur le plateau (et dont le type d'attaque concorde), ou None."""
    _, species = catalog(game)
    if not species:
        return None
    by_signature = {s["signature_gene"]: s for s in species}
    candidates = [by_signature[n] for n in gene_names if n in by_signature]
    if attack_type:
        candidates = [s for s in candidates if s["type"] == attack_type] or candidates
    return candidates[0]["name"] if len(candidates) == 1 else None


def enrich(game: str, folder: Path, record: dict) -> dict:
    """Ajoute à un monstie : nom de catalogue de chaque gène (`ref`), type d'attaque, espèce devinée."""
    for row in record["genes"]:
        for cell in row:
            if cell.get("state") == "gene":
                cell["ref"] = canonical_gene(game, cell.get("gene"))
    tile = cv2.imread(str(folder / "tile.png"))
    record["attack_type"] = badge_type(tile)
    refs = [cell.get("ref") for row in record["genes"] for cell in row if cell.get("ref")]
    record["species"] = guess_species(game, refs, record["attack_type"])
    return record
