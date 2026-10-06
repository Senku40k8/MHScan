"""Télécharge une fois pour toutes les données MHS1 de Kiranico (gènes et monsties) dans mhscan/data/.

Usage : python tools/fetch_kiranico_mhs1.py
Sources : https://mhst.kiranico.com/gene et https://mhst.kiranico.com/monstie (MHS1 uniquement).
"""
import html
import json
import re
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "mhscan" / "data"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as response:
        return response.read().decode("utf-8")


def text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def divs(fragment: str) -> list:
    return [text(d) for d in re.findall(r"<div>(.*?)</div>", fragment, re.S)]


def parse_genes(page: str) -> list:
    genes = []
    for row in re.findall(r"<tr>(.*?)</tr>", page, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 6:
            continue
        name = text(cells[0])
        attack_type, element = text(cells[3]).split("/")
        stats, values = divs(cells[4]), divs(cells[5])
        size = re.search(r"\((S|M|L)\)$", name)
        genes.append({
            "name": name,
            "type": attack_type,          # Power, Speed, Technical ou No-type
            "element": element,           # Fire, Water, Thunder, Ice, Dragon ou Non-Elem
            "size": size.group(1) if size else None,
            "skill": text(cells[2]),
            "bonuses": [{"stat": s, "value": int(v)} for s, v in zip(stats, values) if s and v],
            "sources": [s for s in divs(cells[1]) if s],
        })
    return genes


def parse_monsties(page: str) -> list:
    monsties = []
    for card in page.split('<div class="card">'):
        title = re.search(r'card-title">(.*?)</h4>', card)
        if not title:
            continue
        after = text(card[title.end():title.end() + 600]).split()
        attack_type = next((w for w in after[:8] if w in ("Power", "Speed", "Technical")), None)
        attribute = re.search(r"default_attribute</code></td><td[^>]*>(.*?)</td>", card)
        genes_block = re.search(r"<h5>Genes.*?</h5>(.*?)<h5>", card, re.S)
        gene_names = [g.strip() for g in re.findall(r">([^<>]*Gene[^<>]*)<", genes_block.group(1))] if genes_block else []
        monsties.append({
            "name": html.unescape(title.group(1)).strip(),
            "type": attack_type,
            "element": text(attribute.group(1)) or "Non-Elem" if attribute else "Non-Elem",
            "signature_gene": gene_names[0] if gene_names else None,
            "genes": gene_names,
        })
    return monsties


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    genes = parse_genes(fetch("https://mhst.kiranico.com/gene"))
    monsties = parse_monsties(fetch("https://mhst.kiranico.com/monstie"))
    source = "https://mhst.kiranico.com (MHS1)"
    (DATA / "mhs1_genes.json").write_text(json.dumps({"source": source, "genes": genes}, indent=1, ensure_ascii=False), encoding="utf-8")
    (DATA / "mhs1_monsties.json").write_text(json.dumps({"source": source, "monsties": monsties}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(genes)} gènes et {len(monsties)} monsties enregistrés dans {DATA}")


if __name__ == "__main__":
    main()
