/* The disorder index — front-end logic.
   Data contract: data/disorder_data.json produced by scripts/build_data.py.
   No numbers are computed outside what that file provides except per-1,000
   scaling for sparklines and simple sums for the verdict sentence. */

'use strict';

const MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const BORO_ORDER = ['Manhattan','Bronx','Brooklyn','Queens','Staten Island'];

// Trend classification thresholds (documented in methodology):
// rising/falling requires at least a 10% swing between 12-month windows.
const TREND_UP = 10, TREND_DOWN = -10;

let DATA = null, GEO = null;
let selected = null;            // boro_cd string or null for citywide
let yFromZero = true;
let map, geoLayer, mapMode = 'rate', mapStrand = null;

const $ = (id) => document.getElementById(id);

function fmtMonth(ym) {
  const [y, m] = ym.split('-').map(Number);
  return `${MONTH_NAMES[m - 1]} ${y}`;
}
function fmtNum(n) { return n.toLocaleString('en-US'); }
function fmtPct(p) { return (p > 0 ? '+' : '') + p.toFixed(1).replace(/\.0$/, '') + '%'; }

function trendClass(pct) {
  if (pct === null || pct === undefined) return 'nocall';
  if (pct >= TREND_UP) return 'rising';
  if (pct <= TREND_DOWN) return 'falling';
  return 'steady';
}
const TREND_WORD = { rising: 'Rising', falling: 'Falling', steady: 'Steady', nocall: 'Too few reports to call' };
const TREND_ARROW = { rising: '▲', falling: '▼', steady: '▬', nocall: '' };

function districtLabel(bcd) {
  const d = DATA.districts[bcd];
  const num = Number(bcd) % 100;
  return `${d.name} — ${d.borough} Community District ${num}`;
}

/* ---------- boot ---------- */
Promise.all([
  fetch('data/disorder_data.json').then(r => r.json()),
  fetch('data/community_districts.geojson').then(r => r.json()),
]).then(([data, geo]) => {
  DATA = data; GEO = geo;
  mapStrand = DATA.strands[0].id;
  $('heroMeta').textContent =
    `Covers ${fmtMonth(DATA.meta.months[0])} through ${fmtMonth(DATA.meta.months.at(-1))} · ` +
    `${fmtNum(DATA.meta.total_complaints)} 311 reports across the ten strands · updated ${(([y, m, d]) => `${MONTH_NAMES[m - 1]} ${Number(d)}, ${y}`)(DATA.meta.generated.split('-').map(Number))}`;
  buildPickers();
  buildMap();
  render();
});

function buildPickers() {
  const groups = {};
  Object.keys(DATA.districts).sort().forEach(bcd => {
    const d = DATA.districts[bcd];
    (groups[d.borough] = groups[d.borough] || []).push(bcd);
  });
  const fill = (sel, placeholder) => {
    sel.innerHTML = '';
    const ph = document.createElement('option');
    ph.value = ''; ph.textContent = placeholder;
    sel.appendChild(ph);
    BORO_ORDER.forEach(boro => {
      const og = document.createElement('optgroup');
      og.label = boro;
      (groups[boro] || []).forEach(bcd => {
        const o = document.createElement('option');
        o.value = bcd;
        o.textContent = `CD ${Number(bcd) % 100} — ${DATA.districts[bcd].name}`;
        og.appendChild(o);
      });
      sel.appendChild(og);
    });
  };
  fill($('districtSelect'), 'Citywide (choose a district)');
  fill($('compareA'), 'Choose a district');
  fill($('compareB'), 'Choose a district');
  $('districtSelect').addEventListener('change', e => { selected = e.target.value || null; render(); });
  $('citywideBtn').addEventListener('click', () => { selected = null; $('districtSelect').value = ''; render(); });
  $('compareA').addEventListener('change', renderCompare);
  $('compareB').addEventListener('change', renderCompare);
  $('yZeroToggle').addEventListener('change', e => { yFromZero = e.target.checked; renderCards(); });

  const strandSel = $('mapStrandSelect');
  DATA.strands.forEach(s => {
    const o = document.createElement('option');
    o.value = s.id; o.textContent = s.label;
    strandSel.appendChild(o);
  });
  strandSel.addEventListener('change', e => { mapStrand = e.target.value; paintMap(); });
  document.querySelectorAll('.mode-btn').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.mode-btn').forEach(x => x.classList.toggle('active', x === b));
    mapMode = b.dataset.mode; paintMap();
  }));

  // AI caution popover
  $('aiCautionBtn').addEventListener('click', () => {
    $('aiCautionPop').hidden = !$('aiCautionPop').hidden;
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('.ai-caution-pop') && !e.target.closest('.ai-caution-btn')) $('aiCautionPop').hidden = true;
  });
}

/* ---------- story + cards ---------- */
function strandStats(sid) {
  if (selected) return DATA.districts[selected].strands[sid];
  const c = DATA.strands.find(s => s.id === sid).citywide;
  return { ...c, rank: null, tercile: null, conc_flag: false };
}

function render() {
  const [l0, l1] = DATA.meta.last12;
  if (selected) {
    const d = DATA.districts[selected];
    $('storyTitle').textContent = d.name;
    let sub = document.querySelector('.story-sub');
    if (!sub) {
      sub = document.createElement('p'); sub.className = 'story-sub';
      $('storyTitle').after(sub);
    }
    sub.textContent = `${d.borough} Community District ${Number(selected) % 100} · population ${fmtNum(d.population)} (2020 census)`;
  } else {
    $('storyTitle').textContent = 'New York City, citywide';
    const sub = document.querySelector('.story-sub');
    if (sub) sub.textContent = `Population ${fmtNum(DATA.meta.citywide_population)} (2020 census)`;
  }

  // verdict sentence
  const counts = { rising: [], falling: [], steady: [], nocall: [] };
  let total12 = 0;
  DATA.strands.forEach(s => {
    const st = strandStats(s.id);
    total12 += st.n12;
    counts[trendClass(st.pct)].push(s.label.toLowerCase());
  });
  const where = selected ? DATA.districts[selected].name : 'New York City';
  const parts = [];
  if (counts.rising.length) parts.push(`rose in ${counts.rising.length} (${counts.rising.join(', ')})`);
  if (counts.falling.length) parts.push(`fell in ${counts.falling.length} (${counts.falling.join(', ')})`);
  if (counts.steady.length) parts.push(`held roughly steady in ${counts.steady.length}`);
  let sentence = `In the 12 months ending ${fmtMonth(l1)}, ${where} logged ${fmtNum(total12)} reports across the ten strands of disorder tracked here. Compared with the previous 12 months, reports ${parts.join(', ')}.`;
  if (counts.nocall.length) sentence += ` In ${counts.nocall.length} strand${counts.nocall.length > 1 ? 's' : ''} (${counts.nocall.join(', ')}), there were too few reports to judge a trend.`;
  $('verdictText').textContent = sentence;

  $('verdictChips').innerHTML =
    `<span class="chip rising">▲ ${counts.rising.length} rising</span>` +
    `<span class="chip steady">▬ ${counts.steady.length} steady</span>` +
    `<span class="chip falling">▼ ${counts.falling.length} falling</span>`;

  renderCards();
  renderCompare();
  if (geoLayer) paintMap();
}

function sparklineSVG(sid) {
  // District (or citywide) monthly reports per 1,000 residents, with the
  // citywide series as a dashed comparison line. Same per-1,000 scale.
  const months = DATA.meta.months;
  const w = 320, h = 78, padL = 2, padR = 2, padT = 6, padB = 14;
  const cw = DATA.strands.find(s => s.id === sid).citywide;
  const cityPop = DATA.meta.citywide_population;
  const citySeries = cw.monthly.map(v => v / cityPop * 1000);
  let mainSeries = citySeries, pop = cityPop;
  if (selected) {
    pop = DATA.districts[selected].population;
    mainSeries = DATA.districts[selected].strands[sid].monthly.map(v => v / pop * 1000);
  }
  const all = selected ? mainSeries.concat(citySeries) : mainSeries;
  let lo = yFromZero ? 0 : Math.min(...all);
  let hi = Math.max(...all, yFromZero ? 0 : -Infinity);
  if (hi === lo) hi = lo + 1;
  const x = i => padL + i / (months.length - 1) * (w - padL - padR);
  const y = v => padT + (1 - (v - lo) / (hi - lo)) * (h - padT - padB);
  const path = s => s.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join('');
  const city = selected ? `<path d="${path(citySeries)}" fill="none" stroke="#9b9fbc" stroke-width="1.2" stroke-dasharray="3 3"/>` : '';
  // year tick labels
  const ticks = months.map((m, i) => m.endsWith('-01') ? `<text x="${x(i).toFixed(1)}" y="${h - 2}" font-size="9.5" fill="#707175">${m.slice(0, 4)}</text>` : '').join('');
  const zero = yFromZero ? `<line x1="${padL}" x2="${w - padR}" y1="${y(0)}" y2="${y(0)}" stroke="#dddddd" stroke-width="1"/>` : '';
  return `<svg class="sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Monthly reports per 1,000 residents">
    ${zero}${ticks}${city}
    <path d="${path(mainSeries)}" fill="none" stroke="#ff7c53" stroke-width="1.8"/>
  </svg>`;
}

const STANDING_TEXT = {
  high: 'More reports per resident than most of the city',
  mid: 'Around the middle of the city',
  low: 'Fewer reports per resident than most of the city',
};

function renderCards() {
  const grid = $('cardsGrid');
  grid.innerHTML = '';
  DATA.strands.forEach(s => {
    const st = strandStats(s.id);
    const tc = trendClass(st.pct);
    const card = document.createElement('article');
    card.className = 'card';
    const standing = selected && st.tercile
      ? `<p class="standing"><span class="dot ${st.tercile}"></span>${STANDING_TEXT[st.tercile]} (ranks ${st.rank} of 59 on reports per resident)</p>`
      : `<p class="standing">Citywide: ${fmtNum(st.n12)} reports in the past 12 months</p>`;
    const conc = st.conc_flag
      ? `<div class="conc-flag">A small number of addresses accounts for an outsized share of these reports — read this trend with care.</div>` : '';
    const pctTxt = st.pct === null || st.pct === undefined
      ? TREND_WORD.nocall
      : `${TREND_ARROW[tc]} ${TREND_WORD[tc]} · ${fmtPct(st.pct)} vs prior 12 months`;
    card.innerHTML = `
      <div class="card-head">
        <span class="card-title">${s.label}</span>
        <span class="trend-badge ${tc}">${pctTxt}</span>
      </div>
      <div class="big-row">
        <span class="big-num">${st.rate.toLocaleString('en-US', { maximumFractionDigits: 1 })}</span>
        <span class="big-label">reports per 1,000 residents, past 12 months</span>
      </div>
      ${standing}
      ${sparklineSVG(s.id)}
      <div class="spark-caption"><span>${fmtMonth(DATA.meta.months[0])}</span><span>${selected ? 'orange: district · dashed: citywide' : 'citywide per 1,000 residents'}</span><span>${fmtMonth(DATA.meta.months.at(-1))}</span></div>
      ${conc}
      <p class="fine-print"><strong>What feeds this:</strong> 311 complaint types ${s.types.map(t => `“${t}”`).join(', ')}. ${s.desc}</p>`;
    grid.appendChild(card);
  });
}

/* ---------- map ---------- */
const RATE_COLORS = ['#57aa4a', '#9cc456', '#dde44c', '#ff7c53', '#d2232a'];
const CHANGE_BINS = [
  { test: p => p <= -20, color: '#57aa4a', label: 'Down 20% or more' },
  { test: p => p <= TREND_DOWN, color: '#9cc456', label: 'Down 10–20%' },
  { test: p => p < TREND_UP, color: '#dddddd', label: 'Roughly steady (±10%)' },
  { test: p => p < 20, color: '#ff7c53', label: 'Up 10–20%' },
  { test: p => true, color: '#d2232a', label: 'Up 20% or more' },
];

function buildMap() {
  // Initialize with an explicit finite view: if the container is hidden or
  // zero-width at load (embeds, prerender), fitBounds would poison the zoom.
  map = L.map('map', {
    center: [40.7058, -73.9778], zoom: 10,
    scrollWheelZoom: false, attributionControl: false, zoomSnap: 0.25,
    minZoom: 9, maxZoom: 14,
  });
  geoLayer = L.geoJSON(GEO, {
    style: { color: '#ffffff', weight: 1.2, fillOpacity: 1, fillColor: '#eee' },
    onEachFeature: (f, layer) => {
      const bcd = f.properties.cd_code;
      layer.on('click', () => {
        selected = bcd;
        $('districtSelect').value = bcd;
        render();
        $('storySection').scrollIntoView({ behavior: 'smooth' });
      });
      layer.on('mouseover', () => layer.setStyle({ weight: 2.5, color: '#050507' }));
      layer.on('mouseout', () => layer.setStyle({ weight: 1.2, color: '#ffffff' }));
    },
  }).addTo(map);
  // Fit the five boroughs once the container has real dimensions, then leave
  // the user's pan/zoom alone.
  let fitted = false;
  const fitCity = () => {
    map.invalidateSize();
    const sz = map.getSize();
    if (fitted || !sz.x || !sz.y) return;
    const b = geoLayer.getBounds();
    const p1 = map.project(b.getNorthWest(), 0), p2 = map.project(b.getSouthEast(), 0);
    const zoom = Math.floor(Math.log2(Math.min(
      (sz.x - 16) / Math.abs(p2.x - p1.x),
      (sz.y - 16) / Math.abs(p2.y - p1.y))) * 4) / 4;
    map.setView(b.getCenter(), Math.max(9, Math.min(11.5, zoom)), { animate: false });
    fitted = true;
  };
  fitCity();
  new ResizeObserver(fitCity).observe(document.getElementById('map'));
  window._map = map; window._geoLayer = geoLayer; // debug/testing hook
}

function quantileBreaks(values, n) {
  const sorted = [...values].sort((a, b) => a - b);
  return Array.from({ length: n - 1 }, (_, i) => sorted[Math.floor((i + 1) * sorted.length / n)]);
}

function paintMap() {
  const vals = Object.keys(DATA.districts).map(b => DATA.districts[b].strands[mapStrand].rate);
  const breaks = quantileBreaks(vals, 5);
  const legend = $('mapLegend');
  geoLayer.eachLayer(layer => {
    const bcd = layer.feature.properties.cd_code;
    const st = DATA.districts[bcd] && DATA.districts[bcd].strands[mapStrand];
    if (!st) { layer.setStyle({ fillColor: '#f5f5f5' }); return; }
    let fill, tipVal;
    if (mapMode === 'rate') {
      let i = breaks.findIndex(b => st.rate <= b);
      if (i === -1) i = 4;
      fill = RATE_COLORS[i];
      tipVal = `${st.rate.toLocaleString('en-US')} reports per 1,000 residents`;
    } else {
      if (st.pct === null || st.pct === undefined) { fill = '#f5f5f5'; tipVal = 'too few reports to judge a trend'; }
      else {
        fill = CHANGE_BINS.find(b => b.test(st.pct)).color;
        tipVal = `${fmtPct(st.pct)} vs prior 12 months`;
      }
    }
    layer.setStyle({ fillColor: fill });
    const label = DATA.strands.find(s => s.id === mapStrand).label;
    layer.bindTooltip(`<div class="map-tip"><strong>${districtLabel(bcd)}</strong><br>${label}: ${tipVal}${st.conc_flag ? '<br><em>Concentrated at a few addresses</em>' : ''}</div>`, { sticky: true });
  });
  if (mapMode === 'rate') {
    legend.innerHTML = RATE_COLORS.map((c, i) => {
      const lo = i === 0 ? Math.min(...vals) : breaks[i - 1];
      const hi = i === 4 ? Math.max(...vals) : breaks[i];
      return `<span class="legend-item"><span class="legend-swatch" style="background:${c}"></span>${lo.toLocaleString('en-US', { maximumFractionDigits: 1 })}–${hi.toLocaleString('en-US', { maximumFractionDigits: 1 })}</span>`;
    }).join('') + '<span class="legend-item">quintiles, reports per 1,000 residents</span>';
  } else {
    legend.innerHTML = CHANGE_BINS.map(b =>
      `<span class="legend-item"><span class="legend-swatch" style="background:${b.color}"></span>${b.label}</span>`).join('');
  }
}

/* ---------- compare ---------- */
function renderCompare() {
  const a = $('compareA').value, b = $('compareB').value;
  const wrap = $('compareTableWrap');
  if (!a || !b) { wrap.innerHTML = '<p style="color:#707175;font-size:14px">Choose two districts to compare their per-resident report rates and one-year trends, strand by strand.</p>'; return; }
  const rows = DATA.strands.map(s => {
    const sa = DATA.districts[a].strands[s.id], sb = DATA.districts[b].strands[s.id];
    const cw = s.citywide.rate;
    const delta = st => {
      const tc = trendClass(st.pct);
      if (tc === 'nocall') return '<span class="delta-flat">–</span>';
      return `<span class="delta-${tc === 'rising' ? 'up' : tc === 'falling' ? 'down' : 'flat'}">${fmtPct(st.pct)}</span>`;
    };
    const f = (v) => v.toLocaleString('en-US', { maximumFractionDigits: 1 });
    return `<tr><td class="strand-name">${s.label}</td>
      <td class="num">${f(sa.rate)} ${delta(sa)}</td>
      <td class="num">${f(sb.rate)} ${delta(sb)}</td>
      <td class="num">${f(cw)}</td></tr>`;
  }).join('');
  wrap.innerHTML = `<table class="compare-table">
    <thead><tr><th>Strand</th><th>${DATA.districts[a].name}</th><th>${DATA.districts[b].name}</th><th>Citywide</th></tr>
    <tr><th></th><th colspan="3" style="font-weight:300;text-transform:none;letter-spacing:0">Reports per 1,000 residents, past 12 months · change vs prior 12</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}
