# MHScan
Scan des monsties MH Stories dans l'écurie pour déterminer les gènes les plus adapter à transférer aux monsties pour optimiser leur stats

## Installation

```
pip install -r requirements.txt
```

Le jeu doit tourner en **fenêtré ou fenêtré sans bordure** (la capture se fait sur sa fenêtre).

## Choix du jeu

Jeux pris en charge : **MHS1** (`mhs1`), **MHS2** (`mhs2`) et **MHS3** (`mhs3`).
Chaque commande accepte `--game mhs1|mhs2|mhs3` ; sans cette option, le jeu est demandé au lancement.
Chaque jeu a sa propre calibration (`config_<jeu>.json`) et ses propres scans (`scans/<jeu>/`).

## Étape 1 : scan de l'écurie

### 1. Calibration (une seule fois, ou après un changement de résolution)

```
python -m mhscan calibrate grid --game mhs2    # jeu sur la grille des monsties, page 1
python -m mhscan calibrate genes --game mhs2   # jeu affichant un plateau de gènes 3x3
```

- `grid` : tracer un rectangle du **centre** de la case en haut à gauche au **centre** de la case en bas à droite.
- `genes` : tracer un rectangle englobant exactement les 9 cases de gènes.

Dans la fenêtre de sélection : glisser à la souris pour tracer, **Espace** pour valider, **C**, **Q** ou **Échap** pour annuler.

Chaque calibration écrit `config_<jeu>.json` et une image de contrôle `calibration_preview_<jeu>.png`
(cases de la grille en vert, découpage des gènes en violet). `python -m mhscan check` refait ce contrôle à tout moment.

Si les gènes ne sont visibles qu'après avoir ouvert la fiche du monstie, renseigner dans `config_<jeu>.json`
`open_detail_keys` / `close_detail_keys` (ex. `["enter"]` / `["esc"]`). Les touches de navigation et de
changement de page (`next_page_keys`, `["right"]` par défaut), la taille de la grille (`rows`, `cols`) et le titre
de fenêtre recherché (`window_title`, une regex) sont aussi configurables par jeu.

### 2. Scan

Se placer sur la page 1 de l'écurie, puis :

```
python -m mhscan scan --game mhs2
```

Le curseur parcourt chaque page en serpentin (5× droite, bas, 5× gauche, bas, 5× droite), puis passe à la page suivante.
Sa position est vérifiée à chaque pas grâce au cadre orange de sélection. Le scan s'arrête à la première page
incomplète ou si le changement de page n'a aucun effet.

Pour arrêter le scan : taper **`q` puis Entrée** dans la console, ou **F8** en jeu (Ctrl+C fonctionne aussi).
Quand le jeu n'est plus au premier plan (par exemple en cliquant sur la console), le scan se met en pause
pour ne pas envoyer les touches à une autre fenêtre ; il reprend en recliquant sur le jeu.
Les monsties déjà scannés restent enregistrés après un arrêt.

### Résultat

```
scans/<jeu>/<date-heure>/
  monsties.json            # index de tous les monsties (page, case, grille de gènes 3x3)
  001_p01_r1c1/
    tile.png               # icône du monstie dans la grille
    genes_board.png        # plateau de gènes complet
    gene_11.png ... gene_33.png
    screen.jpg             # capture complète, pour retraiter sans relancer le jeu
```

Le champ `gene` de chaque case vaut `null` pour l'instant : il sera rempli par l'étape de reconnaissance des gènes.
