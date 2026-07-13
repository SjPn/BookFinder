const tbody = document.querySelector('#table tbody');
const resultsCardsEl = document.getElementById('results-cards');
const statsEl = document.getElementById('stats');
const queryEl = document.getElementById('query');
const genreFilterEl = document.getElementById('genre-filter');
const genreListEl = document.getElementById('genre-list');
const filterWeightsEl = document.getElementById('filter-weights');
const resultMetaEl = document.getElementById('result-meta');
const filtersSidebar = document.getElementById('filters-sidebar');
const filtersBackdrop = document.getElementById('filters-backdrop');
const filtersCountEl = document.getElementById('filters-count');

let searchLimit = 200;
let lastSearchTotal = 0;
let searchSeq = 0;

let allGenres = [];
let searchTimer = null;

function selectedGenres() {
  return [...genreListEl.querySelectorAll('input[type=checkbox]:checked')].map((el) => el.value);
}

function updateFiltersCount() {
  const n = selectedGenres().length;
  if (!filtersCountEl) return;
  if (n > 0) {
    filtersCountEl.hidden = false;
    filtersCountEl.textContent = String(n);
  } else {
    filtersCountEl.hidden = true;
    filtersCountEl.textContent = '';
  }
}

function openFilters() {
  document.body.classList.add('is-filters-drawer-open');
  if (filtersBackdrop) filtersBackdrop.hidden = false;
  filtersSidebar?.setAttribute('aria-hidden', 'false');
}

function closeFilters() {
  document.body.classList.remove('is-filters-drawer-open');
  if (filtersBackdrop) filtersBackdrop.hidden = true;
  filtersSidebar?.setAttribute('aria-hidden', 'true');
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
  const filtered = allGenres
    .filter((g) => !needle || g.name.toLowerCase().includes(needle))
    .sort((a, b) => a.name.localeCompare(b.name, 'ru'));

  for (const g of filtered) {
    const label = document.createElement('label');
    label.className = 'genre-item';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = g.name;
    input.addEventListener('change', () => {
      updateFiltersCount();
      scheduleSearch();
    });
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

function formatRatingPill(value) {
  const text = formatAggregateRating(value);
  if (text === '—') return text;
  const num = parseFloat(text);
  const high = !Number.isNaN(num) && num >= 7.5 ? ' high' : '';
  return `<span class="rating-pill${high}">${text}</span>`;
}

async function loadStats() {
  const s = await apiJson('/api/stats');
  const m = s.merge || {};
  statsEl.innerHTML = `
    <span class="stat-chip accent"><strong>${s.works_count?.toLocaleString('ru-RU') ?? '—'}</strong> книг</span>
    <span class="stat-chip"><strong>${s.genres_count?.toLocaleString('ru-RU') ?? '—'}</strong> жанров</span>
    <span class="stat-chip"><strong>${m.match_rate_on_cached_percent ?? '—'}%</strong> LL</span>
    <span class="stat-chip"><strong>${m.fw_matched ?? '—'}</strong> FW</span>
  `;
}

async function loadGenres() {
  allGenres = await apiJson('/api/genres');
  renderGenres();
  applyCatalogState(restoreCatalogState());
}

function buildSearchUrl(limit = searchLimit) {
  const params = new URLSearchParams();
  const q = queryEl.value.trim();
  if (q) params.set('q', q);
  params.set('match', matchMode());
  params.set('limit', String(limit));
  for (const genre of selectedGenres()) {
    params.append('genres', genre);
  }
  return `/api/search?${params.toString()}`;
}

function formatResultMeta(data, rows) {
  const selected = selectedGenres();
  let meta = `Найдено: ${data.total ?? 0}`;
  if (rows.length < data.total) {
    meta += `, показано ${rows.length}`;
  }
  if (selected.length) {
    meta += ` · фильтр: ${selected.length} жанр(ов)`;
  }
  return meta;
}

async function runSearch(resetLimit = true) {
  if (resetLimit) searchLimit = 200;
  const seq = ++searchSeq;
  resultMetaEl.textContent = 'Поиск…';
  resultMetaEl.classList.add('loading');
  const data = await apiJson(buildSearchUrl());
  if (seq !== searchSeq) return;
  resultMetaEl.classList.remove('loading');
  const rows = data.items || [];
  lastSearchTotal = data.total || 0;
  resultMetaEl.textContent = formatResultMeta(data, rows);
  const loadMoreRow = document.getElementById('load-more-row');
  const loadMoreBtn = document.getElementById('load-more');
  if (loadMoreRow && loadMoreBtn) {
    if (rows.length < data.total) {
      loadMoreRow.classList.remove('hidden');
      loadMoreBtn.textContent = `Показать ещё (${Math.min(200, data.total - rows.length)} из ${data.total - rows.length})`;
    } else {
      loadMoreRow.classList.add('hidden');
    }
  }
  renderFilterWeights(data.filters || [], data.total || 0);
  updateFiltersCount();

  tbody.innerHTML = '';
  if (resultsCardsEl) resultsCardsEl.innerHTML = '';

  rows.forEach((w, i) => {
    const href = workUrl(w.id);
    const authors = esc((w.authors || []).join(', '));
    const genres = formatGenreMatches(w);

    const tr = document.createElement('tr');
    tr.dataset.workId = w.id;
    tr.innerHTML = `
      <td class="col-num">${i + 1}</td>
      <td class="col-title"><a class="row-link" href="${href}">${esc(w.title)}</a></td>
      <td class="col-author">${authors}</td>
      <td class="col-rating">${formatRatingPill(w.aggregate_rating)}</td>
      <td class="col-genres genre-cell">${genres}</td>
      <td class="col-go"><a class="link" href="${href}" aria-label="Открыть">→</a></td>
    `;
    tbody.appendChild(tr);

    if (resultsCardsEl) {
      const card = document.createElement('a');
      card.className = 'book-card';
      card.href = href;
      card.dataset.workId = w.id;
      card.innerHTML = `
        <div class="book-card-top">
          <span class="book-card-index">${i + 1}</span>
          ${formatRatingPill(w.aggregate_rating)}
        </div>
        <h3 class="book-card-title">${esc(w.title)}</h3>
        <p class="book-card-authors">${authors || 'Автор не указан'}</p>
        <div class="book-card-meta">
          <span class="book-card-genres">${genres}</span>
        </div>
      `;
      resultsCardsEl.appendChild(card);
    }
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
    runSearch(true).catch((err) => {
      resultMetaEl.textContent = `Ошибка: ${err.message}`;
      console.error(err);
    });
  }, 250);
}

document.getElementById('load-more')?.addEventListener('click', async () => {
  searchLimit = Math.min(searchLimit + 200, lastSearchTotal, 1000);
  try {
    await runSearch(false);
  } catch (err) {
    resultMetaEl.textContent = `Ошибка: ${err.message}`;
    console.error(err);
  }
});

document.getElementById('clear-genres')?.addEventListener('click', () => {
  for (const input of genreListEl.querySelectorAll('input[type=checkbox]:checked')) {
    input.checked = false;
  }
  updateFiltersCount();
  scheduleSearch();
});

document.getElementById('filters-open')?.addEventListener('click', openFilters);
document.getElementById('filters-close')?.addEventListener('click', closeFilters);
filtersBackdrop?.addEventListener('click', closeFilters);
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeFilters();
});

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
    statsEl.innerHTML = `<span class="stat-chip">Ошибка: ${esc(err.message)}</span>`;
    console.error(err);
  }
}

init();
