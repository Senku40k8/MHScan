# MHScan
Scan des monsties MH Stories dans l'écurie pour déterminer les gènes les plus adapter à transférer aux monsties pour optimiser leur stats

## Installation

```
pip install -r requirements.txt
```

Le jeu doit tourner en **fenêtré ou fenêtré sans bordure** (la capture se fait sur la fenêtre « Monster Hunter Stories 2 »).

## Étape 1 : scan de l'écurie

### 1. Calibration (une seule fois, ou après un changement de résolution)

```
python -m mhscan calibrate grid    # jeu sur la grille des monsties, page 1
python -m mhscan calibrate genes   # jeu affichant un plateau de gènes 3x3
```

- `grid` : tracer un rectangle du **centre** de la case en haut à gauche au **centre** de la case en bas à droite.
- `genes` : tracer un rectangle englobant exactement les 9 cases de gènes.

Chaque calibration écrit `config.json` et une image de contrôle `calibration_preview.png`
(cases de la grille en vert, découpage des gènes en violet). `python -m mhscan check` refait ce contrôle à tout moment.

Si les gènes ne sont visibles qu'après avoir ouvert la fiche du monstie, renseigner dans `config.json`
`open_detail_keys` / `close_detail_keys` (ex. `["enter"]` / `["esc"]`). Les touches de navigation et de
changement de page (`next_page_keys`, `["right"]` par défaut) sont aussi configurables.

### 2. Scan

Se placer sur la page 1 de l'écurie, puis :

```
python -m mhscan scan
```

Le curseur parcourt chaque page en serpentin (5× droite, bas, 5× gauche, bas, 5× droite), puis passe à la page suivante.
Sa position est vérifiée à chaque pas grâce au cadre orange de sélection. Le scan s'arrête à la première page
incomplète ou si le changement de page n'a aucun effet. **F8** interrompt le scan.

### Résultat

```
scans/<date-heure>/
  monsties.json            # index de tous les monsties (page, case, grille de gènes 3x3)
  001_p01_r1c1/
    tile.png               # icône du monstie dans la grille
    genes_board.png        # plateau de gènes complet
    gene_11.png ... gene_33.png
    screen.jpg             # capture complète, pour retraiter sans relancer le jeu
```

Le champ `gene` de chaque case vaut `null` pour l'instant : il sera rempli par l'étape de reconnaissance des gènes.
