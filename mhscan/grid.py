"""Géométrie de la grille de l'écurie et détection (case vide, position du curseur)."""
from dataclasses import dataclass

import cv2
import numpy as np

from .config import Config


@dataclass
class Grid:
    rows: int
    cols: int
    x0: float
    y0: float
    step_x: float
    step_y: float
    half: int  # demi-taille d'une tuile en pixels

    @classmethod
    def from_config(cls, cfg: Config, width: int, height: int) -> "Grid":
        fx, fy = cfg.grid_first_center
        lx, ly = cfg.grid_last_center
        x0, y0, x1, y1 = fx * width, fy * height, lx * width, ly * height
        step_x = (x1 - x0) / max(cfg.cols - 1, 1)
        step_y = (y1 - y0) / max(cfg.rows - 1, 1)
        half = int(min(step_x, step_y) * cfg.tile_ratio / 2)
        return cls(cfg.rows, cfg.cols, x0, y0, step_x, step_y, half)

    def center(self, r: int, c: int) -> tuple:
        return int(round(self.x0 + c * self.step_x)), int(round(self.y0 + r * self.step_y))

    def tile(self, img: np.ndarray, r: int, c: int) -> np.ndarray:
        cx, cy = self.center(r, c)
        return img[cy - self.half: cy + self.half, cx - self.half: cx + self.half]

    def background_color(self, img: np.ndarray) -> np.ndarray:
        """Couleur du fond, échantillonnée dans les interstices entre colonnes."""
        samples = []
        for r in range(self.rows):
            for c in range(self.cols - 1):
                cx, cy = self.center(r, c)
                gx = int(cx + self.step_x / 2)
                samples.append(img[cy - 2: cy + 3, gx - 2: gx + 3].reshape(-1, 3))
        return np.median(np.concatenate(samples), axis=0)

    def is_empty(self, img: np.ndarray, r: int, c: int, threshold: float, bg=None) -> bool:
        bg = self.background_color(img) if bg is None else bg
        tile = self.tile(img, r, c).astype(np.int16)
        diff = np.abs(tile - bg).sum(axis=2)
        return float((diff > 45).mean()) < threshold

    def cursor_score(self, img: np.ndarray, r: int, c: int) -> float:
        """Part de pixels orange (bordure de sélection) sur le pourtour de la tuile."""
        tile = self.tile(img, r, c)
        hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
        orange = cv2.inRange(hsv, (4, 140, 100), (22, 255, 255)) > 0
        size = tile.shape[0]
        border = max(3, size // 25)
        ring = np.zeros(orange.shape, bool)
        ring[:border, :] = ring[-border:, :] = ring[:, :border] = ring[:, -border:] = True
        return float(orange[ring].mean())

    def find_cursor(self, img: np.ndarray, threshold: float):
        scores = {(r, c): self.cursor_score(img, r, c) for r in range(self.rows) for c in range(self.cols)}
        best = max(scores, key=scores.get)
        return best if scores[best] >= threshold else None

    def occupancy(self, img: np.ndarray, threshold: float) -> list:
        bg = self.background_color(img)
        return [[not self.is_empty(img, r, c, threshold, bg) for c in range(self.cols)] for r in range(self.rows)]

    def signature(self, img: np.ndarray) -> np.ndarray:
        """Miniature de la grille, pour vérifier qu'un changement de page a bien eu lieu."""
        x0, y0 = self.center(0, 0)
        x1, y1 = self.center(self.rows - 1, self.cols - 1)
        zone = img[y0 - self.half: y1 + self.half, x0 - self.half: x1 + self.half]
        return cv2.resize(cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY), (96, 48)).astype(np.int16)

    def draw(self, img: np.ndarray) -> np.ndarray:
        out = img.copy()
        for r in range(self.rows):
            for c in range(self.cols):
                cx, cy = self.center(r, c)
                cv2.rectangle(out, (cx - self.half, cy - self.half), (cx + self.half, cy + self.half), (0, 255, 0), 2)
        return out


def gene_cells(img: np.ndarray, board: tuple) -> tuple:
    """Découpe le plateau de gènes (x0, y0, x1, y1 en fractions) en 3x3 cases."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = int(board[0] * w), int(board[1] * h), int(board[2] * w), int(board[3] * h)
    crop = img[y0:y1, x0:x1]
    ch, cw = crop.shape[0] / 3, crop.shape[1] / 3
    cells = [[crop[int(r * ch): int((r + 1) * ch), int(c * cw): int((c + 1) * cw)] for c in range(3)] for r in range(3)]
    return crop, cells


def crop_region(img: np.ndarray, region: tuple) -> np.ndarray:
    h, w = img.shape[:2]
    return img[int(region[1] * h): int(region[3] * h), int(region[0] * w): int(region[2] * w)]


def _color_name(hue: float, sat: float) -> str:
    if sat < 60:
        return "gris"
    for limit, name in ((12, "rouge"), (20, "orange"), (35, "jaune"), (85, "vert"), (100, "cyan"), (130, "bleu"), (170, "violet")):
        if hue < limit:
            return name
    return "rouge"


def classify_gene_cell(cell: np.ndarray) -> dict:
    """État d'une case du plateau : « empty » (case claire unie), « dark » (case foncée unie) ou « gene »,
    avec la couleur dominante du gène."""
    h, w = cell.shape[:2]
    patch = cell[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    pixels = patch.reshape(-1, 3).astype(np.float32)
    if pixels.std(axis=0).mean() < 6:
        return {"state": "empty" if pixels.mean() > 110 else "dark"}
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    vivid = hsv[hsv[:, 1] > 90]
    if len(vivid) < 0.15 * len(hsv):
        return {"state": "gene", "color": "gris"}
    hue, sat = float(np.median(vivid[:, 0])), float(np.median(vivid[:, 1]))
    return {"state": "gene", "color": _color_name(hue, sat)}
