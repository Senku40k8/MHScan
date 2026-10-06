"""Envoi de touches au jeu (SendInput avec scancodes, accepté par les jeux DirectX)."""
import ctypes
import time

import pydirectinput

pydirectinput.PAUSE = 0.0
ABORT_VK = 0x77  # F8


class Aborted(Exception):
    pass


def check_abort() -> None:
    if ctypes.windll.user32.GetAsyncKeyState(ABORT_VK) & 0x8000:
        raise Aborted("Scan interrompu (F8).")


def press(key: str, delay: float) -> None:
    check_abort()
    pydirectinput.keyDown(key)
    time.sleep(0.05)
    pydirectinput.keyUp(key)
    time.sleep(delay)


def press_sequence(keys: list, delay: float) -> None:
    for key in keys:
        press(key, delay)
