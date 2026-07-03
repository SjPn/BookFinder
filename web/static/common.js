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

function formatAggregateRating(value) {
  return value == null ? '—' : value;
}

function saveCatalogState() {
  const queryEl = document.getElementById('query');
  const genreListEl = document.getElementById('genre-list');
  if (!queryEl || !genreListEl) return;
  const state = {
    q: queryEl.value.trim(),
    match: document.querySelector('input[name=match]:checked')?.value || 'any',
    genres: [...genreListEl.querySelectorAll('input[type=checkbox]:checked')].map((el) => el.value),
  };
  sessionStorage.setItem('bookfinder_catalog_state', JSON.stringify(state));
}

function restoreCatalogState() {
  const raw = sessionStorage.getItem('bookfinder_catalog_state');
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function workUrl(workId) {
  return `/work/${encodeURIComponent(workId)}`;
}

function navigateToWork(workId) {
  saveCatalogState();
  window.location.href = workUrl(workId);
}
