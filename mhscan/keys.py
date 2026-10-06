"""Envoi de touches au jeu et arrêt du scan avec la touche C.

Les touches sont envoyées par SendInput en scancodes (ce que lisent les jeux DirectX). Les lettres sont
converties selon la disposition du clavier (AZERTY, QWERTY...) : « z » envoie la touche marquée Z sur
le clavier de l'utilisateur, exactement comme s'il l'avait pressée lui-même.
"""
import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
user32.VkKeyScanExW.argtypes = [wintypes.WCHAR, ctypes.c_void_p]
user32.VkKeyScanExW.restype = ctypes.c_short
user32.MapVirtualKeyExW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p]

QUIT_VK = 0x43  # touche C, quelle que soit la fenêtre active
QUIT_HINT = "appuie sur C pour arrêter"

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x1
KEYEVENTF_KEYUP = 0x2
KEYEVENTF_SCANCODE = 0x8

# Touches nommées : (scancode, touche étendue)
NAMED_KEYS = {
    "up": (0x48, True), "down": (0x50, True), "left": (0x4B, True), "right": (0x4D, True),
    "enter": (0x1C, False), "esc": (0x01, False), "space": (0x39, False), "tab": (0x0F, False),
    "backspace": (0x0E, False),
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class Aborted(Exception):
    pass


_stop = threading.Event()
_watching = threading.Event()
_target_hwnd = None


def _watch_quit_key() -> None:
    while _watching.is_set() and not _stop.is_set():
        if user32.GetAsyncKeyState(QUIT_VK) & 0x8000:
            _stop.set()
        time.sleep(0.02)


def stop_quit_watch() -> None:
    _watching.clear()


def start_quit_watch() -> None:
    """Surveille la touche C en tâche de fond : un appui, même bref et dans n'importe quelle fenêtre, arrête tout."""
    _stop.clear()
    _watching.set()
    threading.Thread(target=_watch_quit_key, daemon=True).start()


def set_target(hwnd: int) -> None:
    global _target_hwnd
    _target_hwnd = hwnd


def stop_requested() -> bool:
    return _stop.is_set()


def check_abort() -> None:
    if _stop.is_set():
        raise Aborted("Arrêt demandé (touche C).")


def sleep(seconds: float) -> None:
    """time.sleep interruptible par la touche C."""
    end = time.monotonic() + seconds
    while True:
        check_abort()
        left = end - time.monotonic()
        if left <= 0:
            return
        time.sleep(min(left, 0.05))


def scancode(key: str) -> tuple:
    """(scancode, étendue) pour une touche nommée ou une lettre de la disposition clavier active."""
    key = key.lower()
    if key in NAMED_KEYS:
        return NAMED_KEYS[key]
    if len(key) != 1:
        raise ValueError(f"Touche inconnue : {key!r} (attendu : une lettre ou {', '.join(NAMED_KEYS)})")
    thread = user32.GetWindowThreadProcessId(_target_hwnd, None) if _target_hwnd else 0
    layout = user32.GetKeyboardLayout(thread)
    vk = user32.VkKeyScanExW(key, layout) & 0xFF
    if vk == 0xFF:
        raise ValueError(f"La touche {key!r} n'existe pas sur la disposition clavier active.")
    return user32.MapVirtualKeyExW(vk, 0, layout), False  # 0 = MAPVK_VK_TO_VSC


def _send(code: int, extended: bool, up: bool) -> None:
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0) | (KEYEVENTF_KEYUP if up else 0)
    event = INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(0, code, flags, 0, 0)))
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


def wait_for_game() -> None:
    """Met le scan en pause tant que le jeu n'est pas au premier plan, pour ne pas envoyer
    les touches à une autre fenêtre."""
    if _target_hwnd is None or user32.GetForegroundWindow() == _target_hwnd:
        return
    print(f"Pause : le jeu n'est plus au premier plan (clique sur le jeu pour reprendre, ou {QUIT_HINT}).")
    while user32.GetForegroundWindow() != _target_hwnd:
        sleep(0.2)
    print("Reprise du scan.")
    sleep(0.5)


def press(key: str, delay: float) -> None:
    check_abort()
    wait_for_game()
    code, extended = scancode(key)
    _send(code, extended, up=False)
    time.sleep(0.05)
    _send(code, extended, up=True)
    sleep(delay)


def press_sequence(keys: list, delay: float) -> None:
    for key in keys:
        press(key, delay)
