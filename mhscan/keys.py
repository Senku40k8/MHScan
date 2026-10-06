"""Envoi de touches au jeu (SendInput avec scancodes, accepté par les jeux DirectX) et arrêt du scan."""
import ctypes
import sys
import threading
import time

import pydirectinput

pydirectinput.PAUSE = 0.0
ABORT_VK = 0x77  # F8, lu globalement même quand le jeu a le focus
QUIT_WORDS = {"q", "quit", "quitter", "stop"}

user32 = ctypes.windll.user32
_stop = threading.Event()
_target_hwnd = None


class Aborted(Exception):
    pass


def _listen_console() -> None:
    """Lit la console en tâche de fond : « q » + Entrée arrête le scan."""
    for line in sys.stdin:
        if line.strip().lower() in QUIT_WORDS:
            _stop.set()
            return


def start(hwnd: int) -> None:
    """Active l'arrêt par la console et mémorise la fenêtre du jeu."""
    global _target_hwnd
    _target_hwnd = hwnd
    _stop.clear()
    threading.Thread(target=_listen_console, daemon=True).start()


def check_abort() -> None:
    if _stop.is_set():
        raise Aborted("Scan arrêté depuis la console.")
    if user32.GetAsyncKeyState(ABORT_VK) & 0x8000:
        raise Aborted("Scan arrêté (F8).")


def wait_for_game() -> None:
    """Met le scan en pause tant que le jeu n'est pas au premier plan, pour ne pas envoyer
    les touches à une autre fenêtre (la console quand on y tape « q », par exemple)."""
    if _target_hwnd is None or user32.GetForegroundWindow() == _target_hwnd:
        return
    print("Pause : le jeu n'est plus au premier plan (clique sur le jeu pour reprendre, ou tape q + Entrée pour arrêter).")
    while user32.GetForegroundWindow() != _target_hwnd:
        check_abort()
        time.sleep(0.2)
    print("Reprise du scan.")
    time.sleep(0.5)


def press(key: str, delay: float) -> None:
    check_abort()
    wait_for_game()
    pydirectinput.keyDown(key)
    time.sleep(0.05)
    pydirectinput.keyUp(key)
    time.sleep(delay)


def press_sequence(keys: list, delay: float) -> None:
    for key in keys:
        press(key, delay)
