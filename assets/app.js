/* ===============================================
   Contract Timeline Dashboard - frontend logic
   =============================================== */

const DATA_BASE = 'data';

// ───────────────────────────────────────────────
// Utilities
// ───────────────────────────────────────────────
const fmt = {
  amount(v) {
    if (v == null || isNaN(v)) return '—';
    return (v / 1e8).toLocaleString('ko-KR', { maximumFractionDigits: 0 });
  },
  mcap(v) {
    if (v == null || isNaN(v)) return '—';
    if (v >= 1e12) return (v / 1e12).toFixed(2) + '조';
    if (v >= 1e8)  return (v / 1e8).toFixed(0) + '억';
    return v.toLocaleString();
  },
  price(v) {
    if (v == null || isNaN(v)) return '—';
    return Math.round(v).toLocaleString('ko-KR');
  },
  pct(v) {
    if (v == null || isNaN(v)) return '—';
    const s = v > 0 ? '+' : '';
    return s + v.toFixed(2) + '%';
  },
  date(s) {
    if (!s) return '—';
    return s.slice(0, 10);
  },
  dateTime(s) {
    if (!s) return '—';
    return s.replace('T', ' ').slice(0, 16);
  },
};

function stars(n) {
  n = Math.max(0, Math.min(5, parseInt(n) || 0));
  const filledClass = `filled-${n}`;
  let html = '<span class="stars" title="중요도 ' + n + '/5">';
  for (let i = 1; i <= 5; i++) {
    html += `<span class="star ${i <= n ? filledClass : ''}">★</span>`;
  }
  html += '</span>';
  return html;
}

function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function fetchJson(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`fetch ${path} -> ${r.status}`);
  return r.json();
}

// ───────────────────────────────────────────────
// Meta strip
// ───────────────────────────────────────────────
async function loadMeta() {
  try {
    const meta = await fetchJson(`${DATA_BASE}/meta.json`);
    const isStub = !meta.updated_at || meta.updated_at.startsWith('1970');
    const txt = isStub
      ? '데이터 준비중 · 백필 실행 필요'
      : `Updated ${fmt.dateTime(meta.updated_at)} · 공시 ${meta.n_contracts}건 · 종목 ${meta.n_stocks}`;
    const el = document.getElementById('metaStrip');
    if (el) el.textContent = txt;
    const f = document.getElementById('footerUpdated');
    if (f) f.textContent = isStub ? '— 아직 빌드되지 않음' : `Last updated: ${fmt.dateTime(meta.updated_at)}`;
  } catch (e) {
    console.warn('meta load fail', e);
  }
}

// ===============================================
// MAIN PAGE
// ===============================================
let _contracts = [];
let _stockInfo = [];
let _stockMap  = {};

async function initMainPage() {
  await loadMeta();
  try {
    [_contracts, _stockInfo] = await Promise.all([
      fetchJson(`${DATA_BASE}/contracts.json`),
      fetchJson(`${DATA_BASE}/stock_info.json`),
    ]);
    _stockMap = Object.fromEntries(_stockInfo.map(s => [s.code, s]));
  } catch (e) {
    console.error(e);
    document.getElementById('contractTbody').innerHTML =
      `<tr><td colspan="8" style="padding:40px;text-align:center;color:var(--negative)">데이터 로드 실패: ${esc(e.message)}</td></tr>`;
    return;
  }

  setupSearch();
  setupFilters();
  renderContractTable();
}

function setupSearch() {
  const input = document.getElementById('searchInput');
  const results = document.getElementById('searchResults');
  let activeIdx = -1;

  const render = (matches) => {
    if (!matches.length) {
      results.innerHTML = `<div class="search-result-empty">검색 결과 없음</div>`;
    } else {
      results.innerHTML = matches.slice(0, 20).map((s, i) => `
        <div class="search-result-item${i === activeIdx ? ' active' : ''}" data-code="${s.code}">
          <span class="search-result-name">${esc(s.name)}</span>
          <span class="search-result-meta">${s.code} · ${s.market}</span>
        </div>
      `).join('');
    }
    results.hidden = false;
  };

  const doSearch = (q) => {
    q = q.trim();
    if (!q) { results.hidden = true; return []; }
    const lq = q.toLowerCase();
    const matches = _stockInfo.filter(s => {
      if (s.code.startsWith(q)) return true;
      if (s.name.includes(q)) return true;
      // 초성검색: 입력이 모두 초성이면 chosung 매칭
      if (/^[ㄱ-ㅎ]+$/.test(q) && s.chosung && s.chosung.startsWith(q)) return true;
      return false;
    });
    // 정렬: 종목코드 prefix → 이름 prefix → 이름 contains → 초성
    matches.sort((a, b) => {
      const score = (s) => {
        if (s.code === q) return 0;
        if (s.code.startsWith(q)) return 1;
        if (s.name === q) return 2;
        if (s.name.startsWith(q)) return 3;
        if (s.name.includes(q)) return 4;
        return 5;
      };
      return score(a) - score(b);
    });
    return matches;
  };

  let currentMatches = [];

  input.addEventListener('input', () => {
    activeIdx = -1;
    currentMatches = doSearch(input.value);
    render(currentMatches);
  });

  input.addEventListener('keydown', (e) => {
    if (results.hidden) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(currentMatches.length - 1, activeIdx + 1);
      render(currentMatches);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(0, activeIdx - 1);
      render(currentMatches);
    } else if (e.key === 'Enter' && activeIdx >= 0) {
      e.preventDefault();
      goToStock(currentMatches[activeIdx].code);
    } else if (e.key === 'Escape') {
      results.hidden = true;
    }
  });

  results.addEventListener('click', (e) => {
    const item = e.target.closest('.search-result-item');
    if (item) goToStock(item.dataset.code);
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-wrap')) results.hidden = true;
  });
}

function goToStock(code) {
  if (code) window.location.href = `stock.html?code=${encodeURIComponent(code)}`;
}

function setupFilters() {
  document.getElementById('sortBy').addEventListener('change', renderContractTable);
  document.getElementById('minImportance').addEventListener('change', renderContractTable);
}

function renderContractTable() {
  const sortBy = document.getElementById('sortBy').value;
  const minImp = parseInt(document.getElementById('minImportance').value);
  const tbody  = document.getElementById('contractTbody');
  const empty  = document.getElementById('emptyState');
  const count  = document.getElementById('resultCount');

  let rows = _contracts.filter(c => (c.ai_importance || 0) >= minImp);

  const cmp = {
    'date_desc':       (a, b) => b.date.localeCompare(a.date) || b.id.localeCompare(a.id),
    'date_asc':        (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id),
    'importance_desc': (a, b) => (b.ai_importance || 0) - (a.ai_importance || 0) || b.date.localeCompare(a.date),
    'amount_desc':     (a, b) => (b.amount || 0) - (a.amount || 0),
  }[sortBy];
  rows.sort(cmp);

  count.textContent = `${rows.length.toLocaleString()}건`;
  empty.hidden = rows.length > 0;

  tbody.innerHTML = rows.map(c => `
    <tr data-code="${c.code}">
      <td class="col-date">${fmt.date(c.date)}</td>
      <td class="col-stock">
        <div class="stock-cell">
          <span class="stock-cell-name">${esc(c.name)}</span>
          <span class="stock-cell-code">${esc(c.code)}</span>
        </div>
      </td>
      <td class="col-title title-cell">${esc(c.title)}</td>
      <td class="col-counter">${esc(c.counterparty || '—')}</td>
      <td class="col-amount">${fmt.amount(c.amount)}</td>
      <td class="col-ratio">${c.revenue_ratio != null ? c.revenue_ratio.toFixed(1) + '%' : '—'}</td>
      <td class="col-imp">${stars(c.ai_importance)}</td>
      <td class="col-summary"><div class="summary-cell">${esc(c.ai_summary || '')}</div></td>
    </tr>
  `).join('');

  tbody.querySelectorAll('tr').forEach(tr => {
    tr.addEventListener('click', () => goToStock(tr.dataset.code));
  });
}

// ===============================================
// STOCK PAGE
// ===============================================
let _stockContracts = [];
let _stockBriefs = [];
let _stock = null;

async function initStockPage() {
  await loadMeta();
  const params = new URLSearchParams(window.location.search);
  const code = (params.get('code') || '').trim();
  if (!code) {
    document.getElementById('stockName').textContent = '종목 코드가 없습니다';
    return;
  }

  let stockInfo;
  try {
    stockInfo = await fetchJson(`${DATA_BASE}/stock_info.json`);
  } catch (e) {
    console.error(e); return;
  }

  _stock = stockInfo.find(s => s.code === code);
  if (!_stock) {
    document.getElementById('stockName').textContent = `종목 정보 없음 (${code})`;
    return;
  }

  renderStockHeader();

  // 공급계약 + brief 병렬 로드
  try {
    const allContracts = await fetchJson(`${DATA_BASE}/contracts.json`);
    _stockContracts = allContracts.filter(c => c.code === code);
  } catch (e) {
    console.warn('contracts load fail', e);
    _stockContracts = [];
  }
  try {
    _stockBriefs = await fetchJson(`${DATA_BASE}/briefs_by_stock/${code}.json`);
  } catch (e) {
    _stockBriefs = []; // 해당 종목 brief 없을 수 있음
  }

  document.getElementById('briefToggle').addEventListener('change', renderTimeline);
  renderTimeline();
}

function renderStockHeader() {
  const s = _stock;
  document.getElementById('stockName').textContent = s.name;
  document.getElementById('stockCode').textContent = s.code;
  document.getElementById('stockMarket').textContent = s.market || '';

  document.getElementById('stockPrice').textContent = fmt.price(s.price) + '원';
  const chg = s.change_rate;
  const chgEl = document.getElementById('stockChange');
  chgEl.textContent = fmt.pct(chg);
  chgEl.className = 'stat-sub ' + (chg > 0 ? 'up' : chg < 0 ? 'down' : 'flat');

  document.getElementById('stockMcap').textContent = fmt.mcap(s.market_cap);
  document.getElementById('stock52w').textContent =
    `${fmt.price(s.high_52w)} / ${fmt.price(s.low_52w)}`;

  const yoyEl = document.getElementById('stockYoy');
  yoyEl.textContent = fmt.pct(s.yoy_return);
  yoyEl.classList.remove('up','down','flat');
  if (s.yoy_return > 0) yoyEl.style.color = 'var(--positive)';
  else if (s.yoy_return < 0) yoyEl.style.color = 'var(--negative)';

  document.title = `${s.name} (${s.code}) - 공급계약 타임라인`;
}

function renderTimeline() {
  const showBrief = document.getElementById('briefToggle').checked;
  const tl    = document.getElementById('timeline');
  const empty = document.getElementById('timelineEmpty');
  const badge = document.getElementById('contractCountBadge');

  // 항목 모으기
  const items = _stockContracts.map(c => ({
    type: 'contract',
    date: c.date,
    sortKey: c.date,
    data: c,
  }));

  if (showBrief) {
    _stockBriefs.forEach(b => {
      items.push({
        type: 'brief',
        date: b.created_at ? b.created_at.slice(0,10) : b.date,
        sortKey: b.created_at || b.date,
        data: b,
      });
    });
  }

  badge.textContent = `${_stockContracts.length}건`;

  if (items.length === 0) {
    tl.innerHTML = '';
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  items.sort((a,b) => b.sortKey.localeCompare(a.sortKey));

  tl.innerHTML = items.map(it => {
    if (it.type === 'contract') {
      const c = it.data;
      return `
        <div class="tl-item contract">
          <span class="tl-dot"></span>
          <div class="tl-date">${fmt.date(c.date)}</div>
          <div class="tl-card">
            <div class="tl-card-head">
              <div class="tl-card-title">${esc(c.title)}</div>
              <span class="tag tag-contract">공급계약</span>
            </div>
            <div class="tl-card-meta">
              <span>상대: ${esc(c.counterparty || '—')}</span>
              <span>금액: ${fmt.amount(c.amount)}억</span>
              <span>매출비중: ${c.revenue_ratio != null ? c.revenue_ratio.toFixed(2) + '%' : '—'}</span>
              ${stars(c.ai_importance)}
            </div>
            <div class="tl-card-summary">${esc(c.ai_summary || '')}</div>
            ${c.url ? `<a class="tl-card-link" href="${esc(c.url)}" target="_blank" rel="noopener">원문 공시 →</a>` : ''}
          </div>
        </div>
      `;
    } else {
      const b = it.data;
      const polClass = b.polarity ? `tag-pol-${b.polarity}` : '';
      return `
        <div class="tl-item brief">
          <span class="tl-dot"></span>
          <div class="tl-date">${fmt.dateTime(b.created_at)}</div>
          <div class="tl-card">
            <div class="tl-card-head">
              <div class="tl-card-title">${esc(b.article_title || '(제목 없음)')}</div>
              <span class="tag tag-brief">브리핑</span>
            </div>
            <div class="tl-card-meta">
              <span>${esc(b.publisher || '')}</span>
              ${b.polarity ? `<span class="tag ${polClass}">${esc(b.polarity)}</span>` : ''}
              ${b.change_rate != null ? `<span class="${b.change_rate > 0 ? 'stat-sub up' : b.change_rate < 0 ? 'stat-sub down' : ''}">${fmt.pct(b.change_rate)}</span>` : ''}
            </div>
            <div class="tl-card-summary summary-muted">${esc(b.briefing || '')}</div>
            ${b.content_url ? `<a class="tl-card-link" href="${esc(b.content_url)}" target="_blank" rel="noopener">기사 원문 →</a>` : ''}
          </div>
        </div>
      `;
    }
  }).join('');
}
