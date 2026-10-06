# MHScan
Scan des monsties MH Stories dans l'écurie pour déterminer les gènes les plus adapter à transférer aux monsties pour optimiser leur stats

## Installation

```
pip install -r requirements.txt
```

Le jeu doit tourner en **fenêtré ou fenêtré sans bordure** (la capture se fait sur sa fenêtre).
Les bandes noires (jeu 16:9 sur un écran 16:10 ou ultra-large) sont détectées et ignorées automatiquement.

## Contrôles

- Déplacement dans la grille : **Z Q S D** (clavier AZERTY). Page suivante : **D** sur la dernière colonne ;
  page précédente : **Q** sur la première colonne (le curseur « sort » de la grille). A / E changent de
  catégorie : le scan ne les utilise pas.
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
- `legend` / `info` (facultatif) : la légende avec le nom des gènes, et la fiche du monstie (nom, stats).

Dans la fenêtre de sélection : glisser à la souris pour tracer, **Espace** pour valider, **C** pour annuler.

Chaque calibration écrit dans `config_<jeu>.json` (seulement ce qui diffère des valeurs par défaut) et une image de contrôle `calibration_preview_<jeu>.png`
(cases de la grille en vert, découpage des gènes en violet, zones `page` / `legend` / `info` en cyan)
et affiche le numéro de page lu. `python -m mhscan check` refait ce contrôle à tout moment.

Si les gènes ne sont visibles qu'après avoir ouvert la fiche du monstie, renseigner dans `config_<jeu>.json`
`open_detail_keys` / `close_detail_keys` (ex. `["enter"]` / `["esc"]`). Les touches de navigation
(`key_up`, `key_left`, `key_down`, `key_right` : `z q s d` par défaut), de changement de page (`next_page_keys` / `prev_page_keys`, `["d"]` / `["q"]`), la taille de la grille (`rows`, `cols`) et le titre
de fenêtre recherché (`window_title`, une regex) sont aussi configurables par jeu.

### 2. Scan

Ouvrir l'écran « Rite of Channeling » (n'importe quelle page, n'importe quelle case), puis dans la console :

```
python -m mhscan scan --game mhs1             # mode automatique
python -m mhscan scan --game mhs1 --assiste   # mode assisté
```

Si Windows refuse de passer le jeu au premier plan, la console affiche **« Passe sur le jeu »** :
cliquer sur le jeu (ou Alt+Tab), le scan démarre alors tout seul.

**Mode automatique** : le scan revient à la page 1 (Q depuis la première colonne, en lisant le numéro de
page). Sur chaque page, il remonte en haut à gauche si besoin, puis parcourt les cases en serpentin, le
chemin le plus court (ligne 1 de gauche à droite, ligne 2 de droite à gauche, ligne 3 de gauche à droite).
Il passe ensuite à la page suivante (D depuis la dernière colonne). Les monsties sont ensuite numérotés et
rangés dans l'ordre de lecture (chaque ligne de gauche à droite), dans `monsties.json` comme dans le rapport.
La position du curseur est vérifiée à chaque pas grâce à son cadre orange. Pour aller vite, il n'y a pas
d'attente fixe : le scan surveille l'écran jusqu'à voir le curseur arrivé et le panneau du monstie à jour,
et l'enregistrement des images et la lecture des textes se font en tâche de fond pendant que le curseur avance. Le scan s'arrête après la dernière
page (numéro de page = nombre de pages) ou à la première page incomplète ; si la page ne change pas alors
qu'il en reste, il s'arrête avec un message d'erreur. Si le jeu ne réagit pas aux touches envoyées, le scan
passe tout seul en mode assisté.

**Mode assisté** : tu déplaces toi-même le curseur (ZQSD) ; chaque monstie survolé est enregistré une fois
(bip aigu), un bip grave signale qu'une page est complète. Attendre le bip avant de passer au suivant.
Le scan se termine tout seul après la dernière page complète, ou avec C.

Pour arrêter : touche **C**. Si le jeu n'est plus au premier plan, le scan se met en pause et reprend
en recliquant sur le jeu. Les monsties déjà scannés restent enregistrés après un arrêt, et tout ce qui
s'affiche est aussi écrit dans `scan.log` dans le dossier du scan.

### Résultat

```
scans/<jeu>/
  collection.json          # liste de référence : le dernier scan complet
  <date-heure>/
    rapport.html           # rapport visuel (ouvert automatiquement à la fin du scan)
    scan.log               # journal du scan
    monsties.json          # tous les monsties du scan, dans l'ordre de lecture : nom, page, case, gènes
    changements.json       # monsties ajoutés / retirés depuis le scan complet précédent
    p01_r1c1/              # page 1, ligne 1, colonne 1
      tile.png             # icône du monstie dans la grille
      genes_board.png      # plateau de gènes complet
      gene_11.png ... gene_33.png
      legend.png, info.png # légende des gènes, fiche du monstie
      screen.jpg           # capture complète, pour retraiter sans relancer le jeu
```

Pour chaque monstie, le scan lit (OCR Windows) son **nom** et le **nom de chaque gène** dans la
légende : elle liste les gènes ligne par ligne, dans le même ordre que le plateau. Chaque case du plateau a un
`state` : `gene` (avec son nom, sa couleur et `bingo` si elle fait partie d'un BINGO), `empty` (case claire)
ou `dark` (case foncée). Les incohérences (nom illisible, nombre de gènes différent de la légende) sont listées
dans `checks` et signalées dans le rapport.

### Rescanner : mise à jour de la liste

Un scan **complet** (toutes les pages parcourues) remplace la liste de référence `collection.json` : les
monsties qui ne sont plus dans l'écurie en disparaissent. Le rapport et la console indiquent les monsties
ajoutés et retirés depuis le scan complet précédent. Un monstie est reconnu d'un scan à l'autre par son nom et
ses gènes (le niveau n'est pas lu : un gain de niveau ne change rien). Un scan **interrompu** ne modifie pas
la liste de référence.

### Rapport visuel

Le rapport s'ouvre dans le navigateur à la fin de chaque scan. Pour le rouvrir :

```
python -m mhscan rapport --game mhs1                       # liste de référence (ou dernier scan)
python -m mhscan rapport --game mhs1 --scan scans/mhs1/<date-heure>
```

Les monsties y sont rangés page par page, à la même place que dans la grille du jeu, avec leur icône, leur
nom, leur plateau de gènes et la liste des gènes lus (bingos signalés). On peut chercher un nom ou
un gène, n'afficher que les monsties à vérifier, et ouvrir la capture d'écran complète de chacun.
