"""Chargement / sauvegarde de la configuration (config.json).

Toutes les positions sont exprimées en fractions (0..1) de la zone client de la
fenêtre du jeu, pour rester valides si la résolution change.
"""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_PATH = Path("config.json")


@dataclass
class Config:
    window_title: str = "Monster Hunter Stories 2"
    rows: int = 3
    cols: int = 6
    # Centre de la case (ligne 0, colonne 0) et de la case (dernière ligne, dernière colonne)
    grid_first_center: tuple = (0.0, 0.0)
    grid_last_center: tuple = (0.0, 0.0)
    # Taille d'une tuile relativement au plus petit pas de la grille (mesuré : 135 px pour un pas de 144 px)
    tile_ratio: float = 0.94
    # Rectangle (x0, y0, x1, y1) du plateau de gènes 3x3
    gene_board: tuple = (0.0, 0.0, 0.0, 0.0)
    # Touches (noms pydirectinput)
    key_up: str = "up"
    key_down: str = "down"
    key_left: str = "left"
    key_right: str = "right"
    # Séquence pour passer à la page suivante (depuis la dernière case de la page)
    next_page_keys: list = field(default_factory=lambda: ["right"])
    # Séquences optionnelles pour ouvrir / fermer la fiche du monstie si les gènes n'y sont pas visibles directement
    open_detail_keys: list = field(default_factory=list)
    close_detail_keys: list = field(default_factory=list)
    # Délais (secondes)
    key_delay: float = 0.25
    page_delay: float = 0.8
    detail_delay: float = 0.6
    # Seuils de détection
    empty_threshold: float = 0.06   # part de pixels différents du fond en dessous de laquelle la case est vide
    cursor_threshold: float = 0.35  # part minimale de pixels orange sur le bord de la tuile pour y voir le curseur
    max_pages: int = 100

    def is_calibrated(self) -> bool:
        return self.grid_last_center != (0.0, 0.0) and self.gene_board != (0.0, 0.0, 0.0, 0.0)


def load(path: Path = CONFIG_PATH) -> Config:
    cfg = Config()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, tuple(value) if isinstance(getattr(cfg, key), tuple) else value)
    return cfg


def save(cfg: Config, path: Path = CONFIG_PATH) -> None:
    path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
