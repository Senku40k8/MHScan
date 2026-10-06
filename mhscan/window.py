"""Recherche de la fenêtre du jeu, mise au premier plan et capture de sa zone client."""
import ctypes
import time
from ctypes import wintypes

import mss
import numpy as np

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # coordonnées en pixels physiques
except (AttributeError, OSError):
    user32.SetProcessDPIAware()


def find_window(title_part: str) -> int:
    found = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if title_part.lower() in buf.value.lower():
                found.append(hwnd)
        return True

    user32.EnumWindows(enum_proc(callback), 0)
    if not found:
        raise RuntimeError(f"Fenêtre contenant « {title_part} » introuvable. Le jeu est-il lancé ?")
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


class Capturer:
    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self._sct = mss.mss()

    def grab(self) -> np.ndarray:
        """Image BGR de la zone client de la fenêtre."""
        shot = self._sct.grab(client_rect(self.hwnd))
        return np.ascontiguousarray(np.array(shot)[:, :, :3])
