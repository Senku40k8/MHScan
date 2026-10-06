"""Calibration interactive : on trace les zones à la souris sur une capture du jeu."""
import time
from pathlib import Path

import cv2
import numpy as np

from . import window
from .config import Config, save
from .grid import Grid

MAX_DISPLAY_WIDTH = 1600


def capture(cfg: Config, image: str = None, countdown: int = 5) -> np.ndarray:
    if image:
        img = cv2.imread(image)
        if img is None:
            raise SystemExit(f"Image illisible : {image}")
        return img
    hwnd = window.find_window(cfg.window_title)
    window.focus(hwnd)
    for i in range(countdown, 0, -1):
        print(f"Capture dans {i}s...")
        time.sleep(1)
    return window.Capturer(hwnd).grab()


def select_rect(img: np.ndarray, title: str) -> tuple:
    """Rectangle (x0, y0, x1, y1) en fractions de l'image, tracé à la souris."""
    h, w = img.shape[:2]
    scale = min(1.0, MAX_DISPLAY_WIDTH / w)
    shown = cv2.resize(img, (int(w * scale), int(h * scale)))
    x, y, rw, rh = cv2.selectROI(title, shown, showCrosshair=True)
    cv2.destroyWindow(title)
    if rw == 0 or rh == 0:
        raise SystemExit("Sélection annulée.")
    return (x / scale / w, y / scale / h, (x + rw) / scale / w, (y + rh) / scale / h)


def calibrate_grid(cfg: Config, image: str = None) -> None:
    print("Mets le jeu sur la grille des monsties de l'écurie (page 1).")
    img = capture(cfg, image)
    print("Trace un rectangle du CENTRE de la case en haut à gauche jusqu'au CENTRE de la case en bas à droite, puis Entrée.")
    x0, y0, x1, y1 = select_rect(img, "Grille : centre haut-gauche -> centre bas-droite")
    cfg.grid_first_center = (x0, y0)
    cfg.grid_last_center = (x1, y1)
    save(cfg)
    report(cfg, img)


def calibrate_genes(cfg: Config, image: str = None) -> None:
    print("Affiche à l'écran le plateau de gènes (3x3) d'un monstie.")
    img = capture(cfg, image)
    print("Trace un rectangle englobant exactement les 9 cases de gènes, puis Entrée.")
    cfg.gene_board = select_rect(img, "Plateau de genes 3x3")
    save(cfg)
    report(cfg, img)


def report(cfg: Config, img: np.ndarray, out: Path = Path("calibration_preview.png")) -> None:
    """Affiche ce que le programme détecte et enregistre une image de contrôle."""
    h, w = img.shape[:2]
    preview = img.copy()
    if cfg.grid_last_center != (0.0, 0.0):
        grid = Grid.from_config(cfg, w, h)
        preview = grid.draw(preview)
        print("Cases occupées (X) / vides (.) :")
        for row in grid.occupancy(img, cfg.empty_threshold):
            print("  " + " ".join("X" if o else "." for o in row))
        print(f"Curseur détecté en : {grid.find_cursor(img, cfg.cursor_threshold)}")
    if cfg.gene_board != (0.0, 0.0, 0.0, 0.0):
        x0, y0, x1, y1 = cfg.gene_board
        px0, py0, px1, py1 = int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)
        for i in range(4):
            x = px0 + (px1 - px0) * i // 3
            y = py0 + (py1 - py0) * i // 3
            cv2.line(preview, (x, py0), (x, py1), (255, 0, 255), 2)
            cv2.line(preview, (px0, y), (px1, y), (255, 0, 255), 2)
    cv2.imwrite(str(out), preview)
    print(f"Image de contrôle : {out.resolve()}")
