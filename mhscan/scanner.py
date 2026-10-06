"""Parcours de l'écurie et sauvegarde des gènes de chaque monstie.

Deux modes :
- automatique : le programme déplace lui-même le curseur (ZQSD / E) ;
- assisté : l'utilisateur déplace le curseur, le programme enregistre chaque monstie survolé.
  Utilisé à la demande (--assiste) ou automatiquement si le jeu ne réagit pas aux touches simulées.
"""
import json
import time
import winsound
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from . import keys, ocr, window
from .config import Config
from .grid import Grid, classify_gene_cell, crop_region, gene_cells


def snake_order(rows: int, cols: int) -> list:
    """(0,0)→(0,5), (1,5)→(1,0), (2,0)→(2,5) : 5 fois à droite, 1 fois en bas, 5 fois à gauche..."""
    order = []
    for r in range(rows):
        cs = range(cols) if r % 2 == 0 else range(cols - 1, -1, -1)
        order.extend((r, c) for c in cs)
    return order


class KeysIgnored(Exception):
    """Le jeu ne réagit pas aux touches envoyées par le programme."""


class Scanner:
    def __init__(self, cfg: Config, out_root: Path = Path("scans")):
        if not cfg.is_calibrated():
            raise RuntimeError(f"configuration non calibrée : lance d'abord `python -m mhscan calibrate grid --game {cfg.game}` "
                               f"puis `python -m mhscan calibrate genes --game {cfg.game}`.")
        self.cfg = cfg
        self.hwnd = window.find_window(cfg.window_title)
        self.cap = window.Capturer(self.hwnd)
        self.out = out_root / cfg.game / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.monsties = []
        self.keys_work = False  # devient vrai dès qu'une touche envoyée a fait bouger le curseur

    def log(self, message: str) -> None:
        """Affiche le message et le garde dans scan.log (utile si la console est fermée)."""
        print(message, flush=True)
        self.out.mkdir(parents=True, exist_ok=True)
        with open(self.out / "scan.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} {message}\n")

    # --- capture -------------------------------------------------------------------
    def grab_stable(self, tries: int = 6) -> np.ndarray:
        """Capture une image une fois les animations terminées (deux captures identiques)."""
        prev = self.cap.grab()
        for _ in range(tries):
            keys.sleep(0.12)
            cur = self.cap.grab()
            if prev.shape == cur.shape and np.abs(cur.astype(np.int16) - prev).mean() < 1.0:
                return cur
            prev = cur
        return prev

    def cursor(self, grid: Grid, img: np.ndarray):
        for _ in range(5):
            keys.check_abort()
            pos = grid.find_cursor(img, self.cfg.cursor_threshold)
            if pos is not None:
                return pos, img
            keys.sleep(0.2)
            img = self.grab_stable()
        self.out.mkdir(parents=True, exist_ok=True)
        debug = self.out / "debug_curseur.png"
        cv2.imwrite(str(debug), grid.draw(img))
        best = max(grid.cursor_score(img, r, c) for r in range(grid.rows) for c in range(grid.cols))
        raise RuntimeError(f"curseur introuvable dans la grille (meilleur score {best:.2f}, seuil {self.cfg.cursor_threshold}). "
                           f"Capture de diagnostic : {debug.resolve()}")

    # --- navigation ----------------------------------------------------------------
    def move_to(self, grid: Grid, target: tuple, img: np.ndarray) -> np.ndarray:
        """Déplace le curseur case par case jusqu'à la cible, en vérifiant sa position à chaque pas."""
        cfg = self.cfg
        pos, img = self.cursor(grid, img)
        prefer_col = False  # passe en déplacement horizontal si le jeu refuse de descendre (case vide)
        ignored = 0
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
                ignored += 1
                if not self.keys_work and ignored >= 3:
                    raise KeysIgnored()
            else:
                self.keys_work = True
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
                row.append({"image": name, **classify_gene_cell(cells[gr][gc]), "gene": None})
            genes.append(row)
        regions = {}
        for region_name, region in self.cfg.extra_regions.items():
            regions[region_name] = f"{region_name}.png"
            cv2.imwrite(str(folder / regions[region_name]), crop_region(gene_img, region))
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
            "regions": regions,
            # grille 3x3 : state = gene / empty / dark ; "gene" (nom) sera rempli par l'étape de reconnaissance
            "genes": genes,
        })
        self.write_manifest()
        count = sum(cell["state"] == "gene" for row in genes for cell in row)
        self.log(f"  #{index:03d} page {page} case ({r + 1},{c + 1}) enregistré : {count} gène(s)")

    def write_manifest(self) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        manifest = {"game": self.cfg.game, "scanned_at": self.out.name, "count": len(self.monsties), "monsties": self.monsties}
        (self.out / "monsties.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- boucle principale ---------------------------------------------------------
    def wait_for_game(self) -> None:
        """Attend que le jeu soit au premier plan : Windows refuse parfois qu'un programme lancé
        depuis un terminal prenne le focus, il faut alors cliquer sur le jeu (ou Alt+Tab)."""
        window.focus(self.hwnd)
        if not window.is_foreground(self.hwnd):
            self.log(">>> Passe sur le jeu (Alt+Tab ou clic) : le scan démarrera tout seul dès qu'il sera au premier plan.")
            while not window.is_foreground(self.hwnd):
                keys.sleep(0.2)
        self.log("Jeu au premier plan, démarrage dans 1 s.")
        keys.sleep(1.0)

    def run(self, assisted: bool = False) -> Path:
        """Lance le scan ; en cas d'arrêt ou d'erreur, les monsties déjà scannés restent enregistrés."""
        self.log(f"Scan vers {self.out.resolve()}  (mode {'assisté' if assisted else 'automatique'}, {keys.QUIT_HINT})")
        keys.set_target(self.hwnd)
        try:
            self.wait_for_game()
            if assisted:
                self._assisted()
            else:
                try:
                    self._scan_pages()
                except KeysIgnored:
                    self.log("Le jeu ne réagit pas aux touches envoyées : passage en mode assisté.")
                    self._assisted()
        except keys.Aborted as exc:
            self.log(str(exc))
        except KeyboardInterrupt:
            self.log("Scan interrompu (Ctrl+C).")
        except RuntimeError as exc:
            self.log(f"Erreur : {exc}")
        return self.finish()

    def _scan_pages(self) -> None:
        cfg = self.cfg
        img = self.grab_stable()
        h, w = img.shape[:2]
        grid = Grid.from_config(cfg, w, h)
        order = snake_order(grid.rows, grid.cols)
        img = self.go_to_start(grid, img)

        for page in range(1, cfg.max_pages + 1):
            keys.check_abort()
            page_info = self.read_page(img)
            self.log(f"Page {page}" + (f" / {page_info[1]}" if page_info else ""))
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
                self.log(f"Page {page} incomplète : fin du scan.")
                return
            if page_info and page_info[0] == page_info[1]:
                self.log("Dernière page scannée : fin du scan.")
                return
            before = grid.signature(img)
            keys.press_sequence(cfg.next_page_keys, cfg.page_delay)
            img = self.grab_stable()
            new_info = self.read_page(img)
            if page_info and new_info:
                unchanged = new_info[0] == page_info[0]
            else:
                unchanged = np.abs(grid.signature(img) - before).mean() < 2.0
            if unchanged:
                self.log("La page n'a pas changé : dernière page atteinte.")
                return

    # --- position de départ ----------------------------------------------------------
    def read_page(self, img: np.ndarray):
        """(page, total) lus par OCR, ou None si l'indicateur n'est pas calibré ou illisible."""
        if self.cfg.page_indicator == (0.0, 0.0, 0.0, 0.0) or not ocr.available():
            return None
        return ocr.read_page(crop_region(img, self.cfg.page_indicator))

    def go_to_start(self, grid: Grid, img: np.ndarray) -> np.ndarray:
        """Revient à la page 1 puis place le curseur sur la première case."""
        cfg = self.cfg
        info = self.read_page(img)
        if info is None:
            self.log("Numéro de page illisible (indicateur non calibré ou OCR indisponible) : le scan part de la page affichée.")
        elif info[0] != 1:
            self.log(f"Page {info[0]} / {info[1]} : retour à la page 1.")
            for attempt in range(info[1] + 1):
                keys.press_sequence(cfg.prev_page_keys, cfg.page_delay)
                img = self.grab_stable()
                new_info = self.read_page(img) or info
                if new_info[0] != info[0]:
                    self.keys_work = True
                elif not self.keys_work and attempt >= 2:
                    raise KeysIgnored()
                info = new_info
                if info[0] == 1:
                    break
            else:
                raise RuntimeError("impossible de revenir à la page 1 (vérifie prev_page_keys).")
        if not grid.is_empty(img, 0, 0, cfg.empty_threshold):
            img = self.move_to(grid, (0, 0), img)
            self.log("Curseur sur la première case.")
        return img

    # --- mode assisté -----------------------------------------------------------------
    def _assisted(self) -> None:
        """L'utilisateur déplace le curseur (ZQSD, E) ; chaque monstie survolé est enregistré une fois.
        Se termine avec C, ou tout seul quand la dernière page est entièrement enregistrée."""
        cfg = self.cfg
        self.log("Mode assisté : déplace le curseur sur chaque monstie (ZQSD, E pour la page suivante), "
                 "chacun est enregistré automatiquement (bip aigu ; bip grave quand la page est complète). "
                 "Attends le bip avant de passer au suivant. Appuie sur C quand tu as fini.")
        img = self.cap.grab()
        grid = Grid.from_config(cfg, img.shape[1], img.shape[0])
        done = {(m["page"], m["row"] - 1, m["col"] - 1) for m in self.monsties}
        page_key, total, signature, last_pos, handled_pos = None, None, None, None, None
        while True:
            keys.check_abort()
            time.sleep(0.1)
            if not window.is_foreground(self.hwnd):
                continue
            img = self.cap.grab()
            pos = grid.find_cursor(img, cfg.cursor_threshold)
            if pos is None or pos != last_pos:  # attend que le curseur soit posé sur deux images de suite
                last_pos = pos
                continue
            # Nouvelle page : la grille change fortement (≈ 38) ; un déplacement du curseur la change très peu (< 1)
            sig = grid.signature(img)
            new_view = signature is None or np.abs(sig - signature).mean() > 8.0
            if pos == handled_pos and not new_view:
                continue
            signature, handled_pos = sig, pos
            info = self.read_page(img)  # relu à chaque nouvelle position : deux pages peuvent se ressembler
            if info:
                page_key, total = info
            elif new_view:
                page_key = (page_key or 0) + 1
            if (page_key, *pos) in done or grid.is_empty(img, *pos, cfg.empty_threshold):
                continue
            img = self.grab_stable()
            if grid.find_cursor(img, cfg.cursor_threshold) != pos:
                handled_pos = None
                continue
            self.save_monstie(page_key, *pos, img, grid, img)
            done.add((page_key, *pos))
            winsound.Beep(1200, 60)  # enregistré : on peut passer au suivant
            occupied = grid.occupancy(img, cfg.empty_threshold)
            if all((page_key, r, c) in done for r in range(grid.rows) for c in range(grid.cols) if occupied[r][c]):
                self.log(f"Page {page_key} terminée.")
                winsound.Beep(600, 250)
                if total and page_key == total:
                    self.log("Dernière page terminée : fin du scan.")
                    return

    def finish(self) -> Path:
        self.write_manifest()
        self.log(f"{len(self.monsties)} monsties enregistrés dans {(self.out / 'monsties.json').resolve()}")
        return self.out
