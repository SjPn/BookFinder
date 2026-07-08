const workId = decodeURIComponent(window.location.pathname.replace(/^\/work\//, ''));

const SIMILAR_MODE_LABELS = {
  ideas: 'По идеям',
  atmosphere: 'По атмосфере',
  emotions: 'По эмоциям',
  dynamics: 'По динамике',
  gameplay: 'По геймплею',
  style: 'По стилю',
  overall: 'Общее',
  legacy: 'По жанрам',
};

const AXIS_SIMILAR_MODE = {
  character_growth: 'gameplay',
  world_exploration: 'gameplay',
  politics: 'ideas',
  romance: 'emotions',
  humor: 'style',
  action: 'dynamics',
  brutality: 'atmosphere',
  science: 'ideas',
  magic: 'gameplay',
  survival: 'dynamics',
  construction: 'gameplay',
  thinking: 'ideas',
  philosophy: 'ideas',
  darkness: 'atmosphere',
  hope: 'emotions',
  psychology: 'emotions',
  worldbuilding: 'atmosphere',
  realism: 'style',
  pace: 'dynamics',
  difficulty: 'style',
  dialogues: 'style',
  plot_twists: 'dynamics',
};

let currentSimilarMode = 'auto';
let currentWork = null;
let currentDna = null;

async function saveUserRating(id, rating) {
  const userId = getUserId();
  return apiJson(`/api/works/${id}/user-rating`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, rating }),
  });
}

async function clearUserRating(id) {
  const userId = getUserId();
  return apiJson(`/api/works/${id}/user-rating?user_id=${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  });
}

function renderUserRating(id, data) {
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
        const saved = await saveUserRating(id, n);
        renderUserRating(id, saved);
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
      await clearUserRating(id);
      renderUserRating(id, { rating: null, community });
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

function renderBookActions(work) {
  const box = document.getElementById('d-actions');
  box.innerHTML = '';

  const favoriteBtn = document.createElement('button');
  favoriteBtn.type = 'button';
  favoriteBtn.className = 'book-action-btn';
  const syncFavorite = () => {
    const active = isFavoriteWork(work.id);
    favoriteBtn.classList.toggle('active', active);
    favoriteBtn.textContent = active ? '★ В списке' : '☆ В список';
    favoriteBtn.title = active ? 'Убрать из списка' : 'Добавить в список «Хочу прочитать»';
  };
  favoriteBtn.onclick = () => {
    toggleFavoriteWork(work.id);
    syncFavorite();
  };
  syncFavorite();

  const hideBtn = document.createElement('button');
  hideBtn.type = 'button';
  hideBtn.className = 'book-action-btn';
  const syncHidden = () => {
    const active = isHiddenWork(work.id);
    hideBtn.classList.toggle('active', active);
    hideBtn.textContent = active ? 'Скрыта' : 'Скрыть';
    hideBtn.title = active ? 'Показывать в похожих снова' : 'Не показывать в похожих';
  };
  hideBtn.onclick = async () => {
    toggleHiddenWork(work.id);
    syncHidden();
    await loadSimilarList(currentSimilarMode);
  };
  syncHidden();

  const shareBtn = document.createElement('button');
  shareBtn.type = 'button';
  shareBtn.className = 'book-action-btn';
  shareBtn.textContent = 'Поделиться';
  shareBtn.onclick = async () => {
    const url = window.location.href;
    const payload = { title: work.title, text: `${work.title} — ${(work.authors || []).join(', ')}`, url };
    try {
      if (navigator.share) {
        await navigator.share(payload);
      } else if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
        shareBtn.textContent = 'Ссылка скопирована';
        setTimeout(() => { shareBtn.textContent = 'Поделиться'; }, 1800);
      }
    } catch (err) {
      console.error(err);
    }
  };

  box.append(favoriteBtn, hideBtn, shareBtn);
}

function renderOverview(overview) {
  const panel = document.getElementById('d-overview-panel');
  const box = document.getElementById('d-overview');
  const paragraphs = (overview || []).filter(Boolean);
  if (!paragraphs.length) {
    panel.hidden = true;
    box.innerHTML = '';
    return;
  }
  panel.hidden = false;
  box.innerHTML = paragraphs.map((p) => `<p>${esc(p)}</p>`).join('');
}

function renderSources(w) {
  const el = document.getElementById('d-sources');
  const links = [];
  if (w.fantlab?.url) links.push(`<a href="${esc(w.fantlab.url)}" target="_blank" rel="noopener">FantLab</a>`);
  if (w.livelib?.url) links.push(`<a href="${esc(w.livelib.url)}" target="_blank" rel="noopener">LiveLib</a>`);
  if (w.fantasy_worlds?.url) links.push(`<a href="${esc(w.fantasy_worlds.url)}" target="_blank" rel="noopener">Fantasy-Worlds</a>`);
  if (w.kubikus?.url) links.push(`<a href="${esc(w.kubikus.url)}" target="_blank" rel="noopener">Кубикус</a>`);
  if (w.bookmix?.url) links.push(`<a href="${esc(w.bookmix.url)}" target="_blank" rel="noopener">BookMix</a>`);
  if (w.loveread?.url) links.push(`<a href="${esc(w.loveread.url)}" target="_blank" rel="noopener">LoveRead</a>`);
  el.innerHTML = links.length ? `Карточки: ${links.join(' · ')}` : '';
}

function renderRatingGrid(w) {
  const items = [
    { label: 'Сводный', value: formatAggregateRating(w.aggregate_rating), highlight: true },
    { label: 'FantLab', value: w.fantlab?.rating ?? '—' },
    { label: 'LiveLib', value: w.livelib?.rating ?? '—' },
    { label: 'FW', value: w.fantasy_worlds?.rating ?? '—' },
    { label: 'Кубикус', value: w.kubikus?.rating ?? '—' },
    { label: 'BookMix', value: w.bookmix?.rating ?? '—' },
    { label: 'LoveRead', value: w.loveread?.rating ?? '—' },
  ];
  return items.map((item) => {
    const val = typeof item.value === 'number' ? `${item.value}/10` : item.value;
    const cls = item.highlight ? 'rating-card highlight' : 'rating-card';
    return `<div class="${cls}"><span class="label">${esc(item.label)}</span><span class="value">${esc(String(val))}</span></div>`;
  }).join('');
}

function renderWorkCore(w) {
  currentWork = w;
  document.title = `${w.title} — Bookfinder`;
  document.getElementById('d-title').textContent = w.title;
  document.getElementById('d-authors').textContent = (w.authors || []).join(', ') || 'Автор не указан';
  renderBookActions(w);

  const descEl = document.getElementById('d-description');
  const descPanel = document.getElementById('d-description-panel');
  if (w.description) {
    const srcLabel = { fantasy_worlds: 'Fantasy-Worlds', fantlab: 'FantLab', livelib: 'LiveLib', bookmix: 'BookMix', kubikus: 'Кубикус' }[w.description_source] || w.description_source || '';
    descEl.classList.remove('muted');
    descEl.innerHTML = esc(w.description) + (srcLabel ? `<span class="desc-source">Источник: ${esc(srcLabel)}</span>` : '');
  } else {
    descPanel.classList.add('hidden');
    descEl.textContent = '';
  }

  document.getElementById('d-rating').innerHTML = renderRatingGrid(w);

  const dl = document.getElementById('d-downloads');
  const fwId = w.fantasy_worlds?.id;
  const links = [];
  if (fwId) {
    const localNote = w.fb2_local ? ' (файл в проекте)' : '';
    links.push(`<a class="download-btn" href="/api/download/fw/${esc(fwId)}" target="_blank" rel="noopener">Скачать FB2${localNote}</a>`);
  } else if (w.download_url) {
    links.push(`<a class="download-btn" href="${esc(w.download_url)}" target="_blank" rel="noopener">Скачать FB2</a>`);
  }
  dl.innerHTML = links.length ? links.join(' ') : '<span class="muted">Скачивание недоступно</span>';

  renderSources(w);

  const matches = w.genre_matches || {};
  const relParts = Object.entries(matches).map(([g, s]) => `${g}: ${Math.round(s * 100)}%`);
  const relevanceText = relParts.length
    ? `Совпадение фильтров: ${relParts.join(', ')}`
    : (w.relevance != null ? `Релевантность поиска: ${w.relevance}` : '');

  document.getElementById('d-relevance').innerHTML = relevanceText
    ? `${esc(relevanceText)}<br><span class="muted"><span class="hint-tip" tabindex="0" data-tip="Сводная оценка качества книги по FantLab, LiveLib, FW и другим источникам (шкала 0–10).">Рейтинг</span> — качество по данным источников. <span class="hint-tip" tabindex="0" data-tip="Число 0–100: насколько книга подходит под ваш поиск и фильтры жанров в каталоге.">Релевантность</span> — насколько книга подходит под ваш запрос.</span>`
    : '';

  document.getElementById('d-genres').innerHTML = (w.genres || []).length
    ? (w.genres || []).map((g) => `<span class="badge">${esc(g)}</span>`).join('')
    : '<span class="muted">Жанры не указаны</span>';

  document.getElementById('d-user-rating').innerHTML = '<p class="muted">Загрузка…</p>';
  document.getElementById('similar').innerHTML = '<li class="muted">Загрузка…</li>';
  document.getElementById('d-reviews').innerHTML = '<p class="muted">Загрузка…</p>';
}

function renderDnaAxes(axes, axisLabels, axisHints) {
  const entries = Object.entries(axes || {})
    .map(([key, value]) => ({
      key,
      label: (axisLabels && axisLabels[key]) || key,
      hint: (axisHints && axisHints[key]) || '',
      value: Number(value) || 0,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10);

  return entries.map((item) => {
    const width = Math.max(8, Math.round((item.value / 10) * 100));
    const hint = item.hint
      ? `<span class="hint-tip dna-axis-hint" tabindex="0" data-tip="${esc(item.hint)}">?</span>`
      : '';
    return `<div class="dna-axis" data-axis-key="${esc(item.key)}">
      <div class="dna-axis-head">
        <span>${esc(item.label)} ${hint}</span>
        <span>${item.value}/10</span>
      </div>
      <div class="dna-axis-bar"><span style="width:${width}%"></span></div>
    </div>`;
  }).join('');
}

function bindDnaAxisClicks() {
  const axesBox = document.getElementById('d-dna-axes');
  axesBox.querySelectorAll('.dna-axis[data-axis-key]').forEach((row) => {
    row.addEventListener('click', async (event) => {
      if (event.target.closest('.dna-axis-hint')) return;
      const axisKey = row.getAttribute('data-axis-key');
      const mode = AXIS_SIMILAR_MODE[axisKey];
      if (!mode || !currentDna?.modes?.includes(mode)) return;
      currentSimilarMode = mode;
      renderSimilarModes(currentDna.modes, mode);
      await loadSimilarList(mode);
      document.getElementById('similar')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

function renderDnaReviewsSummary(summary) {
  const praised = (summary?.praised || []).filter(Boolean);
  const criticized = (summary?.criticized || []).filter(Boolean);
  const emotions = (summary?.emotions || []).filter(Boolean);
  if (!praised.length && !criticized.length && !emotions.length) {
    return '';
  }
  const parts = [];
  if (praised.length) parts.push(`<p><strong>Хвалят:</strong> ${esc(praised.join(', '))}</p>`);
  if (criticized.length) parts.push(`<p><strong>Ругают:</strong> ${esc(criticized.join(', '))}</p>`);
  if (emotions.length) parts.push(`<p><strong>Эмоции:</strong> ${esc(emotions.join(', '))}</p>`);
  return `<div class="dna-reviews-box">${parts.join('')}</div>`;
}

function renderDnaBlock(dna) {
  const panel = document.getElementById('d-dna-panel');
  if (!dna || dna.error) {
    panel.hidden = true;
    currentDna = null;
    return;
  }

  currentDna = dna;
  panel.hidden = false;

  const badgeEl = document.getElementById('d-dna-badge');
  if (dna.reader_badge) {
    badgeEl.hidden = false;
    badgeEl.textContent = dna.reader_badge;
  } else {
    badgeEl.hidden = true;
    badgeEl.textContent = '';
  }

  document.getElementById('d-dna-tagline').textContent = dna.ai_tagline || '';
  const summaryEl = document.getElementById('d-dna-summary');
  if (dna.ai_summary) {
    summaryEl.classList.remove('muted');
    summaryEl.textContent = dna.ai_summary;
  } else {
    summaryEl.classList.add('muted');
    summaryEl.textContent = '';
  }

  document.getElementById('d-dna-axes').innerHTML = renderDnaAxes(dna.axes, dna.axis_labels, dna.axis_hints);
  bindDnaAxisClicks();
  document.getElementById('d-dna-themes').innerHTML = (dna.themes || []).length
    ? (dna.themes || []).map((theme) => `<span class="badge">${esc(theme)}</span>`).join('')
    : '';
  document.getElementById('d-dna-reviews-summary').innerHTML = renderDnaReviewsSummary(dna.reviews_summary);
  renderOverview(dna.ai_overview);
}

function renderSimilarModes(modes, activeMode) {
  const box = document.getElementById('similar-modes');
  const available = (modes || []).filter((mode) => mode !== 'overall');
  if (!available.length) {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }

  box.hidden = false;
  box.innerHTML = '';
  available.forEach((mode) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'similar-mode-btn';
    if (mode === activeMode) btn.classList.add('active');
    btn.textContent = SIMILAR_MODE_LABELS[mode] || mode;
    btn.onclick = async () => {
      currentSimilarMode = mode;
      renderSimilarModes(available, mode);
      await loadSimilarList(mode);
    };
    box.appendChild(btn);
  });
}

async function loadSimilarList(mode = currentSimilarMode) {
  const similarEl = document.getElementById('similar');
  similarEl.innerHTML = '<li class="muted">Загрузка…</li>';
  try {
    const query = mode && mode !== 'auto' ? `?mode=${encodeURIComponent(mode)}` : '';
    const sim = await apiJson(`/api/works/${workId}/similar${query}`);
    renderSimilarList(sim);
  } catch (err) {
    similarEl.innerHTML = '<li class="muted">Не удалось загрузить похожие книги</li>';
    console.error(err);
  }
}

function renderSimilarList(sim) {
  const similarEl = document.getElementById('similar');
  const items = filterHiddenWorks(sim);
  similarEl.innerHTML = '';
  if (!items.length) {
    similarEl.innerHTML = '<li class="muted">Похожих книг не найдено</li>';
    return;
  }
  items.forEach((s) => {
    const li = document.createElement('li');
    li.className = 'similar-item';
    const a = document.createElement('a');
    a.href = workUrl(s.id);
    const rating = s.aggregate_rating != null ? ` · ${formatAggregateRating(s.aggregate_rating)}` : '';
    const dnaScore = s.dna_score != null ? ` · ДНК ${Math.round(s.dna_score * 100)}%` : '';
    a.textContent = `${s.title} — ${(s.authors || []).join(', ')}${rating}${dnaScore}`;
    li.appendChild(a);

    const modeLabel = SIMILAR_MODE_LABELS[s.match_mode] || '';
    const matchBits = [];
    if (modeLabel) matchBits.push(modeLabel);
    (s.match_axes || []).forEach((label) => matchBits.push(label));
    if (matchBits.length) {
      const meta = document.createElement('div');
      meta.className = 'similar-match-tags';
      meta.innerHTML = matchBits.map((label) => `<span class="similar-match-tag">${esc(label)}</span>`).join('');
      li.appendChild(meta);
    }

    similarEl.appendChild(li);
  });
}

function renderReviewsBlock(rev) {
  const reviewsEl = document.getElementById('d-reviews');
  if (!rev.reviews?.length) {
    reviewsEl.innerHTML = '<p class="muted">Комментариев с FantLab, LiveLib и Fantasy-Worlds пока нет для этой книги.</p>';
    return;
  }
  reviewsEl.innerHTML = `<p class="reviews-count">Показано ${rev.reviews.length}${rev.count > rev.reviews.length ? ` из ${rev.count}` : ''}</p>` +
    rev.reviews.map((r) => {
      const src = { fantasy_worlds: 'FW', fantlab: 'FantLab', livelib: 'LiveLib', kubikus: 'Кубикус', bookmix: 'BookMix', loveread: 'LoveRead' }[r.source] || r.source;
      const author = r.author ? esc(r.author) : 'Аноним';
      const date = r.date ? ` · ${esc(r.date)}` : '';
      const link = r.url ? ` <a href="${esc(r.url)}" target="_blank" rel="noopener">источник</a>` : '';
      return `<article class="review-item">
        <div class="review-meta"><span class="review-source">${esc(src)}</span>${author}${date}${link}</div>
        <div class="review-text">${esc(r.text)}</div>
      </article>`;
    }).join('');
}

async function loadWorkExtras(w) {
  const userId = getUserId();
  const [ratingResult, dnaResult, similarResult, reviewsResult] = await Promise.allSettled([
    apiJson(`/api/works/${w.id}/user-rating?user_id=${encodeURIComponent(userId)}`),
    apiJson(`/api/works/${w.id}/dna`),
    apiJson(`/api/works/${w.id}/similar`),
    apiJson(`/api/works/${w.id}/reviews?limit=15`),
  ]);

  if (ratingResult.status === 'fulfilled') {
    renderUserRating(w.id, ratingResult.value);
  } else {
    document.getElementById('d-user-rating').innerHTML = '<p class="muted">Не удалось загрузить личную оценку</p>';
    console.error(ratingResult.reason);
  }

  if (dnaResult.status === 'fulfilled' && !dnaResult.value.error) {
    currentSimilarMode = 'ideas';
    renderDnaBlock(dnaResult.value);
    renderSimilarModes(dnaResult.value.modes || [], currentSimilarMode);
  } else {
    document.getElementById('d-dna-panel').hidden = true;
    document.getElementById('similar-modes').hidden = true;
    document.getElementById('d-overview-panel').hidden = true;
  }

  if (similarResult.status === 'fulfilled') {
    renderSimilarList(similarResult.value);
  } else {
    document.getElementById('similar').innerHTML = '<li class="muted">Не удалось загрузить похожие книги</li>';
    console.error(similarResult.reason);
  }

  if (reviewsResult.status === 'fulfilled') {
    renderReviewsBlock(reviewsResult.value);
  } else {
    document.getElementById('d-reviews').innerHTML = '<p class="muted">Не удалось загрузить отзывы</p>';
    console.error(reviewsResult.reason);
  }
}

function showError(message) {
  document.getElementById('d-title').textContent = 'Книга не найдена';
  document.getElementById('d-authors').textContent = message;
}

async function init() {
  if (!workId) {
    showError('Неверная ссылка');
    return;
  }
  try {
    const w = await apiJson(`/api/works/${workId}`);
    if (w.error) {
      showError('Такой книги нет в каталоге');
      return;
    }
    renderWorkCore(w);
    loadWorkExtras(w);
  } catch (err) {
    showError(err.message);
    console.error(err);
  }
}

init();
