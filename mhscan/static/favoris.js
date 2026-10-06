// Favoris et optimisation des gènes (MHS1, données Kiranico).
//
// Priorités, dans l'ordre (comparaison lexicographique) :
//   1. gènes du même élément et du même type d'attaque que le monstie (1 point pour chacun des deux) ;
//   2. famille de gène : Critical > Attack > Speed (puis L > M > S) ;
//   3. nombre de bingos (lignes de 3 gènes de même type d'attaque, ou de même élément) ;
//   4. à égalité, total des bonus utiles (Attack Up, attaque de l'élément du monstie, Crit Rate Up).
// Règles du jeu retenues : toutes les cases sont utilisables (les cases verrouillées se déverrouillent),
// tous les gènes du favori peuvent être remplacés, un donneur disparaît et ne donne donc qu'un seul gène,
// un seul gène par famille (S/M/L ne se cumulent pas), les autres favoris ne servent jamais de donneurs.
(() => {
  const DATA = JSON.parse(document.getElementById('mhscan-data').textContent);
  const CATALOG = DATA.catalog;
  const SPECIES = Object.fromEntries(DATA.species.map(s => [s.name, s]));
  const MONSTIES = DATA.monsties;
  const BY_KEY = Object.fromEntries(MONSTIES.map(m => [m.key, m]));
  const TYPES = ['Power', 'Speed', 'Technical'];
  const ELEMENTS = ['Fire', 'Water', 'Thunder', 'Ice', 'Dragon', 'Non-Elem'];
  const FAMILY_RANK = { 'Critical Gene': 3, 'Attack Gene': 2, 'Speed Gene': 1 };
  const SIZE_RANK = { L: 3, M: 2, S: 1 };
  const LINES = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8], [0, 4, 8], [2, 4, 6]];
  const STORE = `mhscan:${DATA.game}:favoris`;

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

  function toggleFav(key) {
    if (isFav(key)) favs = favs.filter(f => f.key !== key);
    else favs.push({ key });
    saveFavs(favs);
    refreshStars();
    renderFavs();
  }

  // --- profil du favori : type d'attaque et élément visés ------------------------------
  function profile(fav, m) {
    const species = 'species' in fav ? fav.species : (m.species || null);
    const known = species && SPECIES[species];
    return {
      species,
      type: fav.type || (known ? known.type : m.type) || 'Power',
      element: fav.element || (known ? known.element : null) || 'Non-Elem',
      elementGuessed: !fav.element && !known,
    };
  }

  // --- évaluation ---------------------------------------------------------------------------
  function geneScore(name, prof) {
    const g = CATALOG[name];
    if (!g) return { match: 0, family: 0, bonus: 0 };
    const match = (g.e === prof.element ? 1 : 0) + (g.t === prof.type ? 1 : 0);
    const family = FAMILY_RANK[g.f] ? FAMILY_RANK[g.f] * 10 + (SIZE_RANK[g.s] || 0) : 0;
    const useful = new Set(['Attack Up', 'Crit Rate Up', `${prof.element} Attack Up`]);
    const bonus = g.b.filter(b => useful.has(b[0])).reduce((sum, b) => sum + b[1], 0);
    return { match, family, bonus };
  }

  function bingos(board) {
    let count = 0;
    for (const line of LINES) {
      const genes = line.map(i => board[i] && CATALOG[board[i]]);
      if (genes.some(g => !g)) continue;
      if (genes[0].t !== 'No-type' && genes.every(g => g.t === genes[0].t)) count++;
      if (genes.every(g => g.e === genes[0].e)) count++;
    }
    return count;
  }

  function boardScore(board, prof) {
    const total = { match: 0, family: 0, bonus: 0 };
    for (const name of board) {
      if (!name) continue;
      const s = geneScore(name, prof);
      total.match += s.match; total.family += s.family; total.bonus += s.bonus;
    }
    total.bingos = bingos(board);
    return total;
  }

  // Place les gènes mobiles dans les cases libres pour maximiser les bingos (essai de toutes les dispositions).
  function bestPlacement(fixed, movable) {
    const free = fixed.map((g, i) => (g ? null : i)).filter(i => i !== null);
    const board = fixed.slice();
    if (!movable.length) return board;
    const classes = new Set(movable.map(n => { const g = CATALOG[n]; return g ? g.t + '/' + g.e : n; }));
    if (classes.size === 1) {  // tous équivalents pour les bingos : inutile de tout essayer
      movable.forEach((n, i) => { board[free[i]] = n; });
      return board;
    }
    let best = null, bestCount = -1;
    const used = new Array(free.length).fill(false);
    (function place(k) {
      if (k === movable.length) {
        const count = bingos(board);
        if (count > bestCount) { bestCount = count; best = board.slice(); }
        return;
      }
      for (let j = 0; j < free.length; j++) {
        if (used[j]) continue;
        used[j] = true; board[free[j]] = movable[k];
        place(k + 1);
        used[j] = false; board[free[j]] = null;
      }
    })(0);
    return best;
  }

  // Sélection gloutonne : à chaque étape, le meilleur gène restant selon les priorités ; à égalité, celui
  // qui partage le plus souvent son type/élément avec les gènes déjà choisis (favorise les bingos).
  function pickBest(candidates, chosen, prof, extraTieBreak) {
    const classCount = {};
    for (const c of chosen) {
      const g = CATALOG[c.name];
      if (g) { classCount['t' + g.t] = (classCount['t' + g.t] || 0) + 1; classCount['e' + g.e] = (classCount['e' + g.e] || 0) + 1; }
    }
    let best = null, bestKey = null;
    for (const c of candidates) {
      const s = geneScore(c.name, prof);
      const g = CATALOG[c.name];
      const affinity = g ? (g.t !== 'No-type' ? classCount['t' + g.t] || 0 : 0) + (classCount['e' + g.e] || 0) : 0;
      const key = [s.match, s.family, affinity, extraTieBreak(c), s.bonus];
      if (!bestKey || compare(key, bestKey) > 0) { best = c; bestKey = key; }
    }
    return best;
  }
  function compare(a, b) {
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i];
    return 0;
  }
  const familyOf = name => (CATALOG[name] ? CATALOG[name].f : name);

  function perfectPlan(prof) {
    let candidates = Object.keys(CATALOG).map(name => ({ name }));
    const chosen = [];
    while (chosen.length < 9 && candidates.length) {
      const c = pickBest(candidates, chosen, prof, () => 0);
      chosen.push(c);
      candidates = candidates.filter(x => familyOf(x.name) !== familyOf(c.name));
    }
    return bestPlacement(new Array(9).fill(null), chosen.map(c => c.name));
  }

  // Plan atteignable : gènes actuels du favori (gratuits, restent à leur place) ou gènes d'autres monsties
  // (un donneur = un gène, attribués par appariement pour qu'aucun donneur ne serve deux fois).
  function achievablePlan(m, prof, unavailable) {
    let candidates = [];
    m.genes.forEach((name, slot) => { if (name) candidates.push({ name, slot, own: true }); });
    const donorsByGene = {};
    for (const d of MONSTIES) {
      if (d.key === m.key || unavailable.has(d.key)) continue;
      for (const name of new Set(d.genes.filter(Boolean))) {
        (donorsByGene[name] = donorsByGene[name] || []).push(d.key);
      }
    }
    for (const name of Object.keys(donorsByGene)) candidates.push({ name, own: false });

    const chosen = [];
    const assignment = {};  // donneur -> gène
    const tryAssign = (gene, seen) => {
      for (const donor of donorsByGene[gene]) {
        if (seen.has(donor)) continue;
        seen.add(donor);
        if (!(donor in assignment) || tryAssign(assignment[donor], seen)) { assignment[donor] = gene; return true; }
      }
      return false;
    };
    while (chosen.length < 9 && candidates.length) {
      const c = pickBest(candidates, chosen, prof, x => (x.own ? 1 : 0));
      candidates = candidates.filter(x => x !== c);
      if (chosen.some(x => familyOf(x.name) === familyOf(c.name))) continue;
      if (!c.own && !tryAssign(c.name, new Set())) continue;
      chosen.push(c);
      candidates = candidates.filter(x => familyOf(x.name) !== familyOf(c.name));
    }
    const fixed = new Array(9).fill(null);
    chosen.filter(c => c.own).forEach(c => { fixed[c.slot] = c.name; });
    const moving = chosen.filter(c => !c.own).map(c => c.name);
    const board = bestPlacement(fixed, moving);
    const donorOf = Object.fromEntries(Object.entries(assignment).map(([donor, gene]) => [gene, donor]));
    const transfers = board
      .map((name, slot) => (name && !fixed[slot] ? { slot, name, donor: BY_KEY[donorOf[name]] } : null))
      .filter(Boolean);
    return { board, transfers, donors: Object.keys(assignment) };
  }

  // --- affichage ---------------------------------------------------------------------------
  const esc = s => String(s ?? '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
  const short = name => name.replace(/ Gene\b/, '');
  const cellCase = slot => `${Math.floor(slot / 3) + 1},${slot % 3 + 1}`;

  function boardHtml(title, board, prof, extra = '') {
    const s = boardScore(board, prof);
    const cells = board.map((name, i) => {
      if (!name) return '<div class="fv-cell fv-empty">—</div>';
      const g = CATALOG[name];
      const sc = geneScore(name, prof);
      const meta = g ? `${g.t} · ${g.e}` : 'inconnu';
      return `<div class="fv-cell fv-m${sc.match}" title="${esc(name)} — ${esc(meta)}${g ? ' — ' + esc(g.k) : ''}">`
        + `<span class="fv-dot fv-el-${g ? g.e.replace(/[^A-Za-z]/g, '') : 'x'}"></span>`
        + `<b>${esc(short(name))}</b><small>${esc(meta)}</small></div>`;
    }).join('');
    const filled = board.filter(Boolean).length;
    return `<div class="fv-board"><h4>${esc(title)}</h4><div class="fv-grid">${cells}</div>
      <p class="fv-score"><span title="1 point par gène du bon élément, 1 par gène du bon type">Correspondance ${s.match}/${filled * 2}</span>
      · <span>${s.bingos} bingo${s.bingos > 1 ? 's' : ''}</span>
      · <span title="Critical > Attack > Speed">Familles ${s.family}</span></p>${extra}</div>`;
  }

  function select(label, field, value, options, fav) {
    const opts = options.map(o => `<option value="${esc(o.value)}"${o.value === value ? ' selected' : ''}>${esc(o.label)}</option>`).join('');
    return `<label>${label}<select data-key="${esc(fav.key)}" data-field="${field}">${opts}</select></label>`;
  }

  function renderFavs() {
    const container = document.getElementById('fav-list');
    const counter = document.getElementById('fav-count');
    counter.textContent = favs.length;
    if (!favs.length) {
      container.innerHTML = '<p class="empty">Aucun favori : clique sur l\'étoile d\'un monstie dans l\'onglet « Tous les monsties ».</p>';
      return;
    }
    // Les favoris ne servent jamais de donneurs ; les donneurs d'un favori ne sont pas réutilisés pour les suivants.
    const unavailable = new Set(favs.map(f => f.key));
    container.innerHTML = favs.map(fav => {
      const m = BY_KEY[fav.key];
      if (!m) {
        return `<section class="fv-panel"><p class="alert">« ${esc(fav.key.split('|')[0])} » n'est plus dans ce scan.</p>
          <button class="fv-remove" data-key="${esc(fav.key)}">Retirer des favoris</button></section>`;
      }
      const prof = profile(fav, m);
      const reach = achievablePlan(m, prof, unavailable);
      reach.donors.forEach(d => unavailable.add(d));
      const perfect = perfectPlan(prof);
      const speciesOptions = [{ value: '', label: 'Inconnue' }].concat(DATA.species.map(s => ({ value: s.name, label: s.name })));
      const transfers = reach.transfers.length
        ? `<ol class="fv-transfers">${reach.transfers.map(t => `<li>Case ${cellCase(t.slot)} : <b>${esc(t.name)}</b> ← ${esc(t.donor.name || '?')}
            <span class="meta">(page ${t.donor.page}, case ${t.donor.row},${t.donor.col}) — sacrifié</span></li>`).join('')}</ol>`
        : '<p class="meta">Aucun transfert utile : le plateau actuel est déjà le meilleur possible avec ton écurie.</p>';
      return `<section class="fv-panel">
        <div class="fv-head">
          <img src="${esc(m.folder)}/tile.png" alt="">
          <div><div class="name">${esc(m.name || 'Nom illisible')}</div><div class="meta">#${m.index} · page ${m.page}, case ${m.row},${m.col}</div></div>
          <div class="fv-profile">
            ${select('Espèce', 'species', prof.species || '', speciesOptions, fav)}
            ${select('Type', 'type', prof.type, TYPES.map(t => ({ value: t, label: t })), fav)}
            ${select('Élément', 'element', prof.element, ELEMENTS.map(e => ({ value: e, label: e })), fav)}
          </div>
          <button class="fv-remove" data-key="${esc(fav.key)}">Retirer</button>
        </div>
        ${prof.elementGuessed ? '<p class="alert">Espèce inconnue (absente de Kiranico) : vérifie l\'élément choisi.</p>' : ''}
        <div class="fv-boards">
          ${boardHtml('Actuel', m.genes, prof)}
          ${boardHtml(`Atteignable avec ton écurie (${reach.transfers.length} transfert${reach.transfers.length > 1 ? 's' : ''})`, reach.board, prof, transfers)}
          ${boardHtml('Parfait (tous les gènes du jeu)', perfect, prof)}
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

  document.addEventListener('click', e => {
    const star = e.target.closest('.star');
    if (star) { toggleFav(star.dataset.key); return; }
    const remove = e.target.closest('.fv-remove');
    if (remove) { toggleFav(remove.dataset.key); return; }
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
    fav[sel.dataset.field] = sel.value || null;
    if (sel.dataset.field === 'species') { delete fav.type; delete fav.element; }  // repart des valeurs de l'espèce
    saveFavs(favs);
    renderFavs();
  });

  loadFavs().then(list => {
    favs = list;
    setStorageNote();
    refreshStars();
    renderFavs();
  });
  try {
    const tab = localStorage.getItem(STORE + ':onglet');
    if (tab) document.querySelector(`[data-tab="${tab}"]`)?.click();
  } catch { /* ignoré */ }
})();
