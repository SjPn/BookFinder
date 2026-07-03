const tbody = document.querySelector('#table tbody');
const statsEl = document.getElementById('stats');
const queryEl = document.getElementById('query');
const genreFilterEl = document.getElementById('genre-filter');
const genreListEl = document.getElementById('genre-list');
const filterWeightsEl = document.getElementById('filter-weights');
const resultMetaEl = document.getElementById('result-meta');

const ASSET_V = '20260703';

let allGenres = [];
let searchTimer = null;

function selectedGenres() {
  return [...genreListEl.querySelectorAll('input[type=checkbox]:checked')].map((el) => el.value);
}

function matchMode() {
  return document.querySelector('input[name=match]:checked')?.value || 'any';
}

function applyCatalogState(state) {
  if (!state) return;
  queryEl.value = state.q || '';
  for (const el of document.querySelectorAll('input[name=match]')) {
    el.checked = el.value === (state.match || 'any');
  }
  const selected = new Set(state.genres || []);
  for (const input of genreListEl.querySelectorAll('input[type=checkbox]')) {
    input.checked = selected.has(input.value);
  }
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

function openWork(workId) {
  saveCatalogState();
  window.location.assign(workUrl(workId));
}

async function loadStats() {
  const s = await apiJson('/api/stats');
  const m = s.merge || {};
  statsEl.textContent = `Книг: ${s.works_count} | Жанров: ${s.genres_count} | Склейка LL: ${m.match_rate_on_cached_percent ?? '—'}% | FW: ${m.fw_matched ?? '—'}`;
}

async function loadGenres() {
  allGenres = await apiJson('/api/genres');
  renderGenres();
  applyCatalogState(restoreCatalogState());
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
    tr.dataset.workId = w.id;
    const href = workUrl(w.id);
    const sources = [w.fantlab ? 'FL' : null, w.livelib ? 'LL' : null, w.fantasy_worlds ? 'FW' : null, w.kubikus ? 'KB' : null, w.bookmix ? 'BM' : null]
      .filter(Boolean)
      .join('+');
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td><a class="row-link" href="${href}">${esc(w.title)}</a></td>
      <td>${esc((w.authors || []).join(', '))}</td>
      <td>${formatAggregateRating(w.aggregate_rating)}</td>
      <td>${w.relevance ?? '—'}</td>
      <td>${sources || '—'}</td>
      <td class="genre-cell">${formatGenreMatches(w)}</td>
      <td><a class="link" href="${href}" aria-label="Открыть">→</a></td>
    `;
    tbody.appendChild(tr);
  });
}

tbody.addEventListener('click', (e) => {
  const tr = e.target.closest('tr');
  if (!tr?.dataset.workId) return;
  if (e.target.closest('a')) return;
  e.preventDefault();
  openWork(tr.dataset.workId);
});

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
