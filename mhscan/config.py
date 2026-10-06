"""Chargement / sauvegarde de la configuration, un fichier par jeu (config_<jeu>.json).

Toutes les positions sont exprimées en fractions (0..1) de la zone client de la
fenêtre du jeu, pour rester valides si la résolution change.
"""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Titre de fenêtre (regex) : ancré au début, en excluant navigateurs / Discord dont les onglets
# peuvent contenir le nom du jeu ; MHS1 ne doit pas attraper MHS2 ou MHS3.
_NOT_OTHER_APP = r"(?!.*(Chrome|Firefox|Edge|Opera|Brave|Discord|YouTube))"

GAMES = {
    "mhs1": {
        "name": "Monster Hunter Stories",
        "window_title": _NOT_OTHER_APP + r"^Monster Hunter Stories(?!\s*[23])",
        # Calibration mesurée sur l'écran « Rite of Channeling » en 2560x1440 (valable pour tout écran 16:9)
        "defaults": {
            "grid_first_center": (0.56428, 0.24965),
            "grid_last_center": (0.89762, 0.44952),
            "gene_board": (0.25401, 0.30290, 0.39469, 0.55187),
            "extra_regions": {
                "legend": (0.03986, 0.57538, 0.43493, 0.88866),  # noms des gènes du monstie
                "info": (0.04259, 0.11964, 0.30481, 0.52559),    # nom, niveau, stats
            },
        },
    },
    "mhs2": {"name": "Monster Hunter Stories 2: Wings of Ruin", "window_title": _NOT_OTHER_APP + r"^Monster Hunter Stories 2"},
    "mhs3": {"name": "Monster Hunter Stories 3", "window_title": _NOT_OTHER_APP + r"^Monster Hunter Stories 3"},
}


@dataclass
class Config:
    game: str = "mhs2"
    # Expression régulière appliquée au titre de la fenêtre du jeu
    window_title: str = GAMES["mhs2"]["window_title"]
    rows: int = 3
    cols: int = 6
    # Centre de la case (ligne 0, colonne 0) et de la case (dernière ligne, dernière colonne)
    grid_first_center: tuple = (0.0, 0.0)
    grid_last_center: tuple = (0.0, 0.0)
    # Taille d'une tuile relativement au plus petit pas de la grille (mesuré : 135 px pour un pas de 144 px)
    tile_ratio: float = 0.94
    # Rectangle (x0, y0, x1, y1) du plateau de gènes 3x3
    gene_board: tuple = (0.0, 0.0, 0.0, 0.0)
    # Zones supplémentaires enregistrées pour chaque monstie, {nom: (x0, y0, x1, y1)} ; ex. legend, info
    extra_regions: dict = field(default_factory=dict)
    # Touches : une lettre telle qu'écrite sur le clavier (convertie selon la disposition AZERTY/QWERTY active)
    # ou un nom parmi up, down, left, right, enter, esc, space, tab, backspace
    key_up: str = "z"
    key_down: str = "s"
    key_left: str = "q"
    key_right: str = "d"
    # Séquence pour passer à la page suivante
    next_page_keys: list = field(default_factory=lambda: ["e"])
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


def defaults(game: str) -> Config:
    cfg = Config(game=game, window_title=GAMES[game]["window_title"])
    for key, value in GAMES[game].get("defaults", {}).items():
        setattr(cfg, key, value)
    return cfg


def _plain(value):
    """Valeur normalisée comme après un aller-retour JSON (tuples -> listes)."""
    return json.loads(json.dumps(value))


def config_path(game: str) -> Path:
    return Path(f"config_{game}.json")


def load(game: str) -> Config:
    cfg = defaults(game)
    path = config_path(game)
    legacy = Path("config.json")
    if game == "mhs2" and not path.exists() and legacy.exists():
        # Calibration d'avant le choix du jeu : son titre de fenêtre (simple sous-chaîne) est remplacé par la regex
        data = json.loads(legacy.read_text(encoding="utf-8"))
        data.pop("window_title", None)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        legacy.unlink()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if hasattr(cfg, key) and key != "game":
                setattr(cfg, key, tuple(value) if isinstance(getattr(cfg, key), tuple) else value)
    return cfg


def save(cfg: Config) -> None:
    """N'enregistre que ce qui diffère des valeurs par défaut du jeu, pour que les améliorations
    des défauts (touches, seuils...) s'appliquent aussi aux configurations existantes."""
    base = _plain(asdict(defaults(cfg.game)))
    changed = {k: v for k, v in _plain(asdict(cfg)).items() if k != "game" and v != base.get(k)}
    config_path(cfg.game).write_text(json.dumps(changed, indent=2), encoding="utf-8")
