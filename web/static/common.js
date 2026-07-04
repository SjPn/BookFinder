const USER_ID_KEY = 'bookfinder_user_id';
const THEME_KEY = 'bookfinder_theme';

function getTheme() {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_KEY, theme);
  syncThemeToggle();
}

function toggleTheme() {
  setTheme(getTheme() === 'dark' ? 'light' : 'dark');
}

function syncThemeToggle() {
  const dark = getTheme() === 'dark';
  for (const btn of document.querySelectorAll('[data-theme-toggle]')) {
    btn.textContent = dark ? '☀' : '🌙';
    btn.setAttribute('aria-label', dark ? 'Включить светлую тему' : 'Включить тёмную тему');
    btn.title = dark ? 'Светлая тема' : 'Тёмная тема';
  }
}

function initThemeToggle() {
  syncThemeToggle();
  for (const btn of document.querySelectorAll('[data-theme-toggle]')) {
    btn.addEventListener('click', toggleTheme);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initThemeToggle);
} else {
  initThemeToggle();
}

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
  if (value == null) return '—';
  const n = Number(value);
  if (Number.isNaN(n)) return '—';
  const scaled = n > 10 ? n / 10 : n;
  return `${scaled.toFixed(1)}/10`;
}

function formatCommunityRating(stats) {
  if (!stats?.count) return '—';
  return `${Number(stats.average).toFixed(1)}/10 (${stats.count})`;
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
