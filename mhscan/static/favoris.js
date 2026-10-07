// Favoris et builds de gènes (MHS1, données Kiranico + builds méta trouvés en ligne).
//
// Pour chaque favori :
//   - Build méta (parfait) : le build recommandé en ligne pour son espèce (mhscan/data/mhs1_builds.json),
//     placé pour faire le plus de bingos ; sans build connu, le meilleur plateau possible avec tous les gènes du jeu ;
//   - Build optimisé avec ton écurie : les gènes du build méta que tu possèdes (sur le favori ou sur un donneur),
//     et pour les gènes absents, les plateaux possibles qui respectent ces règles :
//       * bingos de l'élément du monstie, ou bingos non-élémentaires (Non-Elem) ;
//       * une compétence passive n'apparaît qu'une fois sur le plateau ;
//       * une seule compétence active par plateau.
// Règles du jeu retenues : toutes les cases sont utilisables, tous les gènes du favori peuvent être remplacés,
// un donneur disparaît après le transfert (un seul gène par donneur), les favoris ne servent jamais de donneurs.
(() => {
  const DATA = JSON.parse(document.getElementById('mhscan-data').textContent);
  const CATALOG = DATA.catalog;
  const SPECIES = Object.fromEntries(DATA.species.map(s => [s.name, s]));
  const BUILDS = DATA.builds || {};
  const MONSTIES = DATA.monsties;
  const BY_KEY = Object.fromEntries(MONSTIES.map(m => [m.key, m]));
  const TYPES = ['Power', 'Speed', 'Technical'];
  const ELEMENTS = ['Fire', 'Water', 'Thunder', 'Ice', 'Dragon', 'Non-Elem'];
  const LINES = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8], [0, 4, 8], [2, 4, 6]];
  const STORE = `mhscan:${DATA.game}:favoris`;
  const MAX_ALTERNATIVES = 6;  // plateaux proposés quand des gènes du build méta manquent

  // --- favoris ---------------------------------------------------------------------------------
  // Ouvert par `python -m mhscan rapport` (serveur local), le rapport enregistre les favoris dans
  // scans/<jeu>/favoris.json. Ouvert directement comme fichier, il ne peut pas écrire sur le disque :
  // les favoris restent alors dans le navigateur.
  let onDisk = false;
  function loadLocal() {
    try { return JSON.parse(localStorage.getItem(STORE)) || []; } catch { return []; }
  }
  async function loadFavs() {
    try {
      const response = await fetch('/api/favoris', { cache: 'no-store' });
      if (response.ok) {
        onDisk = true;
        const saved = await response.json();
        const local = loadLocal();
        if (!saved.length && local.length) {  // reprise des favoris mis avant dans le navigateur
          favs = local;
          await saveFavs(favs);
          return favs;
        }
        return saved;
      }
    } catch { /* pas de serveur : rapport ouvert comme fichier */ }
    return loadLocal();
  }
  async function saveFavs(list) {
    if (onDisk) {
      try {
        const response = await fetch('/api/favoris', {
          method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(list),
        });
        if (!response.ok) throw new Error(response.status);
        setStorageNote();
      } catch {
        setStorageNote('Impossible d\'enregistrer les favoris : la console de `python -m mhscan rapport` est-elle encore ouverte ?');
      }
      return;
    }
    try { localStorage.setItem(STORE, JSON.stringify(list)); } catch { /* stockage indisponible */ }
  }
  function setStorageNote(error) {
    const note = document.getElementById('fav-storage');
    if (!note) return;
    note.className = error ? 'alert' : 'fv-legend';
    note.textContent = error || (onDisk
      ? `Favoris enregistrés dans scans/${DATA.game}/favoris.json.`
      : `Rapport ouvert comme fichier : les favoris restent dans ce navigateur. Ouvre-le avec « python -m mhscan rapport --game ${DATA.game} » pour les enregistrer dans scans/${DATA.game}/favoris.json.`);
  }
  let favs = [];
  const isFav = key => favs.some(f => f.key === key);

  // --- transferts effectués (bouton « Gènes transférés ») -----------------------------------
  // Les donneurs sacrifiés disparaissent du rapport et des donneurs possibles ; le favori prend son nouveau
  // plateau. Enregistré dans scans/<jeu>/transferts.json, valable jusqu'au prochain scan (qui fait foi).
  const DONE_STORE = STORE.replace(':favoris', ':transferts');
  const freshDone = () => ({ scan: DATA.scan, removed: [], boards: {} });
  let done = freshDone();
  for (const m of MONSTIES) m.scanGenes = m.genes;
  async function loadDone() {
    let saved = null;
    if (onDisk) {
      try { const r = await fetch('/api/transferts', { cache: 'no-store' }); if (r.ok) saved = await r.json(); } catch { /* ignoré */ }
    } else {
      try { saved = JSON.parse(localStorage.getItem(DONE_STORE)); } catch { /* ignoré */ }
    }
    return saved && saved.scan === DATA.scan ? saved : freshDone();
  }
  async function saveDone() {
    if (onDisk) {
      try {
        const r = await fetch('/api/transferts', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(done) });
        if (!r.ok) throw new Error(r.status);
      } catch {
        setStorageNote('Impossible d\'enregistrer les transferts : la console de `python -m mhscan rapport` est-elle encore ouverte ?');
      }
      return;
    }
    try { localStorage.setItem(DONE_STORE, JSON.stringify(done)); } catch { /* ignoré */ }
  }
  function applyDone() {
    const removed = new Set(done.removed);
    for (const m of MONSTIES) {
      m.sacrificed = removed.has(m.key);
      m.genes = done.boards[m.key] || m.scanGenes;
    }
    for (const card of document.querySelectorAll('.card[data-key]')) card.classList.toggle('sacrificed', removed.has(card.dataset.key));
    if (window.mhscanApply) window.mhscanApply();
  }
  const plans = {};  // plans calculés, par identifiant de bouton

  function toggleFav(key) {
    if (isFav(key)) favs = favs.filter(f => f.key !== key);
    else favs.push({ key });
    saveFavs(favs);
    refreshStars();
    renderFavs();
  }

  // --- profil du favori : espèce, type d'attaque, élément, build méta ------------------------
  function profile(fav, m) {
    const species = 'species' in fav ? fav.species : (m.species || null);
    const known = species && SPECIES[species];
    const builds = (species && BUILDS[species]) || [];
    return {
      species,
      type: fav.type || (known ? known.type : m.type) || 'Power',
      element: fav.element || (known ? known.element : null) || 'Non-Elem',
      elementGuessed: !fav.element && !known,
      builds,
      build: builds[Math.min(fav.build || 0, Math.max(builds.length - 1, 0))] || null,
    };
  }

  // --- règles des gènes ------------------------------------------------------------------------
  const gene = name => CATALOG[name] || null;
  const skillFamily = name => { const g = gene(name); return g && g.k ? g.k.replace(/ \((S|M|L)\)$/, '') : null; };
  const isActive = name => !!(gene(name) && gene(name).a);
  // Classe d'élément pour les bingos : E = élément du monstie, N = non-élémentaire, X = autre
  const elementClass = (name, prof) => {
    const g = gene(name);
    if (!g) return 'X';
    if (g.e === prof.element) return 'E';
    return g.e === 'Non-Elem' ? 'N' : 'X';
  };
  function value(name, prof) {
    const g = gene(name);
    if (!g) return 0;
    const useful = new Set(['Attack Up', 'Crit Rate Up', `${prof.element} Attack Up`]);
    return g.b.filter(b => useful.has(b[0])).reduce((sum, b) => sum + b[1], 0) + ({ L: 0.3, M: 0.2, S: 0.1 }[g.s] || 0);
  }

  // Bingos comptés : lignes de 3 gènes de l'élément du monstie, ou de 3 gènes non-élémentaires.
  function elementBingos(classes) {
    let count = 0;
    for (const [a, b, c] of LINES) {
      if (classes[a] && classes[a] !== 'X' && classes[a] === classes[b] && classes[b] === classes[c]) count++;
    }
    return count;
  }
  function typeBingos(board) {
    let count = 0;
    for (const line of LINES) {
      const g = line.map(i => board[i] && gene(board[i]));
      if (g.every(Boolean) && g[0].t !== 'No-type' && g.every(x => x.t === g[0].t)) count++;
    }
    return count;
  }
  function boardStats(board, prof) {
    const actives = board.filter(n => n && isActive(n)).length;
    const families = board.filter(n => n && !isActive(n)).map(skillFamily).filter(Boolean);
    return {
      elementBingos: elementBingos(board.map(n => (n ? elementClass(n, prof) : null))),
      typeBingos: typeBingos(board),
      actives,
      duplicatePassives: families.length - new Set(families).size,
    };
  }

  // Place les gènes mobiles dans les cases libres : d'abord le plus de bingos d'élément (on essaie toutes les
  // répartitions des classes E / N / X sur les cases libres), puis le plus de bingos de type.
  // Le meilleur motif ne dépend que des classes des cases fixes et du nombre de gènes mobiles par classe :
  // il est mémorisé pour ne pas refaire la recherche à chaque combinaison essayée.
  const layoutMemo = new Map();
  function bestLayout(fixedClasses, counts) {
    const memoKey = fixedClasses.map(c => c || '.').join('') + `|${counts.E},${counts.N},${counts.X}`;
    if (layoutMemo.has(memoKey)) return layoutMemo.get(memoKey);
    const free = fixedClasses.map((c, i) => (c ? null : i)).filter(i => i !== null);
    const classes = fixedClasses.slice();
    const left = { ...counts };
    let best = null, bestCount = -1;
    (function fill(k) {
      const remaining = left.E + left.N + left.X;
      if (!remaining) {
        const count = elementBingos(classes);
        if (count > bestCount) { bestCount = count; best = classes.slice(); }
        return;
      }
      if (k === free.length) return;
      for (const c of ['E', 'N', 'X']) {
        if (!left[c]) continue;
        left[c]--; classes[free[k]] = c;
        fill(k + 1);
        left[c]++; classes[free[k]] = null;
      }
      if (free.length - k > remaining) fill(k + 1);  // case laissée vide
    })(0);
    layoutMemo.set(memoKey, best);
    return best;
  }

  // Place les gènes mobiles dans les cases libres : le plus de bingos d'élément (E / N) possible.
  function arrange(fixed, movable, prof) {
    const freeCount = fixed.filter(n => !n).length;
    const byClass = { E: [], N: [], X: [] };
    for (const name of movable.slice(0, freeCount)) byClass[elementClass(name, prof)].push(name);
    const layout = bestLayout(fixed.map(n => (n ? elementClass(n, prof) : null)),
      { E: byClass.E.length, N: byClass.N.length, X: byClass.X.length });
    const board = fixed.slice();
    if (!layout) return board;
    layout.forEach((c, i) => { if (!board[i] && c) board[i] = byClass[c].shift(); });
    return board;
  }

  // Appariement donneurs <-> gènes (un donneur ne donne qu'un gène), par chemins augmentants.
  function makeMatcher(donorsByGene) {
    const assignment = {};
    const tryAssign = (name, seen) => {
      for (const donor of donorsByGene[name] || []) {
        if (seen.has(donor)) continue;
        seen.add(donor);
        if (!(donor in assignment) || tryAssign(assignment[donor], seen)) { assignment[donor] = name; return true; }
      }
      return false;
    };
    return {
      assignment,
      add: name => tryAssign(name, new Set()),
      clone() { const c = makeMatcher(donorsByGene); Object.assign(c.assignment, assignment); return c; },
    };
  }

  // Cherche les meilleurs plateaux : gènes imposés (fixes ou mobiles) + gènes de remplacement, en respectant les
  // règles (compétences passives uniques, une seule active, bingos E / N).
  // Les bingos ne dépendent que du nombre de gènes de chaque classe : on essaie chaque répartition
  // (x gènes de l'élément du monstie, y non-élémentaires) en prenant les meilleurs gènes disponibles de chaque
  // classe, puis des variantes (un gène écarté à chaque fois) pour proposer d'autres possibilités.
  function searchBoards({ fixed, required, candidates, matcher, prof }) {
    const used = [...fixed.filter(Boolean), ...required];
    const usedFamilies = new Set(used.filter(n => !isActive(n)).map(skillFamily).filter(Boolean));
    const usedNames = new Set(used);
    const activeBudget = Math.max(0, 1 - used.filter(isActive).length);
    const slotsLeft = 9 - used.length;
    // Candidats compatibles : élément du monstie ou non-élémentaire, compétence absente du plateau,
    // le meilleur gène par compétence passive (gènes du favori d'abord, puis par valeur).
    const families = new Set();
    const seen = new Set();
    const compatible = candidates
      .filter(c => !usedNames.has(c.name) && gene(c.name) && elementClass(c.name, prof) !== 'X')
      .filter(c => (isActive(c.name) ? activeBudget > 0 : !usedFamilies.has(skillFamily(c.name))))
      .sort((a, b) => (b.own ? 1 : 0) - (a.own ? 1 : 0) || value(b.name, prof) - value(a.name, prof))
      .filter(c => {
        if (seen.has(c.name)) return false;
        seen.add(c.name);
        if (isActive(c.name)) return true;
        const family = skillFamily(c.name);
        return families.has(family) ? false : families.add(family);
      });
    const byClass = { E: compatible.filter(c => elementClass(c.name, prof) === 'E'),
                      N: compatible.filter(c => elementClass(c.name, prof) === 'N') };

    // Prend les meilleurs gènes de chaque classe (hors `excluded`) ; null si impossible.
    function pick(counts, excluded) {
      const board = fixed.slice();
      const m = matcher ? matcher.clone() : null;
      const chosen = [];
      let actives = 0;
      for (const cls of ['E', 'N']) {
        let need = counts[cls];
        for (const c of byClass[cls]) {
          if (!need) break;
          if (excluded.has(c.name)) continue;
          if (isActive(c.name) && actives >= activeBudget) continue;
          if (c.own ? board[c.slot] : (m && !m.add(c.name))) continue;
          if (c.own) board[c.slot] = c.name;
          if (isActive(c.name)) actives++;
          chosen.push(c);
          need--;
        }
        if (need) return null;
      }
      const movable = [...required, ...chosen.filter(c => !c.own).map(c => c.name)];
      if (movable.length > board.filter(n => !n).length) return null;
      const placed = arrange(board, movable, prof);
      return { board: placed, stats: boardStats(placed, prof), chosen, matcher: m,
               total: placed.reduce((s, n) => s + (n ? value(n, prof) : 0), 0),
               transfers: movable.length };
    }

    const results = [];
    const fill = Math.min(slotsLeft, byClass.E.length + byClass.N.length);
    for (let total = fill; total >= 0 && !results.length; total--) {  // le plus de gènes possible
      for (let nE = 0; nE <= total; nE++) {
        const r = pick({ E: nE, N: total - nE }, new Set());
        if (r) results.push({ ...r, counts: { E: nE, N: total - nE } });
      }
    }
    // À bingos égaux : plus de gènes de l'élément du monstie, puis de bingos de type, de bonus, moins de transferts
    const ownElement = r => r.board.filter(n => n && elementClass(n, prof) === 'E').length;
    const rank = (a, b) => b.stats.elementBingos - a.stats.elementBingos || ownElement(b) - ownElement(a)
      || b.stats.typeBingos - a.stats.typeBingos || b.total - a.total || a.transfers - b.transfers;
    results.sort(rank);
    // Variantes des meilleures répartitions : on écarte tour à tour un gène choisi
    for (const base of results.slice(0, 3)) {
      for (const c of base.chosen) {
        const r = pick(base.counts, new Set([c.name]));
        if (r) results.push({ ...r, counts: base.counts });
      }
    }
    if (!results.length) {  // aucun remplaçant possible : seulement les gènes imposés
      const placed = arrange(fixed, required, prof);
      results.push({ board: placed, stats: boardStats(placed, prof), total: 0, matcher, transfers: required.length });
    }
    results.sort(rank);
    const unique = [];
    const signatures = new Set();
    for (const r of results) {
      const sig = r.board.map(n => n || '').join('|');
      if (signatures.has(sig)) continue;
      signatures.add(sig);
      unique.push(r);
      if (unique.length >= MAX_ALTERNATIVES) break;
    }
    return unique;
  }

  // Build méta (parfait) : le build trouvé en ligne, complété si besoin avec les gènes du jeu.
  function perfectBoard(prof) {
    const required = prof.build ? prof.build.genes.filter(gene).slice(0, 9) : [];
    const candidates = Object.keys(CATALOG).map(name => ({ name }));
    return searchBoards({ fixed: new Array(9).fill(null), required, candidates, matcher: null, prof })[0].board;
  }

  // Build optimisé : gènes du build méta disponibles dans l'écurie, puis plateaux possibles pour les absents.
  function optimizedPlans(m, prof, unavailable) {
    const donorsByGene = {};
    for (const d of MONSTIES) {
      if (d.key === m.key || d.sacrificed || unavailable.has(d.key)) continue;
      for (const name of new Set(d.genes.filter(Boolean))) (donorsByGene[name] = donorsByGene[name] || []).push(d.key);
    }
    const matcher = makeMatcher(donorsByGene);
    const fixed = new Array(9).fill(null);
    const required = [];
    const missing = [];
    for (const name of prof.build ? prof.build.genes.slice(0, 9) : []) {
      const slot = m.genes.indexOf(name);
      if (slot >= 0) fixed[slot] = name;               // déjà sur le favori : il reste à sa place
      else if (matcher.add(name)) required.push(name);  // transféré depuis un donneur
      else missing.push(name);
    }
    const candidates = [];
    m.genes.forEach((name, slot) => { if (name && !fixed.includes(name)) candidates.push({ name, slot, own: true }); });
    for (const name of Object.keys(donorsByGene)) candidates.push({ name, own: false });
    const results = searchBoards({ fixed, required, candidates, matcher, prof });
    return {
      missing,
      alternatives: results.map(r => {
        const donorOf = {};
        for (const [donor, name] of Object.entries(r.matcher.assignment)) donorOf[name] = donor;
        const transfers = r.board
          .map((name, slot) => (name && m.genes[slot] !== name ? { slot, name, donor: BY_KEY[donorOf[name]] } : null))
          .filter(t => t && t.donor);
        return { board: r.board, stats: r.stats, transfers, donors: transfers.map(t => t.donor.key) };
      }),
    };
  }

  // --- affichage ---------------------------------------------------------------------------
  const esc = s => String(s ?? '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const short = name => name.replace(/ Gene\b/, '');
  const cellCase = slot => `${Math.floor(slot / 3) + 1},${slot % 3 + 1}`;

  function boardHtml(title, board, prof, extra = '', compact = false) {
    const s = boardStats(board, prof);
    const cells = board.map(name => {
      if (!name) return '<div class="fv-cell fv-empty">—</div>';
      const g = gene(name);
      const cls = elementClass(name, prof);
      const meta = g ? `${g.t} · ${g.e}` : 'inconnu';
      const kind = g ? (g.a ? 'active' : 'passive') : '';
      return `<div class="fv-cell fv-c${cls}" title="${esc(name)} — ${esc(meta)}${g ? ` — ${esc(g.k)} (${kind})` : ''}">`
        + `<span class="fv-dot fv-el-${g ? g.e.replace(/[^A-Za-z]/g, '') : 'x'}"></span>`
        + `<b>${esc(short(name))}${g && g.a ? ' <i class="fv-active">actif</i>' : ''}</b><small>${esc(meta)}</small></div>`;
    }).join('');
    const warnings = [];
    if (s.actives > 1) warnings.push(`${s.actives} compétences actives`);
    if (s.duplicatePassives) warnings.push('compétence passive en double');
    return `<div class="fv-board${compact ? ' fv-compact' : ''}">${title ? `<h4>${esc(title)}</h4>` : ''}<div class="fv-grid">${cells}</div>
      <p class="fv-score"><b>${s.elementBingos} bingo${s.elementBingos > 1 ? 's' : ''} ${esc(prof.element)}/Non-Elem</b>
      · ${s.typeBingos} bingo${s.typeBingos > 1 ? 's' : ''} de type · ${s.actives} active${s.actives > 1 ? 's' : ''}
      ${warnings.length ? `<span class="fv-warn"> · ${esc(warnings.join(', '))}</span>` : ''}</p>${extra}</div>`;
  }

  function transfersHtml(plan, favKey, id) {
    plans[id] = { favKey, plan };
    if (!plan.transfers.length) return '<p class="meta">Aucun transfert à faire.</p>';
    return `<ol class="fv-transfers">${plan.transfers.map(t => `<li>Case ${cellCase(t.slot)} : <b>${esc(t.name)}</b> ← ${esc(t.donor.name || '?')}
        <span class="meta">(page ${t.donor.page}, case ${t.donor.row},${t.donor.col}) — sacrifié</span></li>`).join('')}</ol>
      <button class="fv-done" data-plan="${esc(id)}" title="À cliquer une fois ces transferts faits dans le jeu">Gènes transférés</button>`;
  }

  function select(label, field, value, options, fav) {
    const opts = options.map(o => `<option value="${esc(o.value)}"${String(o.value) === String(value) ? ' selected' : ''}>${esc(o.label)}</option>`).join('');
    return `<label>${label}<select data-key="${esc(fav.key)}" data-field="${field}">${opts}</select></label>`;
  }

  function metaHtml(prof) {
    if (!prof.build) {
      return `<p class="fv-note">Aucun build méta trouvé en ligne pour ${esc(prof.species || 'cette espèce')} :
        plateau construit avec tous les gènes du jeu selon les règles (bingos, passives uniques, une active).</p>`;
    }
    const b = prof.build;
    const unknown = b.genes.filter(n => !gene(n));
    const sources = (b.sources || []).map((u, i) => `<a href="${esc(u)}" target="_blank" rel="noopener">source ${i + 1}</a>`).join(' · ');
    return `<p class="fv-note">${esc(b.intent || '')} ${sources ? `(${sources})` : ''}
      ${b.from_summaries ? '<br><span class="fv-warn">Build reconstitué à partir de résumés de recherche (page source inaccessible) : vérifie-le avec la source.</span>' : ''}
      ${b.unmapped && b.unmapped.length ? `<br><span class="meta">Non identifiés dans le catalogue : ${esc(b.unmapped.join(', '))}</span>` : ''}
      ${unknown.length ? `<br><span class="meta">Gènes hors catalogue Kiranico : ${esc(unknown.join(', '))}</span>` : ''}</p>`;
  }

  function renderFavs() {
    const container = document.getElementById('fav-list');
    document.getElementById('fav-count').textContent = favs.length;
    if (!favs.length) {
      container.innerHTML = '<p class="empty">Aucun favori : clique sur l\'étoile d\'un monstie dans l\'onglet « Tous les monsties ».</p>';
      return;
    }
    const doneNote = done.removed.length
      ? `<p class="fv-done-note">${done.removed.length} monstie${done.removed.length > 1 ? 's' : ''} sacrifié${done.removed.length > 1 ? 's' : ''}
          retiré${done.removed.length > 1 ? 's' : ''} du rapport depuis ce scan. <button class="fv-undo">Annuler</button></p>`
      : '';
    // Les favoris ne servent jamais de donneurs ; les donneurs du meilleur plan d'un favori sont réservés pour lui.
    const unavailable = new Set(favs.map(f => f.key));
    for (const id of Object.keys(plans)) delete plans[id];
    container.innerHTML = doneNote + favs.map((fav, fi) => {
      const m = BY_KEY[fav.key];
      if (!m) {
        return `<section class="fv-panel"><p class="alert">« ${esc(fav.key.split('|')[0])} » n'est plus dans ce scan.</p>
          <button class="fv-remove" data-key="${esc(fav.key)}">Retirer des favoris</button></section>`;
      }
      const prof = profile(fav, m);
      const opt = optimizedPlans(m, prof, unavailable);
      const best = opt.alternatives[0];
      best.donors.forEach(d => unavailable.add(d));
      const perfect = perfectBoard(prof);
      const speciesOptions = [{ value: '', label: 'Inconnue' }].concat(DATA.species.map(s => ({ value: s.name, label: s.name })));
      const buildSelect = prof.builds.length > 1
        ? select('Build', 'build', fav.build || 0, prof.builds.map((b, i) => ({ value: i, label: `Build ${i + 1}` })), fav) : '';
      const missingNote = opt.missing.length
        ? `<p class="fv-note">Absents de ton écurie : <b>${esc(opt.missing.map(short).join(', '))}</b>. Plateaux possibles ci-dessous.</p>` : '';
      const others = opt.alternatives.slice(1);
      const othersHtml = others.length
        ? `<details class="fv-others"><summary>${others.length} autre${others.length > 1 ? 's' : ''} possibilité${others.length > 1 ? 's' : ''}</summary>
            <div class="fv-alts">${others.map((alt, i) => boardHtml(`Possibilité ${i + 2}`, alt.board, prof, transfersHtml(alt, fav.key, `${fi}-${i + 1}`), true)).join('')}</div></details>`
        : '';
      return `<section class="fv-panel">
        <div class="fv-head">
          <img src="${esc(m.folder)}/tile.png" alt="">
          <div><div class="name">${esc(m.name || 'Nom illisible')}</div><div class="meta">#${m.index} · page ${m.page}, case ${m.row},${m.col}</div></div>
          <div class="fv-profile">
            ${select('Espèce', 'species', prof.species || '', speciesOptions, fav)}
            ${select('Type', 'type', prof.type, TYPES.map(t => ({ value: t, label: t })), fav)}
            ${select('Élément', 'element', prof.element, ELEMENTS.map(e => ({ value: e, label: e })), fav)}
            ${buildSelect}
          </div>
          <button class="fv-remove" data-key="${esc(fav.key)}">Retirer</button>
        </div>
        ${prof.elementGuessed ? '<p class="alert">Espèce inconnue (absente de Kiranico) : vérifie l\'élément choisi.</p>' : ''}
        <div class="fv-boards">
          ${boardHtml('Actuel', m.genes, prof)}
          ${boardHtml('Build méta (parfait)', perfect, prof, metaHtml(prof))}
          ${boardHtml(`Optimisé avec ton écurie (${best.transfers.length} transfert${best.transfers.length > 1 ? 's' : ''})`, best.board, prof,
            missingNote + transfersHtml(best, fav.key, `${fi}-0`) + othersHtml)}
        </div>
      </section>`;
    }).join('');
  }

  function refreshStars() {
    for (const btn of document.querySelectorAll('.star')) {
      const on = isFav(btn.dataset.key);
      btn.classList.toggle('on', on);
      btn.textContent = on ? '★' : '☆';
      btn.title = on ? 'Retirer des favoris' : 'Ajouter aux favoris';
    }
  }

  function markTransferred(id) {
    const entry = plans[id];
    if (!entry || !entry.plan.transfers.length) return;
    const m = BY_KEY[entry.favKey];
    const donors = entry.plan.transfers.map(t => t.donor);
    const list = donors.map(d => `• ${d.name || '?'} (page ${d.page}, case ${d.row},${d.col})`).join('\n');
    if (!confirm(`As-tu fait ces ${donors.length} transfert(s) vers ${m.name || '?'} ?\n\nCes monsties sacrifiés seront retirés du rapport :\n${list}`)) return;
    done.removed.push(...donors.map(d => d.key));
    done.boards[entry.favKey] = entry.plan.board;
    saveDone(); applyDone(); renderFavs();
  }

  document.addEventListener('click', e => {
    const star = e.target.closest('.star');
    if (star) { toggleFav(star.dataset.key); return; }
    const remove = e.target.closest('.fv-remove');
    if (remove) { toggleFav(remove.dataset.key); return; }
    const transferred = e.target.closest('.fv-done');
    if (transferred) { markTransferred(transferred.dataset.plan); return; }
    if (e.target.closest('.fv-undo')) {
      if (!confirm('Annuler les transferts enregistrés ? Les monsties sacrifiés réapparaîtront et les plateaux reviendront à ceux du scan.')) return;
      done = freshDone();
      saveDone(); applyDone(); renderFavs();
      return;
    }
    const tab = e.target.closest('[data-tab]');
    if (tab) {
      for (const t of document.querySelectorAll('[data-tab]')) t.classList.toggle('active', t === tab);
      document.getElementById('view-all').classList.toggle('hidden', tab.dataset.tab !== 'all');
      document.getElementById('view-favs').classList.toggle('hidden', tab.dataset.tab !== 'favs');
      try { localStorage.setItem(STORE + ':onglet', tab.dataset.tab); } catch { /* ignoré */ }
    }
  });
  document.addEventListener('change', e => {
    const sel = e.target.closest('.fv-profile select');
    if (!sel) return;
    const fav = favs.find(f => f.key === sel.dataset.key);
    if (!fav) return;
    const field = sel.dataset.field;
    fav[field] = field === 'build' ? Number(sel.value) : (sel.value || null);
    if (field === 'species') { delete fav.type; delete fav.element; delete fav.build; }  // repart des valeurs de l'espèce
    saveFavs(favs);
    renderFavs();
  });

  loadFavs().then(async list => {
    favs = list;
    done = await loadDone();
    applyDone();
    setStorageNote();
    refreshStars();
    renderFavs();
  });
  try {
    const tab = localStorage.getItem(STORE + ':onglet');
    if (tab) document.querySelector(`[data-tab="${tab}"]`)?.click();
  } catch { /* ignoré */ }
})();
