"""Gestion de l'espace disque des scans (un scan complet pèse environ 400 Mo, dont 60 % de captures plein écran).

Après chaque scan complet :
- le dernier scan complet est gardé tel quel ;
- l'avant-dernier scan complet est archivé : ses captures plein écran (screen.jpg) sont supprimées et le reste
  (découpes, monsties.json, rapport) est rangé dans un seul fichier <date-heure>.zip ;
- tous les autres scans (complets plus anciens, scans interrompus, anciennes archives) sont supprimés.
Les favoris, les transferts et la liste de référence (collection.json) sont dans scans/<jeu>/ et ne sont pas touchés.
"""
import json
import re
import shutil
import zipfile
from pathlib import Path

SCAN_NAME = re.compile(r"^\d{8}-\d{6}$")


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _is_complete(scan_dir: Path) -> bool:
    manifest = scan_dir / "monsties.json"
    try:
        return bool(json.loads(manifest.read_text(encoding="utf-8")).get("complete"))
    except (OSError, ValueError):
        return False


def _archive(scan_dir: Path) -> Path:
    """Remplace le dossier du scan par une archive .zip sans les captures plein écran."""
    archive = scan_dir.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(scan_dir.rglob("*")):
            if file.is_file() and file.name != "screen.jpg":
                zf.write(file, file.relative_to(scan_dir.parent))
    shutil.rmtree(scan_dir)
    return archive


def cleanup(game_dir: Path, current: Path, log=print) -> None:
    """Applique la politique de conservation après le scan complet `current`."""
    game_dir, current = game_dir.resolve(), current.resolve()
    before = _size(game_dir)
    scans = sorted(p for p in game_dir.iterdir() if p.is_dir() and SCAN_NAME.match(p.name) and p != current)
    archives = sorted(p for p in game_dir.glob("*.zip") if SCAN_NAME.match(p.stem))
    older_complete = [p for p in scans if p.name < current.name and _is_complete(p)]
    previous = older_complete[-1] if older_complete else None
    if previous:
        archive = _archive(previous)
        log(f"Avant-dernier scan archivé (sans captures plein écran) : {archive.name}")
    for path in scans:
        if path != previous and path.name < current.name:
            shutil.rmtree(path)
            log(f"Ancien scan supprimé : {path.name}")
    for path in archives:
        if not previous or path.stem != previous.name:
            path.unlink()
            log(f"Ancienne archive supprimée : {path.name}")
    freed = before - _size(game_dir)
    if freed > 0:
        log(f"Espace libéré : {freed / 1e6:.0f} Mo")
