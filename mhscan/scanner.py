"""Parcours automatique de l'écurie et sauvegarde des gènes de chaque monstie."""
import json
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from . import keys, window
from .config import Config
from .grid import Grid, gene_cells


def snake_order(rows: int, cols: int) -> list:
    """(0,0)→(0,5), (1,5)→(1,0), (2,0)→(2,5) : 5 fois à droite, 1 fois en bas, 5 fois à gauche..."""
    order = []
    for r in range(rows):
        cs = range(cols) if r % 2 == 0 else range(cols - 1, -1, -1)
        order.extend((r, c) for c in cs)
    return order


class Scanner:
    def __init__(self, cfg: Config, out_root: Path = Path("scans")):
        if not cfg.is_calibrated():
            raise RuntimeError("Configuration non calibrée : lance d'abord `python -m mhscan calibrate grid` puis `calibrate genes` pour ce jeu.")
        self.cfg = cfg
        self.hwnd = window.find_window(cfg.window_title)
        self.cap = window.Capturer(self.hwnd)
        self.out = out_root / cfg.game / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.monsties = []

    # --- capture -------------------------------------------------------------------
    def grab_stable(self, tries: int = 6) -> np.ndarray:
        """Capture une image une fois les animations terminées (deux captures identiques)."""
        prev = self.cap.grab()
        for _ in range(tries):
            time.sleep(0.12)
            cur = self.cap.grab()
            if prev.shape == cur.shape and np.abs(cur.astype(np.int16) - prev).mean() < 1.0:
                return cur
            prev = cur
        return prev

    def cursor(self, grid: Grid, img: np.ndarray):
        for _ in range(5):
            pos = grid.find_cursor(img, self.cfg.cursor_threshold)
            if pos is not None:
                return pos, img
            time.sleep(0.2)
            img = self.grab_stable()
        raise RuntimeError("Curseur introuvable dans la grille (vérifie la calibration avec `python -m mhscan check`).")

    # --- navigation ----------------------------------------------------------------
    def move_to(self, grid: Grid, target: tuple, img: np.ndarray) -> np.ndarray:
        """Déplace le curseur case par case jusqu'à la cible, en vérifiant sa position à chaque pas."""
        cfg = self.cfg
        pos, img = self.cursor(grid, img)
        prefer_col = False  # passe en déplacement horizontal si le jeu refuse de descendre (case vide)
        for _ in range(2 * (grid.rows + grid.cols) + 6):
            if pos == target:
                return img
            move_row = pos[0] != target[0] and not (prefer_col and pos[1] != target[1])
            if move_row:
                key = cfg.key_down if target[0] > pos[0] else cfg.key_up
            else:
                key = cfg.key_right if target[1] > pos[1] else cfg.key_left
            keys.press(key, cfg.key_delay)
            img = self.grab_stable()
            new_pos, img = self.cursor(grid, img)
            if new_pos == pos:
                prefer_col = move_row
            pos = new_pos
        raise RuntimeError(f"Impossible d'atteindre la case {target} (curseur bloqué en {pos}).")

    # --- sauvegarde ----------------------------------------------------------------
    def save_monstie(self, page: int, r: int, c: int, grid_img: np.ndarray, grid: Grid, gene_img: np.ndarray) -> None:
        index = len(self.monsties) + 1
        folder = self.out / f"{index:03d}_p{page:02d}_r{r + 1}c{c + 1}"
        folder.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(folder / "tile.png"), grid.tile(grid_img, r, c))
        board, cells = gene_cells(gene_img, self.cfg.gene_board)
        cv2.imwrite(str(folder / "genes_board.png"), board)
        genes = []
        for gr in range(3):
            row = []
            for gc in range(3):
                name = f"gene_{gr + 1}{gc + 1}.png"
                cv2.imwrite(str(folder / name), cells[gr][gc])
                row.append({"image": name, "gene": None})
            genes.append(row)
        # Capture complète conservée pour pouvoir retraiter le scan sans relancer le jeu
        cv2.imwrite(str(folder / "screen.jpg"), gene_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        self.monsties.append({
            "index": index,
            "page": page,
            "row": r + 1,
            "col": c + 1,
            "folder": folder.name,
            "tile": "tile.png",
            "genes_board": "genes_board.png",
            "genes": genes,  # grille 3x3 ; "gene" sera rempli par l'étape de reconnaissance
        })
        self.write_manifest()
        print(f"  #{index:03d} page {page} case ({r + 1},{c + 1}) enregistré")

    def write_manifest(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        manifest = {"game": self.cfg.game, "scanned_at": self.out.name, "count": len(self.monsties), "monsties": self.monsties}
        (self.out / "monsties.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- boucle principale ---------------------------------------------------------
    def run(self) -> Path:
        cfg = self.cfg
        window.focus(self.hwnd)
        img = self.grab_stable()
        h, w = img.shape[:2]
        grid = Grid.from_config(cfg, w, h)
        order = snake_order(grid.rows, grid.cols)
        print(f"Scan vers {self.out}  (F8 pour interrompre)")

        for page in range(1, cfg.max_pages + 1):
            print(f"Page {page}")
            # La dernière page se remplit dans l'ordre de lecture : en serpentin, une case vide
            # peut précéder une case occupée. On scanne donc toutes les cases occupées de la page,
            # et une page contenant une case vide est forcément la dernière.
            occupied = grid.occupancy(img, cfg.empty_threshold)
            targets = [(r, c) for r, c in order if occupied[r][c]]
            for r, c in targets:
                img = self.move_to(grid, (r, c), img)
                grid_img = img
                if cfg.open_detail_keys:
                    keys.press_sequence(cfg.open_detail_keys, cfg.detail_delay)
                    gene_img = self.grab_stable()
                    keys.press_sequence(cfg.close_detail_keys, cfg.detail_delay)
                    img = self.grab_stable()
                else:
                    gene_img = img
                self.save_monstie(page, r, c, grid_img, grid, gene_img)

            if len(targets) < len(order):
                print(f"Page {page} incomplète : fin du scan.")
                return self.finish()
            before = grid.signature(img)
            keys.press_sequence(cfg.next_page_keys, cfg.page_delay)
            img = self.grab_stable()
            if np.abs(grid.signature(img) - before).mean() < 2.0:
                print("La page n'a pas changé : dernière page atteinte.")
                return self.finish()
        return self.finish()

    def finish(self) -> Path:
        self.write_manifest()
        print(f"{len(self.monsties)} monsties enregistrés dans {self.out / 'monsties.json'}")
        return self.out
