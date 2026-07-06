const workId = decodeURIComponent(window.location.pathname.replace(/^\/work\//, ''));

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
  document.title = `${w.title} — Bookfinder`;
  document.getElementById('d-title').textContent = w.title;
  document.getElementById('d-authors').textContent = (w.authors || []).join(', ') || 'Автор не указан';

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

function renderSimilarList(sim) {
  const similarEl = document.getElementById('similar');
  similarEl.innerHTML = '';
  if (!sim.length) {
    similarEl.innerHTML = '<li class="muted">Похожих книг не найдено</li>';
    return;
  }
  sim.forEach((s) => {
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.href = workUrl(s.id);
    const rating = s.aggregate_rating != null ? ` · ${formatAggregateRating(s.aggregate_rating)}` : '';
    a.textContent = `${s.title} — ${(s.authors || []).join(', ')}${rating}`;
    li.appendChild(a);
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
  const [ratingResult, similarResult, reviewsResult] = await Promise.allSettled([
    apiJson(`/api/works/${w.id}/user-rating?user_id=${encodeURIComponent(userId)}`),
    apiJson(`/api/works/${w.id}/similar`),
    apiJson(`/api/works/${w.id}/reviews?limit=15`),
  ]);

  if (ratingResult.status === 'fulfilled') {
    renderUserRating(w.id, ratingResult.value);
  } else {
    document.getElementById('d-user-rating').innerHTML = '<p class="muted">Не удалось загрузить личную оценку</p>';
    console.error(ratingResult.reason);
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
