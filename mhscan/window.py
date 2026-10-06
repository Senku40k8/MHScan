"""Recherche de la fenêtre du jeu, mise au premier plan et capture de sa zone client."""
import ctypes
import re
import time
from ctypes import wintypes

import mss
import numpy as np

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # coordonnées en pixels physiques
except (AttributeError, OSError):
    user32.SetProcessDPIAware()


def find_window(title_pattern: str) -> int:
    pattern = re.compile(title_pattern, re.IGNORECASE)
    found = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if pattern.search(buf.value):
                found.append(hwnd)
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    if not found:
        raise RuntimeError(f"Fenêtre correspondant à « {title_pattern} » introuvable. Le jeu est-il lancé ?")
    return found[0]


def focus(hwnd: int) -> None:
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)


def client_rect(hwnd: int) -> dict:
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return {"left": origin.x, "top": origin.y, "width": rect.right, "height": rect.bottom}


def content_box(img: np.ndarray, threshold: int = 8, min_fill: float = 0.10) -> tuple:
    """(x0, y0, x1, y1) de l'image du jeu sans les bandes noires : un jeu en 16:9 sur un écran 16:10
    (ou ultra-large) est affiché avec des bandes noires qu'il faut ignorer pour que les positions calibrées restent justes.
    Une ligne (ou colonne) ne compte comme image que si au moins min_fill de ses pixels ne sont pas noirs,
    pour ne pas être trompé par un compteur de FPS ou une autre petite incrustation dans une bande."""
    h, w = img.shape[:2]
    lit = img.max(axis=2) > threshold
    rows = np.flatnonzero(lit.mean(axis=1) > min_fill)
    cols = np.flatnonzero(lit.mean(axis=0) > min_fill)
    if len(rows) == 0 or len(cols) == 0:
        return 0, 0, w, h
    x0, x1, y0, y1 = cols[0], cols[-1] + 1, rows[0], rows[-1] + 1
    if (x1 - x0) < w * 0.6 or (y1 - y0) < h * 0.6:  # écran presque noir : pas de recadrage
        return 0, 0, w, h
    return int(x0), int(y0), int(x1), int(y1)


def crop_black_bars(img: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = content_box(img)
    return img[y0:y1, x0:x1]


class Capturer:
    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self._sct = mss.mss()
        self._box = None  # zone de l'image du jeu, mesurée une fois quand le jeu est au premier plan

    def grab_full(self) -> np.ndarray:
        """Image BGR de toute la zone client de la fenêtre."""
        shot = self._sct.grab(client_rect(self.hwnd))
        return np.ascontiguousarray(np.array(shot)[:, :, :3])

    def grab(self) -> np.ndarray:
        """Image BGR du jeu, sans les bandes noires éventuelles."""
        img = self.grab_full()
        if self._box is None:
            if user32.GetForegroundWindow() != self.hwnd:
                return crop_black_bars(img)
            self._box = content_box(img)
            x0, y0, x1, y1 = self._box
            if (x1 - x0, y1 - y0) != (img.shape[1], img.shape[0]):
                print(f"Bandes noires ignorées : image du jeu {x1 - x0}x{y1 - y0} dans une fenêtre {img.shape[1]}x{img.shape[0]}.")
        x0, y0, x1, y1 = self._box
        return np.ascontiguousarray(img[y0:y1, x0:x1])
