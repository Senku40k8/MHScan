"""Liste de référence des monsties d'un jeu (scans/<jeu>/collection.json).

Chaque scan complet la remplace entièrement : les monsties qui ne sont plus dans l'écurie en disparaissent.
Les différences avec la liste précédente (ajouts, retraits) sont calculées pour le rapport.
"""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from .analyze import identity


def collection_path(game_dir: Path) -> Path:
    return game_dir / "collection.json"


def load(game_dir: Path):
    path = collection_path(game_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _label(record: dict) -> str:
    level = f" Lv{record['level']}" if record.get("level") else ""
    return f"{record.get('name') or '?'}{level}"


def update(game_dir: Path, scan_dir: Path, monsties: list) -> dict:
    """Remplace la liste de référence par ce scan complet ; renvoie les changements."""
    previous = load(game_dir)
    changes = {"previous_scan": previous["scan"] if previous else None, "added": [], "removed": []}
    if previous:
        old = Counter(identity(m) for m in previous["monsties"])
        new = Counter(identity(m) for m in monsties)
        added_keys, removed_keys = new - old, old - new
        for record in monsties:
            key = identity(record)
            if added_keys[key] > 0:
                added_keys[key] -= 1
                changes["added"].append(_label(record))
        for record in previous["monsties"]:
            key = identity(record)
            if removed_keys[key] > 0:
                removed_keys[key] -= 1
                changes["removed"].append(_label(record))
    collection = {
        "scan": scan_dir.name,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(monsties),
        "monsties": monsties,
    }
    collection_path(game_dir).write_text(json.dumps(collection, indent=2, ensure_ascii=False), encoding="utf-8")
    return changes
