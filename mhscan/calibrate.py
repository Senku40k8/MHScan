"""Calibration interactive : on trace les zones à la souris sur une capture du jeu."""
from pathlib import Path

import cv2
import numpy as np

from . import keys, ocr, window
from .config import Config, save
from .grid import Grid, crop_region

MAX_DISPLAY_WIDTH = 1600


def capture(cfg: Config, image: str = None, countdown: int = 5) -> np.ndarray:
    if image:
        img = cv2.imread(image)
        if img is None:
            raise SystemExit(f"Image illisible : {image}")
        return window.crop_black_bars(img)
    hwnd = window.find_window(cfg.window_title)
    window.focus(hwnd)
    for i in range(countdown, 0, -1):
        print(f"Capture dans {i}s...")
        keys.sleep(1)
    return window.Capturer(hwnd).grab()


KEY_SPACE = 32
CANCEL_KEYS = {ord("c"), ord("C")}


def select_rect(img: np.ndarray, title: str) -> tuple:
    """Rectangle (x0, y0, x1, y1) en fractions de l'image, tracé à la souris.
    Glisser pour tracer, ESPACE pour valider, C (ou fermer la fenêtre) pour annuler."""
    h, w = img.shape[:2]
    scale = min(1.0, MAX_DISPLAY_WIDTH / w)
    shown = cv2.resize(img, (int(w * scale), int(h * scale)))
    state = {"start": None, "end": None, "dragging": False}

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            state.update(start=(x, y), end=(x, y), dragging=True)
        elif event == cv2.EVENT_MOUSEMOVE and state["dragging"]:
            state["end"] = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and state["dragging"]:
            state.update(end=(x, y), dragging=False)

    cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)
    cv2.setWindowProperty(title, cv2.WND_PROP_TOPMOST, 1)
    cv2.setMouseCallback(title, on_mouse)
    help_text = "Glisser : tracer   ESPACE : valider   C : annuler"
    try:
        while True:
            frame = shown.copy()
            cv2.putText(frame, help_text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(frame, help_text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
            if state["start"]:
                cv2.rectangle(frame, state["start"], state["end"], (0, 255, 0), 2)
            cv2.imshow(title, frame)
            key = cv2.waitKey(20) & 0xFF
            if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1 or key in CANCEL_KEYS or keys.stop_requested():
                raise SystemExit("Sélection annulée.")
            if key == KEY_SPACE:
                if state["start"] and abs(state["end"][0] - state["start"][0]) > 2 and abs(state["end"][1] - state["start"][1]) > 2:
                    break
                print("Trace d'abord un rectangle avant de valider avec ESPACE.")
    finally:
        cv2.destroyAllWindows()

    (ax, ay), (bx, by) = state["start"], state["end"]
    x0, x1, y0, y1 = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
    return (x0 / scale / w, y0 / scale / h, x1 / scale / w, y1 / scale / h)


def calibrate_grid(cfg: Config, image: str = None) -> None:
    print("Mets le jeu sur la grille des monsties de l'écurie (page 1).")
    img = capture(cfg, image)
    print("Trace un rectangle du CENTRE de la case en haut à gauche jusqu'au CENTRE de la case en bas à droite, puis ESPACE (c pour annuler).")
    x0, y0, x1, y1 = select_rect(img, "Grille : centre haut-gauche -> centre bas-droite")
    cfg.grid_first_center = (x0, y0)
    cfg.grid_last_center = (x1, y1)
    save(cfg)
    report(cfg, img)


def calibrate_genes(cfg: Config, image: str = None) -> None:
    print("Affiche à l'écran le plateau de gènes (3x3) d'un monstie.")
    img = capture(cfg, image)
    print("Trace un rectangle englobant exactement les 9 cases de gènes, puis ESPACE (c pour annuler).")
    cfg.gene_board = select_rect(img, "Plateau de genes 3x3")
    save(cfg)
    report(cfg, img)


REGION_HELP = {
    "page": "l'indicateur de page (« 1 / 22 ») sous la grille",
    "legend": "la légende listant le nom des gènes du monstie",
    "info": "la fiche du monstie (nom, niveau, stats)",
}


def calibrate_region(cfg: Config, name: str, image: str = None) -> None:
    print(f"Affiche à l'écran {REGION_HELP[name]}.")
    img = capture(cfg, image)
    print(f"Trace un rectangle englobant {REGION_HELP[name]}, puis ESPACE (c pour annuler).")
    rect = select_rect(img, f"Zone {name}")
    if name == "page":
        cfg.page_indicator = rect
    else:
        cfg.extra_regions = {**cfg.extra_regions, name: rect}
    save(cfg)
    report(cfg, img)


def report(cfg: Config, img: np.ndarray, out: Path = None) -> None:
    """Affiche ce que le programme détecte et enregistre une image de contrôle."""
    out = out or Path(f"calibration_preview_{cfg.game}.png")
    cv2.imwrite(str(out.with_name(f"calibration_capture_{cfg.game}.png")), img)  # capture brute, pour diagnostic
    if not cfg.is_calibrated():
        print(f"Calibration incomplète pour {cfg.game} : lance `python -m mhscan calibrate grid --game {cfg.game}` puis `calibrate genes`.")
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
    regions = dict(cfg.extra_regions)
    if cfg.page_indicator != (0.0, 0.0, 0.0, 0.0):
        regions["page"] = cfg.page_indicator
        print(f"Page lue : {ocr.read_page(crop_region(img, cfg.page_indicator)) if ocr.available() else 'OCR indisponible'}")
    for name, (x0, y0, x1, y1) in regions.items():
        cv2.rectangle(preview, (int(x0 * w), int(y0 * h)), (int(x1 * w), int(y1 * h)), (255, 255, 0), 2)
        cv2.putText(preview, name, (int(x0 * w) + 6, int(y0 * h) + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
    cv2.imwrite(str(out), preview)
    print(f"Image de contrôle : {out.resolve()}")
