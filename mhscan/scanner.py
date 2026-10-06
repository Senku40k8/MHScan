"""Parcours de l'écurie et sauvegarde des gènes de chaque monstie.

Deux modes :
- automatique : le programme déplace lui-même le curseur, en serpentin pour aller plus vite
  (ZQSD ; D sur la dernière colonne = page suivante). Les monsties sont ensuite rangés dans l'ordre de lecture ;
- assisté : l'utilisateur déplace le curseur, le programme enregistre chaque monstie survolé.
  Utilisé à la demande (--assiste) ou automatiquement si le jeu ne réagit pas aux touches simulées.

Pour aller vite, l'enregistrement des images et l'OCR se font en tâche de fond pendant que le curseur avance,
et les attentes ne sont pas fixes : on surveille l'écran jusqu'à ce que le curseur soit arrivé et que le
panneau du monstie (plateau, légende, fiche) ait fini de changer.
"""
import json
import queue
import threading
import time
import winsound
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from . import collection, keys, ocr, report, window
from . import genes as catalog
from .analyze import analyze_monstie
from .config import Config
from .grid import Grid, classify_gene_cell, crop_region, gene_cells

POLL = 0.03            # intervalle de surveillance de l'écran (s)
MOVE_TIMEOUT = 1.0     # temps maximal pour voir le curseur arriver sur la case visée
SETTLE_TIMEOUT = 0.8   # temps maximal pour que le panneau du monstie se stabilise
PAGE_TIMEOUT = 2.5     # temps maximal pour voir le numéro de page changer


def snake_order(rows: int, cols: int) -> list:
    """Parcours le plus court : ligne 1 de gauche à droite, ligne 2 de droite à gauche, etc."""
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
        self.complete = False   # vrai si toute l'écurie a été parcourue : le scan devient la liste de référence
        self.pages_done, self.total_pages = set(), None  # suivi du mode assisté
        self.last_panel = None  # panneau du dernier monstie enregistré
        self._lock = threading.Lock()
        self._jobs = queue.Queue()
        self._worker = threading.Thread(target=self._save_worker, daemon=True)
        self._worker.start()

    def log(self, message: str) -> None:
        """Affiche le message et le garde dans scan.log (utile si la console est fermée)."""
        with self._lock:
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

    def panel(self, img: np.ndarray) -> np.ndarray:
        """Miniature du panneau du monstie (plateau de gènes + légende + fiche), pour détecter ses changements."""
        regions = [self.cfg.gene_board, *self.cfg.extra_regions.values()]
        box = (min(r[0] for r in regions), min(r[1] for r in regions), max(r[2] for r in regions), max(r[3] for r in regions))
        zone = cv2.cvtColor(crop_region(img, box), cv2.COLOR_BGR2GRAY)
        return cv2.resize(zone, (160, 120), interpolation=cv2.INTER_AREA).astype(np.int16)

    def settle(self, img: np.ndarray) -> np.ndarray:
        """Attend que le panneau du monstie ait changé (nouveau monstie affiché) puis soit stable."""
        start = time.monotonic()
        current = self.panel(img)
        changed = self.last_panel is None or np.abs(current - self.last_panel).mean() > 2.0
        while time.monotonic() - start < SETTLE_TIMEOUT:
            keys.sleep(POLL)
            new_img = self.cap.grab()
            new = self.panel(new_img)
            stable = np.abs(new - current).mean() < 0.8
            changed = changed or self.last_panel is None or np.abs(new - self.last_panel).mean() > 2.0
            img, current = new_img, new
            # Le panneau a fini de changer ; s'il est identique au précédent depuis 0,4 s, deux monsties
            # se ressemblent vraiment (ou l'affichage est en retard) : on prend l'image telle quelle.
            if stable and (changed or time.monotonic() - start > 0.4):
                break
        return img

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

    def wait_move(self, grid: Grid, before: tuple, expected: tuple):
        """Surveille l'écran après un appui jusqu'à ce que le curseur ait quitté sa case (normalement pour la case
        attendue). Renvoie (image, position) ; la position reste `before` si le jeu n'a pas réagi."""
        start = time.monotonic()
        img, pos = None, None
        while time.monotonic() - start < MOVE_TIMEOUT:
            keys.check_abort()
            img = self.cap.grab()
            pos = grid.find_cursor(img, self.cfg.cursor_threshold)
            if pos == expected or (pos is not None and pos != before):
                return img, pos
            time.sleep(POLL)
        return self.cursor(grid, img)[::-1]

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
                step = (1 if target[0] > pos[0] else -1, 0)
                key = cfg.key_down if step[0] > 0 else cfg.key_up
            else:
                step = (0, 1 if target[1] > pos[1] else -1)
                key = cfg.key_right if step[1] > 0 else cfg.key_left
            keys.press(key, cfg.key_delay)
            img, new_pos = self.wait_move(grid, pos, (pos[0] + step[0], pos[1] + step[1]))
            if new_pos == pos:
                prefer_col = move_row
                ignored += 1
                if not self.keys_work and ignored >= 3:
                    raise KeysIgnored()
            else:
                self.keys_work = True
            pos = new_pos
        raise RuntimeError(f"Impossible d'atteindre la case {target} (curseur bloqué en {pos}).")

    def change_page(self, grid: Grid, img: np.ndarray, page_keys: list, edge_col: int, info):
        """Pousse le curseur au-delà du bord de la grille (colonne edge_col) pour changer de page ;
        renvoie (image, nouvelle info de page)."""
        pos, img = self.cursor(grid, img)
        img = self.move_to(grid, (pos[0], edge_col), img)
        before = grid.signature(img)
        keys.press_sequence(page_keys, self.cfg.key_delay)
        start = time.monotonic()
        while time.monotonic() - start < PAGE_TIMEOUT:
            keys.sleep(0.1)
            img = self.cap.grab()
            new_info = self.read_page(img) if info else None
            if (new_info and new_info[0] != info[0]) or (not info and np.abs(grid.signature(img) - before).mean() > 8.0):
                return self.grab_stable(), new_info
        return img, info

    # --- sauvegarde (en tâche de fond) ---------------------------------------------------
    def save_monstie(self, page: int, r: int, c: int, img: np.ndarray, grid: Grid, gene_img: np.ndarray = None) -> None:
        """Confie l'enregistrement du monstie à la tâche de fond ; le curseur peut repartir aussitôt."""
        self.last_panel = self.panel(gene_img if gene_img is not None else img)
        self._jobs.put((page, r, c, img, grid, gene_img if gene_img is not None else img))

    def _save_worker(self) -> None:
        while True:
            job = self._jobs.get()
            try:
                self._save(*job)
            except Exception as exc:  # une erreur d'enregistrement ne doit pas bloquer le scan
                self.log(f"Erreur d'enregistrement page {job[0]} case ({job[1] + 1},{job[2] + 1}) : {exc}")
            finally:
                self._jobs.task_done()

    def _save(self, page: int, r: int, c: int, grid_img: np.ndarray, grid: Grid, gene_img: np.ndarray) -> None:
        folder = self.out / f"p{page:02d}_r{r + 1}c{c + 1}"
        folder.mkdir(parents=True, exist_ok=True)
        images = {"tile.png": grid.tile(grid_img, r, c)}
        board, cells = gene_cells(gene_img, self.cfg.gene_board)
        images["genes_board.png"] = board
        genes = []
        for gr in range(3):
            row = []
            for gc in range(3):
                name = f"gene_{gr + 1}{gc + 1}.png"
                images[name] = cells[gr][gc]
                row.append({"image": name, **classify_gene_cell(cells[gr][gc]), "gene": None})
            genes.append(row)
        regions = {}
        for region_name, region in self.cfg.extra_regions.items():
            regions[region_name] = f"{region_name}.png"
            images[regions[region_name]] = crop_region(gene_img, region)
        for name, image in images.items():
            cv2.imwrite(str(folder / name), image)
        # Capture complète conservée pour pouvoir retraiter le scan sans relancer le jeu
        cv2.imwrite(str(folder / "screen.jpg"), gene_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        record = {
            "page": page,
            "row": r + 1,
            "col": c + 1,
            "folder": folder.name,
            "tile": "tile.png",
            "genes_board": "genes_board.png",
            "regions": regions,
            # grille 3x3 : state = gene / empty / dark ; gene = nom lu dans la légende ; bingo
            "genes": genes,
        }
        analyze_monstie(folder, record, images)
        catalog.enrich(self.cfg.game, folder, record)  # gènes du catalogue, type d'attaque, espèce (favoris)
        with self._lock:
            self.monsties.append(record)
            count_saved = len(self.monsties)
        count = sum(cell["state"] == "gene" for row in genes for cell in row)
        alert = f"  -> à vérifier : {', '.join(record['checks'])}" if record["checks"] else ""
        self.log(f"  page {page} case ({r + 1},{c + 1}) : {record['name'] or '?'}, {count} gène(s){alert}")
        if count_saved % 18 == 0:
            self.write_manifest()

    def write_manifest(self) -> None:
        with self._lock:
            # Ordre de lecture (page, ligne, colonne), quel que soit l'ordre de parcours
            self.monsties.sort(key=lambda m: (m["page"], m["row"], m["col"]))
            for i, m in enumerate(self.monsties, 1):
                m["index"] = i
            manifest = {"game": self.cfg.game, "scanned_at": self.out.name, "complete": self.complete,
                        "count": len(self.monsties), "monsties": self.monsties}
            self.out.mkdir(parents=True, exist_ok=True)
            text = json.dumps(manifest, indent=2, ensure_ascii=False)
        (self.out / "monsties.json").write_text(text, encoding="utf-8")

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
        self.started = time.monotonic()
        self.log(f"Scan vers {self.out.resolve()}  (mode {'assisté' if assisted else 'automatique'}, {keys.QUIT_HINT})")
        keys.set_target(self.hwnd)
        try:
            self.wait_for_game()
            if assisted:
                self._assisted()
            else:
                try:
                    self._scan_pages()
                    self.complete = True
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
            # On scanne toutes les cases occupées ; une page contenant une case vide est forcément la dernière.
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
                    img = gene_img = grid_img = self.settle(img)
                self.save_monstie(page, r, c, grid_img, grid, gene_img)

            if len(targets) < len(order):
                self.log(f"Page {page} incomplète : fin du scan.")
                return
            if page_info and page_info[0] == page_info[1]:
                self.log("Dernière page scannée : fin du scan.")
                return
            # Page suivante : depuis la dernière colonne, on pousse le curseur au-delà du bord droit
            img, new_info = self.change_page(grid, img, cfg.next_page_keys, grid.cols - 1, page_info)
            if page_info and new_info and new_info[0] == page_info[0]:
                raise RuntimeError(f"la page {page_info[0]} / {page_info[1]} n'a pas changé après {cfg.next_page_keys} "
                                   "sur la dernière colonne : vérifie next_page_keys dans la config.")
            if not page_info and new_info is None and np.abs(grid.signature(img) - grid.signature(grid_img)).mean() < 2.0:
                self.log("La page n'a pas changé : dernière page atteinte.")
                return

    # --- position de départ ----------------------------------------------------------
    def read_page(self, img: np.ndarray):
        """(page, total) lus par OCR, ou None si l'indicateur n'est pas calibré ou illisible."""
        if self.cfg.page_indicator == (0.0, 0.0, 0.0, 0.0) or not ocr.available():
            return None
        return ocr.read_page(crop_region(img, self.cfg.page_indicator))

    def go_to_start(self, grid: Grid, img: np.ndarray) -> np.ndarray:
        """Revient à la page 1 (le curseur se replace ensuite en haut à gauche en commençant la page)."""
        info = self.read_page(img)
        if info is None:
            self.log("Numéro de page illisible (indicateur non calibré ou OCR indisponible) : le scan part de la page affichée.")
            return img
        if info[0] != 1:
            # Les pages bouclent (la page suivante de la dernière est la première) : on prend le chemin le plus court
            forward = info[1] - info[0] + 1 < info[0] - 1
            page_keys, edge = (self.cfg.next_page_keys, grid.cols - 1) if forward else (self.cfg.prev_page_keys, 0)
            self.log(f"Page {info[0]} / {info[1]} : retour à la page 1 par les pages {'suivantes' if forward else 'précédentes'}.")
            for attempt in range(info[1] + 1):
                # Changement de page : on pousse le curseur au-delà du bord de la grille
                img, new_info = self.change_page(grid, img, page_keys, edge, info)
                if new_info[0] != info[0]:
                    self.keys_work = True
                elif not self.keys_work and attempt >= 2:
                    raise KeysIgnored()
                info = new_info
                if info[0] == 1:
                    break
            else:
                raise RuntimeError("impossible de revenir à la page 1 (vérifie prev_page_keys).")
        return img

    # --- mode assisté -----------------------------------------------------------------
    def _assisted(self) -> None:
        """L'utilisateur déplace le curseur (ZQSD) ; chaque monstie survolé est enregistré une fois.
        Se termine avec C, ou tout seul quand la dernière page est entièrement enregistrée."""
        cfg = self.cfg
        self.log("Mode assisté : déplace le curseur sur chaque monstie (ZQSD ; D sur la dernière colonne pour la page suivante), "
                 "chacun est enregistré automatiquement (bip aigu ; bip grave quand la page est complète). "
                 "Attends le bip avant de passer au suivant. Appuie sur C quand tu as fini.")
        img = self.cap.grab()
        grid = Grid.from_config(cfg, img.shape[1], img.shape[0])
        with self._lock:
            done = {(m["page"], m["row"] - 1, m["col"] - 1) for m in self.monsties}
        page_key, total, signature, last_pos, handled_pos = None, None, None, None, None
        while True:
            keys.check_abort()
            time.sleep(0.05)
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
            img = self.settle(img)
            if grid.find_cursor(img, cfg.cursor_threshold) != pos:
                handled_pos = None
                continue
            self.save_monstie(page_key, *pos, img, grid)
            done.add((page_key, *pos))
            winsound.Beep(1200, 60)  # enregistré : on peut passer au suivant
            occupied = grid.occupancy(img, cfg.empty_threshold)
            if all((page_key, r, c) in done for r in range(grid.rows) for c in range(grid.cols) if occupied[r][c]):
                self.log(f"Page {page_key} terminée.")
                self.pages_done.add(page_key)
                self.total_pages = total
                winsound.Beep(600, 250)
                if total and page_key == total:
                    self.log("Dernière page terminée : fin du scan.")
                    return

    def finish(self) -> Path:
        if self._jobs.unfinished_tasks:
            self.log("Fin de l'enregistrement des derniers monsties...")
        self._jobs.join()
        if self.total_pages and set(range(1, self.total_pages + 1)) <= self.pages_done:
            self.complete = True  # mode assisté : toutes les pages ont été parcourues
        self.write_manifest()
        elapsed = time.monotonic() - getattr(self, "started", time.monotonic())
        per = f" ({elapsed / len(self.monsties):.2f} s par monstie)" if self.monsties else ""
        self.log(f"{len(self.monsties)} monsties enregistrés en {elapsed / 60:.1f} min{per} dans "
                 f"{(self.out / 'monsties.json').resolve()}")
        to_check = sum(1 for m in self.monsties if m["checks"])
        if to_check:
            self.log(f"{to_check} monstie(s) à vérifier (voir le rapport).")
        changes = None
        if self.complete and self.monsties:
            changes = collection.update(self.out.parent, self.out, self.monsties)
            (self.out / "changements.json").write_text(json.dumps(changes, indent=2, ensure_ascii=False), encoding="utf-8")
            if changes["previous_scan"]:
                self.log(f"Liste de référence mise à jour : {len(changes['added'])} ajouté(s), {len(changes['removed'])} retiré(s).")
            else:
                self.log("Premier scan complet : il devient la liste de référence.")
        else:
            self.log("Scan incomplet : la liste de référence (collection.json) n'est pas modifiée.")
        if self.monsties:
            path = report.build(self.out, changes)
            self.log(f"Rapport : {path.resolve()}")
        return self.out
