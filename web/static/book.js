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
  el.innerHTML = links.length ? `Карточки: ${links.join(' · ')}` : '';
}

async function renderWork(w) {
  document.title = `${w.title} — Bookfinder`;
  document.getElementById('d-title').textContent = w.title;
  document.getElementById('d-authors').textContent = (w.authors || []).join(', ') || 'Автор не указан';
  document.getElementById('d-rating').textContent =
    `Сводный: ${formatAggregateRating(w.aggregate_rating)} | FantLab: ${w.fantlab?.rating ?? '—'} | LiveLib: ${w.livelib?.rating ?? '—'} | FW: ${w.fantasy_worlds?.rating ?? '—'} | Кубикус: ${w.kubikus?.rating ?? '—'} | BookMix: ${w.bookmix?.rating ?? '—'}`;

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
    ? `${esc(relevanceText)}<br><span class="muted">Рейтинг — качество по данным источников. Релевантность — насколько книга подходит под ваш запрос в каталоге.</span>`
    : '';

  document.getElementById('d-genres').innerHTML = (w.genres || []).length
    ? (w.genres || []).map((g) => `<span class="badge">${esc(g)}</span>`).join('')
    : '<span class="muted">Жанры не указаны</span>';

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
      const a = document.createElement('a');
      a.href = workUrl(s.id);
      const rating = s.aggregate_rating != null ? ` · ${s.aggregate_rating}` : '';
      a.textContent = `${s.title} — ${(s.authors || []).join(', ')}${rating}`;
      li.appendChild(a);
      similarEl.appendChild(li);
    });
  }

  const reviewsEl = document.getElementById('d-reviews');
  try {
    const rev = await apiJson(`/api/works/${w.id}/reviews?limit=10`);
    if (!rev.reviews?.length) {
      reviewsEl.innerHTML = '<p class="muted">Отзывов с сайтов пока нет.</p>';
    } else {
      reviewsEl.innerHTML = rev.reviews.map((r) => {
        const src = { fantasy_worlds: 'FW', fantlab: 'FantLab', livelib: 'LiveLib', kubikus: 'Кубикус', bookmix: 'BookMix' }[r.source] || r.source;
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
    await renderWork(w);
  } catch (err) {
    showError(err.message);
    console.error(err);
  }
}

init();
