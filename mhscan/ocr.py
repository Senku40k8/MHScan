"""Lecture de texte à l'écran avec l'OCR intégré à Windows 10/11 (hors ligne, rien à installer côté système)."""
import asyncio
import re

import cv2
import numpy as np

try:
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter
except ImportError:  # paquets winrt absents : l'OCR est simplement désactivé
    OcrEngine = None

_engine = None


def available() -> bool:
    return _get_engine() is not None


def _get_engine():
    global _engine
    if _engine is None and OcrEngine is not None:
        _engine = OcrEngine.try_create_from_language(Language("en-US"))
        if _engine is None:
            _engine = OcrEngine.try_create_from_user_profile_languages()
    return _engine


def read_text(img: np.ndarray, upscale: float = 2.0) -> str:
    """Texte lu dans une image BGR (chaîne vide si l'OCR n'est pas disponible)."""
    engine = _get_engine()
    if engine is None or img.size == 0:
        return ""
    if upscale != 1.0:
        img = cv2.resize(img, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    writer = DataWriter()
    writer.write_bytes(bgra.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.BGRA8, bgra.shape[1], bgra.shape[0])

    async def recognize():
        return await engine.recognize_async(bitmap)

    return asyncio.run(recognize()).text


def _variants(img: np.ndarray):
    """L'image brute puis des versions plus faciles à lire (marge, agrandissement, noir et blanc) :
    l'OCR de Windows rate parfois un texte court et serré comme « 1 / 3 »."""
    yield img, 2.0
    pad = max(img.shape[:2]) // 4
    padded = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    yield padded, 3.0
    gray = cv2.cvtColor(padded, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR), 3.0


def read_page(img: np.ndarray):
    """(page actuelle, nombre de pages) lus dans un indicateur du type « 1 / 22 », ou None."""
    for variant, upscale in _variants(img):
        text = read_text(variant, upscale).replace(" ", "")
        match = re.search(r"(\d+)[/|lI\\](\d+)", text)
        if match:
            page, total = int(match.group(1)), int(match.group(2))
            if 1 <= page <= total:
                return page, total
    return None
