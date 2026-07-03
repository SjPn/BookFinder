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
let currentWorkId = null;

const USER_ID_KEY = 'bookfinder_user_id';

function getUserId() {
  let id = localStorage.getItem(USER_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(USER_ID_KEY, id);
  }
  return id;
}

async function apiJson(url, options) {
  const r = await fetch(url, options);
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

function formatAggregateRating(value) {
  return value == null ? '—' : value;
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
      <td>${formatAggregateRating(w.aggregate_rating)}</td>
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

async function saveUserRating(workId, rating) {
  const userId = getUserId();
  return apiJson(`/api/works/${workId}/user-rating`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, rating }),
  });
}

async function clearUserRating(workId) {
  const userId = getUserId();
  return apiJson(`/api/works/${workId}/user-rating?user_id=${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  });
}

function renderUserRating(workId, data) {
  const box = document.getElementById('d-user-rating');
  const current = data?.rating ?? null;
  const community = data?.community || {};

  const stars = document.createElement('div');
  stars.className = 'rating-stars';

  for (let n = 1; n <= 10; n += 1) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = String(n);
    btn.title = `Моя оценка: ${n}/10`;
    if (current === n) btn.classList.add('active');
    btn.onclick = async () => {
      try {
        const saved = await saveUserRating(workId, n);
        renderUserRating(workId, saved);
      } catch (err) {
        console.error(err);
      }
    };
    stars.appendChild(btn);
  }

  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'clear';
  clearBtn.textContent = 'Сбросить';
  clearBtn.onclick = async () => {
    try {
      await clearUserRating(workId);
      renderUserRating(workId, { rating: null, community: community });
    } catch (err) {
      console.error(err);
    }
  };
  stars.appendChild(clearBtn);

  const meta = document.createElement('p');
  meta.className = 'user-rating-meta';
  const mine = current != null ? `Ваша оценка: ${current}/10` : 'Вы ещё не оценивали эту книгу';
  const comm = community.count
    ? `Средняя читателей портала: ${community.average}/10 (${community.count})`
    : 'Пока нет оценок других читателей';
  meta.textContent = `${mine}. ${comm}.`;

  box.innerHTML = '<label>Ваша личная оценка (1–10)</label>';
  box.appendChild(stars);
  box.appendChild(meta);
}

async function showDetail(w) {
  if (typeof w === 'string') {
    w = await apiJson(`/api/works/${w}`);
  }
  if (w.error) return;

  currentWorkId = w.id;
  detail.classList.remove('hidden');
  document.getElementById('d-title').textContent = w.title;
  document.getElementById('d-authors').textContent = (w.authors || []).join(', ');
  document.getElementById('d-rating').textContent =
    `Рейтинг каталога: ${formatAggregateRating(w.aggregate_rating)} | FantLab: ${w.fantlab?.rating ?? '—'} | LiveLib: ${w.livelib?.rating ?? '—'} | FW: ${w.fantasy_worlds?.rating ?? '—'}`;

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
  const relevanceText = relParts.length
    ? `Совпадение фильтров: ${relParts.join(', ')}`
    : (w.relevance != null ? `Релевантность поиска: ${w.relevance}` : 'Релевантность не рассчитана (нет активного поиска)');

  document.getElementById('d-relevance').innerHTML =
    `${esc(relevanceText)}<br><span class="muted">Рейтинг — качество книги по данным FantLab/LiveLib/FW. Релевантность — насколько книга подходит под ваш запрос и выбранные жанры.</span>`;

  document.getElementById('d-genres').innerHTML = (w.genres || [])
    .map((g) => `<span class="badge">${esc(g)}</span>`)
    .join('');

  try {
    const userId = getUserId();
    const ratingData = await apiJson(
      `/api/works/${w.id}/user-rating?user_id=${encodeURIComponent(userId)}`,
    );
    renderUserRating(w.id, ratingData);
  } catch (err) {
    document.getElementById('d-user-rating').innerHTML = '<p class="muted">Не удалось загрузить личную оценку</p>';
    console.error(err);
  }

  const sim = await apiJson(`/api/works/${w.id}/similar`);
  const similarEl = document.getElementById('similar');
  similarEl.innerHTML = '';
  if (!sim.length) {
    similarEl.innerHTML = '<li class="muted">Похожих книг не найдено</li>';
  } else {
    sim.forEach((s) => {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'similar-link';
      const rating = s.aggregate_rating != null ? ` · ${s.aggregate_rating}` : '';
      btn.textContent = `${s.title} — ${(s.authors || []).join(', ')}${rating}`;
      btn.onclick = () => showDetail(s.id);
      li.appendChild(btn);
      similarEl.appendChild(li);
    });
  }

  const reviewsEl = document.getElementById('d-reviews');
  try {
    const rev = await apiJson(`/api/works/${w.id}/reviews?limit=10`);
    if (!rev.reviews?.length) {
      reviewsEl.innerHTML = '<p class="muted">Отзывов с сайтов пока нет (ничего не выдумываем).</p>';
    } else {
      reviewsEl.innerHTML = rev.reviews.map((r) => {
        const src = { fantasy_worlds: 'FW', fantlab: 'FantLab', livelib: 'LiveLib' }[r.source] || r.source;
        const author = r.author ? esc(r.author) : 'Аноним';
        const date = r.date ? ` · ${esc(r.date)}` : '';
        const link = r.url ? ` <a href="${esc(r.url)}" target="_blank" rel="noopener">источник</a>` : '';
        return `<article class="review-item">
          <div class="review-meta"><span class="review-source">${esc(src)}</span>${author}${date}${link}</div>
          <div class="review-text">${esc(r.text)}</div>
        </article>`;
      }).join('');
    }
  } catch (err) {
    reviewsEl.innerHTML = '<p class="muted">Не удалось загрузить отзывы</p>';
    console.error(err);
  }

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
