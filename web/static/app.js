const tbody = document.querySelector('#table tbody');
const statsEl = document.getElementById('stats');
const detail = document.getElementById('detail');
const queryEl = document.getElementById('query');
const genreFilterEl = document.getElementById('genre-filter');
const genreListEl = document.getElementById('genre-list');
const filterWeightsEl = document.getElementById('filter-weights');
const resultMetaEl = document.getElementById('result-meta');

let allGenres = [];
let searchTimer = null;

async function apiJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
}

function selectedGenres() {
  return [...genreListEl.querySelectorAll('input[type=checkbox]:checked')].map((el) => el.value);
}

function matchMode() {
  return document.querySelector('input[name=match]:checked')?.value || 'any';
}

function renderGenres(filterText = '') {
  const needle = filterText.trim().toLowerCase();
  genreListEl.innerHTML = '';
  const filtered = allGenres.filter((g) => !needle || g.name.toLowerCase().includes(needle));

  for (const g of filtered) {
    const label = document.createElement('label');
    label.className = 'genre-item';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = g.name;
    input.addEventListener('change', () => runSearch());
    const name = document.createElement('span');
    name.className = 'genre-name';
    name.textContent = g.name;
    const meta = document.createElement('span');
    meta.className = 'genre-meta';
    meta.textContent = `${g.count} · ${(g.weight * 100).toFixed(1)}%`;
    label.append(input, name, meta);
    genreListEl.appendChild(label);
  }

  if (!filtered.length) {
    genreListEl.innerHTML = '<p class="muted">Жанры не найдены</p>';
  }
}

function renderFilterWeights(filters, total) {
  if (!filters.length) {
    filterWeightsEl.classList.add('hidden');
    filterWeightsEl.innerHTML = '';
    return;
  }

  filterWeightsEl.classList.remove('hidden');
  const rows = filters.map((f) => {
    const catalogPct = (f.catalog_weight * 100).toFixed(1);
    const resultPct = total ? ((f.results_count / total) * 100).toFixed(0) : '0';
    return `<li>
      <strong>${esc(f.name)}</strong>
      <span>в каталоге: ${f.catalog_count} (${catalogPct}%)</span>
      <span>в выдаче: ${f.results_count} (${resultPct}%)</span>
    </li>`;
  }).join('');

  filterWeightsEl.innerHTML = `<h3>Веса фильтров</h3><ul>${rows}</ul>`;
}

function formatGenreMatches(work) {
  const matches = work.genre_matches || {};
  const keys = Object.keys(matches);
  if (!keys.length) {
    return (work.genres || []).slice(0, 2).map((g) => esc(g)).join(', ');
  }
  return keys
    .map((g) => `${esc(g)} (${Math.round(matches[g] * 100)}%)`)
    .join(', ');
}

async function loadStats() {
  const s = await apiJson('/api/stats');
  const m = s.merge || {};
  statsEl.textContent = `Книг: ${s.works_count} | Жанров: ${s.genres_count} | Склейка LL: ${m.match_rate_on_cached_percent ?? '—'}% | FW: ${m.fw_matched ?? '—'}`;
}

async function loadGenres() {
  allGenres = await apiJson('/api/genres');
  renderGenres();
}

function buildSearchUrl() {
  const params = new URLSearchParams();
  const q = queryEl.value.trim();
  if (q) params.set('q', q);
  params.set('match', matchMode());
  params.set('limit', '200');
  for (const genre of selectedGenres()) {
    params.append('genres', genre);
  }
  return `/api/search?${params.toString()}`;
}

async function runSearch() {
  const data = await apiJson(buildSearchUrl());
  const rows = data.items || [];
  resultMetaEl.textContent = `Найдено: ${data.total}${rows.length < data.total ? `, показано ${rows.length}` : ''}`;
  renderFilterWeights(data.filters || [], data.total || 0);

  tbody.innerHTML = '';
  rows.forEach((w, i) => {
    const tr = document.createElement('tr');
    const sources = [w.fantlab ? 'FL' : null, w.livelib ? 'LL' : null, w.fantasy_worlds ? 'FW' : null]
      .filter(Boolean)
      .join('+');
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>${esc(w.title)}</td>
      <td>${esc((w.authors || []).join(', '))}</td>
      <td>${w.aggregate_rating}</td>
      <td>${w.relevance ?? '—'}</td>
      <td>${sources || '—'}</td>
      <td class="genre-cell">${formatGenreMatches(w)}</td>
      <td><button class="link" data-id="${w.id}">→</button></td>
    `;
    tr.querySelector('button').onclick = (e) => {
      e.stopPropagation();
      showDetail(w);
    };
    tr.onclick = () => showDetail(w);
    tbody.appendChild(tr);
  });
}

async function showDetail(w) {
  if (typeof w === 'string') {
    w = await apiJson(`/api/works/${w}`);
  }
  if (w.error) return;

  detail.classList.remove('hidden');
  document.getElementById('d-title').textContent = w.title;
  document.getElementById('d-authors').textContent = (w.authors || []).join(', ');
  document.getElementById('d-rating').textContent =
    `Рейтинг: ${w.aggregate_rating} | FantLab: ${w.fantlab?.rating ?? '—'} | LiveLib: ${w.livelib?.rating ?? '—'} | FW: ${w.fantasy_worlds?.rating ?? '—'}`;

  const dl = document.getElementById('d-downloads');
  const fwId = w.fantasy_worlds?.id;
  const links = [];
  if (fwId) {
    const localNote = w.fb2_local ? ' (файл в проекте)' : '';
    links.push(`<a href="/api/download/fw/${fwId}" target="_blank" rel="noopener">Скачать FB2${localNote}</a>`);
    if (w.fantasy_worlds?.url) {
      links.push(`<a href="${esc(w.fantasy_worlds.url)}" target="_blank" rel="noopener">Карточка FW</a>`);
    }
  } else if (w.download_url) {
    links.push(`<a href="${esc(w.download_url)}" target="_blank" rel="noopener">Скачать FB2</a>`);
  }
  dl.innerHTML = links.length ? links.join(' · ') : 'Скачивание недоступно';

  const matches = w.genre_matches || {};
  const relParts = Object.entries(matches).map(([g, s]) => `${g}: ${Math.round(s * 100)}%`);
  document.getElementById('d-relevance').textContent = relParts.length
    ? `Совпадение фильтров: ${relParts.join(', ')}`
    : `Релевантность: ${w.relevance ?? '—'}`;

  document.getElementById('d-genres').innerHTML = (w.genres || [])
    .map((g) => `<span class="badge">${esc(g)}</span>`)
    .join('');

  const sim = await apiJson(`/api/works/${w.id}/similar`);
  document.getElementById('similar').innerHTML = sim
    .map((s) => `<li>${esc(s.title)} — ${esc((s.authors || []).join(', '))} (${s.aggregate_rating})</li>`)
    .join('');
  detail.scrollIntoView({ behavior: 'smooth' });
}

function scheduleSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    runSearch().catch((err) => {
      resultMetaEl.textContent = `Ошибка: ${err.message}`;
      console.error(err);
    });
  }, 250);
}

queryEl.addEventListener('input', scheduleSearch);
genreFilterEl.addEventListener('input', () => renderGenres(genreFilterEl.value));
for (const el of document.querySelectorAll('input[name=match]')) {
  el.addEventListener('change', scheduleSearch);
}

async function init() {
  try {
    await Promise.all([loadGenres(), loadStats()]);
    await runSearch();
  } catch (err) {
    statsEl.textContent = `Ошибка загрузки: ${err.message}`;
    console.error(err);
  }
}

init();
