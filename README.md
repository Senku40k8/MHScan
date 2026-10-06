# MHScan
Scan des monsties MH Stories dans l'écurie pour déterminer les gènes les plus adapter à transférer aux monsties pour optimiser leur stats

## Installation

```
pip install -r requirements.txt
```

Le jeu doit tourner en **fenêtré ou fenêtré sans bordure** (la capture se fait sur sa fenêtre).

## Contrôles

- Déplacement dans la grille : **Z Q S D** ; page précédente / suivante : **A** / **E** (clavier AZERTY).
  Les lettres sont envoyées selon la disposition clavier active : sur un clavier QWERTY, mettre `w a s d` dans la config.
- **C** arrête immédiatement le programme, à tout moment et quelle que soit la fenêtre active
  (scan, compte à rebours, fenêtre de sélection). Les monsties déjà scannés restent enregistrés.

## Choix du jeu

Jeux pris en charge : **MHS1** (`mhs1`), **MHS2** (`mhs2`) et **MHS3** (`mhs3`).
Chaque commande accepte `--game mhs1|mhs2|mhs3` ; sans cette option, le jeu est demandé au lancement.
Chaque jeu a sa propre calibration (`config_<jeu>.json`) et ses propres scans (`scans/<jeu>/`).

## Étape 1 : scan de l'écurie

### 1. Calibration (une seule fois, ou après un changement de résolution)

**MHS1 est déjà calibré** pour l'écran « Rite of Channeling » (écran 16:9) : vérifier simplement avec
`python -m mhscan check --game mhs1` que la grille et le plateau tombent juste. Pour MHS2 / MHS3 :

```
python -m mhscan calibrate grid --game mhs2    # jeu sur la grille des monsties, page 1
python -m mhscan calibrate genes --game mhs2   # jeu affichant un plateau de gènes 3x3
```

- `grid` : tracer un rectangle du **centre** de la case en haut à gauche au **centre** de la case en bas à droite.
- `genes` : tracer un rectangle englobant exactement les 9 cases de gènes.
- `page` : l'indicateur « 1 / 22 » sous la grille (lu par l'OCR de Windows, sans rien installer de plus).
- `legend` / `info` (facultatif) : la légende avec le nom des gènes, et la fiche du monstie (nom, niveau, stats).

Dans la fenêtre de sélection : glisser à la souris pour tracer, **Espace** pour valider, **C** pour annuler.

Chaque calibration écrit dans `config_<jeu>.json` (seulement ce qui diffère des valeurs par défaut) et une image de contrôle `calibration_preview_<jeu>.png`
(cases de la grille en vert, découpage des gènes en violet, zones `page` / `legend` / `info` en cyan)
et affiche le numéro de page lu. `python -m mhscan check` refait ce contrôle à tout moment.

Si les gènes ne sont visibles qu'après avoir ouvert la fiche du monstie, renseigner dans `config_<jeu>.json`
`open_detail_keys` / `close_detail_keys` (ex. `["enter"]` / `["esc"]`). Les touches de navigation
(`key_up`, `key_left`, `key_down`, `key_right` : `z q s d` par défaut), de changement de page (`next_page_keys`, `["e"]`), la taille de la grille (`rows`, `cols`) et le titre
de fenêtre recherché (`window_title`, une regex) sont aussi configurables par jeu.

### 2. Scan

Ouvrir l'écurie (n'importe quelle page, n'importe quelle case), puis :

```
python -m mhscan scan --game mhs2
```

Le scan revient d'abord à la page 1 (touche A, en lisant le numéro de page) et place le curseur sur la
première case. Il parcourt ensuite chaque page en serpentin (5× droite, bas, 5× gauche, bas, 5× droite), puis passe à la page suivante.
Sa position est vérifiée à chaque pas grâce au cadre orange de sélection. Le scan s'arrête après la dernière page
(numéro de page = nombre de pages), à la première page incomplète, ou si le changement de page n'a aucun effet.
Si l'indicateur de page n'est pas calibré, le scan part de la page affichée.

Pour arrêter le scan : touche **C**.
Quand le jeu n'est plus au premier plan (par exemple en cliquant sur la console), le scan se met en pause
pour ne pas envoyer les touches à une autre fenêtre ; il reprend en recliquant sur le jeu.
Les monsties déjà scannés restent enregistrés après un arrêt.

### Résultat

```
scans/<jeu>/<date-heure>/
  monsties.json            # index de tous les monsties (page, case, grille de gènes 3x3, état de chaque case)
  001_p01_r1c1/
    tile.png               # icône du monstie dans la grille
    genes_board.png        # plateau de gènes complet
    gene_11.png ... gene_33.png
    legend.png, info.png   # noms des gènes, fiche du monstie (si ces zones sont calibrées)
    screen.jpg             # capture complète, pour retraiter sans relancer le jeu
```

Chaque case du plateau a un `state` : `gene` (avec sa couleur dominante : `rouge`, `bleu`, `vert`, `gris`...),
`empty` (case claire unie) ou `dark` (case foncée unie). Le champ `gene` (nom du gène) vaut `null` pour l'instant :
il sera rempli par l'étape de reconnaissance (lecture de la légende).
