"""Rapport visuel d'un scan (rapport.html dans le dossier du scan), pour vérifier ce qui a été enregistré.

Les monsties sont présentés page par page, à la même place que dans la grille du jeu, avec leur icône,
leur plateau de gènes, le nom de chaque gène et les éventuelles alertes de lecture.

Quand le catalogue des gènes du jeu est disponible (MHS1), on peut mettre des monsties en favoris : l'onglet
Favoris propose pour chacun le meilleur plateau atteignable avec l'écurie et le plateau parfait (static/favoris.js).
"""
import json
import re
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from html import escape
from pathlib import Path

from . import config, genes
from .analyze import analyze_monstie

STATIC = Path(__file__).resolve().parent / "static"

CSS = """
:root {
  --bg: #f6efe0; --surface: #fffaf0; --surface-2: #f1e6cf; --text: #2f2416; --muted: #7a6a52;
  --border: #e2d3b4; --accent: #c4621b; --warn-bg: #fde8d7; --warn: #a3410d; --ok: #2e7d4f;
  --bingo: #e8890c; --shadow: 0 1px 2px rgba(60, 40, 10, .08);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #1b1712; --surface: #26201a; --surface-2: #30281f; --text: #f1e8d8; --muted: #b3a48b;
    --border: #41372b; --accent: #f08a3c; --warn-bg: #4a2a16; --warn: #ffb27a; --ok: #6fcf97;
    --bingo: #ffb347; --shadow: none;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
       font: 15px/1.45 "Segoe UI", system-ui, sans-serif; }
main { max-width: 1500px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; }
.sub { color: var(--muted); margin: 0 0 20px; }
.stats { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
.stat { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
        padding: 10px 16px; min-width: 130px; box-shadow: var(--shadow); }
.stat b { display: block; font-size: 24px; font-variant-numeric: tabular-nums; }
.stat span { color: var(--muted); font-size: 13px; }
.stat.warn b { color: var(--warn); }
.changes { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
           padding: 12px 16px; margin-bottom: 20px; }
.changes h2 { font-size: 16px; margin: 0 0 6px; }
.changes p { margin: 4px 0; }
.toolbar { position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
           background: var(--bg); padding: 10px 0; border-bottom: 1px solid var(--border); margin-bottom: 8px; }
.toolbar input[type=search] { flex: 1 1 260px; padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border);
           background: var(--surface); color: var(--text); font: inherit; }
.toolbar label { color: var(--muted); display: flex; gap: 6px; align-items: center; cursor: pointer; }
#count { color: var(--muted); margin-left: auto; font-variant-numeric: tabular-nums; }
section.page h2 { font-size: 18px; margin: 24px 0 10px; }
.grid { display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); gap: 10px; }
@media (max-width: 1100px) { .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } .card { grid-row: auto !important; grid-column: auto !important; } }
@media (max-width: 640px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 420px) { .grid { grid-template-columns: 1fr; } }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 10px;
        box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.card.has-warn { border-color: var(--warn); }
.head { display: flex; gap: 8px; align-items: center; }
.head img { width: 52px; height: 52px; border-radius: 8px; flex: none; }
.name { font-weight: 600; overflow-wrap: anywhere; }
.meta { color: var(--muted); font-size: 12px; }
.board { width: 100%; max-width: 170px; align-self: center; border-radius: 8px; }
ol.genes { margin: 0; padding-left: 20px; font-size: 13px; }
ol.genes li.bingo::marker { color: var(--bingo); }
.tag { font-size: 11px; font-weight: 600; color: var(--bingo); margin-left: 4px; }
.alert { background: var(--warn-bg); color: var(--warn); border-radius: 6px; padding: 4px 8px; font-size: 12px; }
.card a { color: var(--accent); font-size: 12px; margin-top: auto; }
.empty { color: var(--muted); font-size: 13px; }
.hidden { display: none !important; }
"""

JS = """
const search = document.getElementById('search');
const onlyWarn = document.getElementById('only-warn');
const count = document.getElementById('count');
function apply() {
  const cards = [...document.querySelectorAll('.card:not(.sacrificed)')];
  const q = search.value.trim().toLowerCase();
  let shown = 0;
  for (const card of cards) {
    const ok = (!q || card.dataset.search.includes(q)) && (!onlyWarn.checked || card.classList.contains('has-warn'));
    card.classList.toggle('hidden', !ok);
    if (ok) shown++;
  }
  for (const page of document.querySelectorAll('section.page')) {
    page.classList.toggle('hidden', !page.querySelector('.card:not(.hidden)'));
  }
  count.textContent = shown + ' / ' + cards.length + ' monsties';
}
window.mhscanApply = apply;  // rappelé quand des monsties sacrifiés sont retirés
search.addEventListener('input', apply);
onlyWarn.addEventListener('change', apply);
apply();
"""


def _favorite_data(game: str, scan_dir: Path, monsties: list):
    """Données intégrées au rapport pour les favoris (catalogue, espèces, gènes de chaque monstie), ou None."""
    catalog, species = genes.catalog(game)
    if not catalog:
        return None
    seen = {}
    rows = []
    for m in monsties:
        # (re)rattachement au catalogue : nouveau scan, ou espèce inconnue lors d'une analyse précédente
        if not m.get("species") or any(c.get("state") == "gene" and not c.get("ref") for r in m["genes"] for c in r):
            genes.enrich(game, scan_dir / m["folder"], m)
        # Clé stable d'un scan à l'autre : nom + espèce (+ rang parmi les homonymes de même espèce)
        base = f"{m.get('name') or '?'}|{m.get('species') or '?'}"
        seen[base] = seen.get(base, 0) + 1
        m["key"] = f"{base}|{seen[base]}"
        board = [(c.get("ref") or c.get("gene")) if c.get("state") == "gene" else None for r in m["genes"] for c in r]
        rows.append({"key": m["key"], "index": m["index"], "name": m.get("name"), "page": m["page"], "row": m["row"],
                     "col": m["col"], "folder": m["folder"], "type": m.get("attack_type"), "species": m.get("species"),
                     "genes": board})
    compact = {g["name"]: {"t": g["type"], "e": g["element"], "s": g["size"], "k": g["skill"],
                           "f": re.sub(r" \((S|M|L)\)$", "", g["name"]),
                           "a": g.get("active"),
                           "sl": bool(g.get("sleep")),  # sa compétence peut endormir l'ennemi
                           # espèces qui portent ce gène (Kiranico) ; pour les gènes hors Kiranico, ce sont des URL
                           "src": [x for x in g.get("sources", []) if not x.startswith("http")],
                           "b": [[b["stat"], b["value"]] for b in g.get("bonuses", [])]} for g in catalog}
    return {"game": game, "scan": scan_dir.name, "catalog": compact, "builds": genes.builds(game), "rules": genes.rules(),
            "species": [{"name": sp["name"], "type": sp["type"], "element": sp["element"],
                         "sleep": bool(sp.get("sleep_attack"))} for sp in species],
            "monsties": rows}


def _card(m: dict, with_star: bool = False) -> str:
    folder = escape(m["folder"])
    genes = [c for row in m["genes"] for c in row if c.get("state") == "gene"]
    items = "".join(
        f'<li class="{"bingo" if c.get("bingo") else ""}">{escape(c.get("gene") or "?")}'
        f'{"<span class=tag>BINGO</span>" if c.get("bingo") else ""}</li>'
        for c in genes)
    gene_list = f'<ol class="genes">{items}</ol>' if genes else '<p class="empty">Aucun gène</p>'
    alerts = "".join(f'<div class="alert">{escape(a)}</div>' for a in m.get("checks", []))
    search = " ".join([m.get("name") or ""] + [c.get("gene") or "" for c in genes]).lower()
    return (
        f'<article class="card{" has-warn" if m.get("checks") else ""}"{f' data-key="{escape(m["key"])}"' if with_star else ""} '
        f'style="grid-row:{m["row"]};grid-column:{m["col"]}" data-search="{escape(search)}">'
        f'<div class="head"><img src="{folder}/tile.png" alt="" loading="lazy">'
        f'<div><div class="name">{escape(m.get("name") or "Nom illisible")}</div>'
        f'<div class="meta">#{m["index"]} · case {m["row"]},{m["col"]}</div></div>'
        f'{f"""<button class="star" data-key="{escape(m["key"])}" title="Ajouter aux favoris">☆</button>""" if with_star else ""}</div>'
        f'<img class="board" src="{folder}/genes_board.png" alt="Plateau de gènes" loading="lazy">'
        f'{gene_list}{alerts}'
        f'<a href="{folder}/screen.jpg" target="_blank">Voir la capture</a>'
        f'</article>')


FAVS_VIEW = """<div id="view-favs" class="hidden">
<p class="fv-legend"><b>Build méta</b> : build recommandé en ligne pour l'espèce (sources indiquées).
<b>Optimisé avec ton écurie</b> : les gènes du build méta que tu possèdes ; pour ceux qui manquent, les plateaux
possibles avec des bingos de l'élément du monstie (<span class="ok">vert</span>) ou non-élémentaires
(<span class="half">bleu</span>), chaque compétence passive une seule fois et <b>une seule compétence active</b>.
Deux bingos identiques ne comptent qu'une fois. Tes règles (mhscan/data/gene_rules.json) passent en premier :
Sturdy seulement pour White Monoblos, Tenacity en priorité, Sealing remplaçable, Hypnotic seulement avec une
attaque de sommeil.
Un donneur disparaît après le transfert et ne donne qu'un gène ; les favoris ne sont jamais utilisés comme donneurs.</p>
<p id="fav-storage" class="fv-legend"></p>
<div id="fav-list"></div>
</div>"""


def _data_script(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    script = (STATIC / "favoris.js").read_text(encoding="utf-8")
    return f'<script id="mhscan-data" type="application/json">{payload}</script>\n<script>{script}</script>'


FAVORITES_FILE = "favoris.json"
MAX_JSON_BYTES = 2_000_000


def _valid_favorites(data) -> bool:
    return isinstance(data, list) and all(isinstance(f, dict) and isinstance(f.get("key"), str) for f in data)


def _valid_transfers(data) -> bool:
    return (isinstance(data, dict) and isinstance(data.get("scan"), str)
            and isinstance(data.get("removed"), list) and all(isinstance(k, str) for k in data["removed"])
            and isinstance(data.get("boards"), dict)
            and all(isinstance(b, list) and len(b) == 9 for b in data["boards"].values()))


# Données enregistrées par le rapport : URL -> (fichier dans scans/<jeu>/, contenu par défaut, validation)
API = {
    "/api/favoris": (FAVORITES_FILE, b"[]", _valid_favorites),
    "/api/transferts": ("transferts.json", b"null", _valid_transfers),
}


class _ReportHandler(SimpleHTTPRequestHandler):
    """Sert le dossier des scans du jeu, et lit / écrit les favoris et les transferts effectués."""

    def do_GET(self):
        route = API.get(self.path.split("?")[0])
        if not route:
            return super().do_GET()
        path = Path(self.directory) / route[0]
        body = path.read_bytes() if path.exists() else route[1]
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        route = API.get(self.path)
        if not route:
            return self.send_error(404)
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_JSON_BYTES:
            return self.send_error(413)
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not route[2](data):
                raise ValueError
        except ValueError:
            return self.send_error(400)
        (Path(self.directory) / route[0]).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):  # pas de journal de chaque requête dans la console
        pass


class _ReportServer(ThreadingHTTPServer):
    # Sous Windows, SO_REUSEADDR (activé par défaut) laisserait deux rapports écouter le même port :
    # on exige un port libre, sinon on passe au suivant.
    allow_reuse_address = False


def serve(scan_dir: Path, port: int = 8765) -> None:
    """Ouvre le rapport via un petit serveur local (accessible uniquement depuis ce PC), pour que les favoris
    soient enregistrés dans scans/<jeu>/favoris.json. Tourne jusqu'à Ctrl+C ou la fermeture de la console."""
    game_dir = scan_dir.resolve().parent
    handler = partial(_ReportHandler, directory=str(game_dir))
    for candidate in range(port, port + 20):
        try:
            server = _ReportServer(("127.0.0.1", candidate), handler)
            break
        except OSError:  # port déjà pris (un autre rapport ouvert, par exemple)
            continue
    else:
        raise SystemExit("Aucun port libre pour ouvrir le rapport.")
    url = f"http://127.0.0.1:{server.server_address[1]}/{scan_dir.resolve().name}/rapport.html"
    print(f"Rapport ouvert : {url}")
    print(f"Favoris enregistrés dans {game_dir / FAVORITES_FILE}")
    print("Laisse cette console ouverte tant que tu utilises le rapport ; Ctrl+C pour le fermer.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Rapport fermé.")
    finally:
        server.server_close()


def build(scan_dir: Path, changes: dict = None, open_browser: bool = False) -> Path:
    """Écrit rapport.html dans le dossier du scan (ré-analyse les anciens scans si besoin)."""
    manifest_path = scan_dir / "monsties.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    monsties = manifest["monsties"]
    if any("name" not in m for m in monsties):  # scan antérieur à l'analyse : on la fait maintenant
        for m in monsties:
            analyze_monstie(scan_dir / m["folder"], m)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    if changes is None and (scan_dir / "changements.json").exists():
        changes = json.loads((scan_dir / "changements.json").read_text(encoding="utf-8"))

    cfg = config.load(manifest.get("game", "mhs1"))
    game_name = config.GAMES.get(manifest.get("game"), {}).get("name", manifest.get("game", ""))
    try:
        when = datetime.strptime(manifest.get("scanned_at", scan_dir.name), "%Y%m%d-%H%M%S").strftime("%d/%m/%Y à %H:%M")
    except ValueError:
        when = scan_dir.name
    pages = sorted({m["page"] for m in monsties})
    warnings = sum(1 for m in monsties if m.get("checks"))
    bingos = sum(1 for m in monsties for row in m["genes"] for c in row if c.get("bingo"))
    gene_count = sum(1 for m in monsties for row in m["genes"] for c in row if c.get("state") == "gene")

    status = manifest.get("complete")
    status_text = {True: "Scan complet", False: "Scan incomplet (la liste de référence n'a pas été modifiée)"}.get(status, "")
    changes_html = ""
    if changes:
        if changes.get("previous_scan"):
            def names(items):
                text = ", ".join(escape(x) for x in items) or "aucun"
                return f"<details><summary>voir la liste</summary>{text}</details>" if len(items) > 15 else text
            changes_html = (f'<div class="changes"><h2>Changements depuis le scan précédent</h2>'
                            f'<p><b>{len(changes["added"])} ajouté(s)</b> : {names(changes["added"])}</p>'
                            f'<p><b>{len(changes["removed"])} retiré(s)</b> : {names(changes["removed"])}</p></div>')
        else:
            changes_html = '<div class="changes"><h2>Premier scan complet</h2><p>Il sert de liste de référence.</p></div>'

    fav_data = _favorite_data(manifest.get("game", "mhs1"), scan_dir, monsties)
    if fav_data:  # enregistre les gènes rattachés au catalogue et l'espèce devinée
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    sections = []
    for page in pages:
        cards = "".join(_card(m, bool(fav_data)) for m in sorted(monsties, key=lambda m: (m["row"], m["col"])) if m["page"] == page)
        sections.append(f'<section class="page"><h2>Page {page}</h2><div class="grid" style="--cols:{cfg.cols}">{cards}</div></section>')

    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rapport de scan</title>
<style>{CSS}{(STATIC / "favoris.css").read_text(encoding="utf-8") if fav_data else ""}</style>
</head>
<body>
<main>
<h1>Rapport de scan · {escape(game_name)}</h1>
<p class="sub">Scan du {escape(when)}{" · " + escape(status_text) if status_text else ""}</p>
<div class="stats">
  <div class="stat"><b>{len(monsties)}</b><span>monsties</span></div>
  <div class="stat"><b>{len(pages)}</b><span>page(s)</span></div>
  <div class="stat"><b>{gene_count}</b><span>gènes lus</span></div>
  <div class="stat"><b>{bingos}</b><span>gènes en bingo</span></div>
  <div class="stat{' warn' if warnings else ''}"><b>{warnings}</b><span>monstie(s) à vérifier</span></div>
</div>
{changes_html}
{"""<div class="tabs"><button class="active" data-tab="all">Tous les monsties</button>
<button data-tab="favs">★ Favoris (<span id="fav-count">0</span>)</button></div>""" if fav_data else ""}
<div id="view-all">
<div class="toolbar">
  <input type="search" id="search" placeholder="Rechercher un nom ou un gène…" aria-label="Rechercher">
  <label><input type="checkbox" id="only-warn"> Seulement ceux à vérifier</label>
  <span id="count"></span>
</div>
{"".join(sections) if sections else '<p class="empty">Aucun monstie dans ce scan.</p>'}
</div>
{FAVS_VIEW if fav_data else ""}
</main>
<script>{JS}</script>
{_data_script(fav_data) if fav_data else ""}
</body>
</html>"""
    out = scan_dir / "rapport.html"
    out.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(out.resolve().as_uri())
    return out
