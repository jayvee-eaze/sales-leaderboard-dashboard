// Deterministic HTML injection. Reads index.template.html (source, human-edited, never
// served) + data.json (single source of numbers), writes index.html (served, never
// hand-edited). No LLM writes a number into HTML: every figure below is read out of
// data.json. Refuses to write if a marker region is missing, a token is unresolved, or
// an em/en dash appears in the output (house style forbids them).
const fs = require('fs');

const d = JSON.parse(fs.readFileSync('data.json', 'utf8'));

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Canonical window order, shared by the scorecard and the leaderboard table so one
// toggle controls both. Defaults to All Time: a young account's early wins can predate
// the current day/week/month/quarter boundary, so a rolling window alone can make a real
// sale look like it never happened (this is exactly what surfaced 2026-07-09).
const WINS = [
  { key: 'day', label: 'Today' },
  { key: 'week', label: 'This week' },
  { key: 'month', label: 'This month' },
  { key: 'quarter', label: 'This quarter' },
  { key: 'allTime', label: 'All time' },
];
const DEFAULT_WIN = 'allTime';

const COLS = [
  { k: 'name', label: 'Closer', cls: '' },
  { k: 'dealsClosed', label: 'Deals closed', cls: 'num' },
  { k: 'cash', label: 'Cash collected', cls: 'num ok' },
  { k: 'trend', label: 'Trend', cls: 'num' },
  { k: 'callsBooked', label: 'Calls booked', cls: 'num' },
  { k: 'callsHeld', label: 'Calls held', cls: 'num' },
  { k: 'noShow', label: 'No show', cls: 'num' },
  { k: 'noShowRate', label: 'No show rate', cls: 'num' },
  { k: 'showed', label: 'Show', cls: 'num' },
  { k: 'showRate', label: 'Show rate', cls: 'num' },
  { k: 'closeRate', label: 'Close rate', cls: 'num' },
  { k: 'outboundCalls', label: 'Outbound calls', cls: 'num' },
  { k: 'inboundCalls', label: 'Inbound calls', cls: 'num' },
  { k: 'callHours', label: 'Call hours', cls: 'num' },
];

// The team-wide scorecard tiles, in display order, each pulled straight from data.totals.
const SCORECARD_TILES = [
  { k: 'cash', label: 'Total cash collected', cls: 'ok' },
  { k: 'dealsClosed', label: 'Total deals closed', cls: '' },
  { k: 'callsBooked', label: 'Total calls booked', cls: '' },
  { k: 'callsHeld', label: 'Total calls held', cls: '' },
  { k: 'noShow', label: 'Total no show', cls: '' },
  { k: 'noShowRate', label: 'No show rate', cls: '' },
  { k: 'showed', label: 'Total show', cls: '' },
];

const LEADER_TILES = [
  { k: 'topCash', label: 'Top cash collected' },
  { k: 'topCloseRate', label: 'Top close rate' },
  { k: 'topShowRate', label: 'Top show rate' },
  { k: 'mostActive', label: 'Most active (calls)' },
];

function medal(rank) {
  if (rank === 1) return '<span class="medal g">1</span>';
  if (rank === 2) return '<span class="medal s">2</span>';
  if (rank === 3) return '<span class="medal b">3</span>';
  return '<span class="medal">' + rank + '</span>';
}

function rankClass(rank) {
  return rank === 1 ? 'g' : rank === 2 ? 's' : rank === 3 ? 'b' : '';
}

function initials(name) {
  const parts = String(name).trim().split(/\s+/);
  return ((parts[0] || '')[0] || '') + ((parts[parts.length - 1] || '')[0] || '');
}

function buildBadgeChips(badges) {
  if (!badges || !badges.length) return '';
  return '<div class="chips">' + badges.map(b => '<span class="chip">' + esc(b) + '</span>').join('') + '</div>';
}

const PODIUM_STATS = [
  { k: 'dealsClosed', label: 'Deals closed' },
  { k: 'callsBooked', label: 'Calls booked' },
  { k: 'showRate', label: 'Show rate' },
  { k: 'closeRate', label: 'Close rate' },
];

function buildPodiumCard(row) {
  const rc = rankClass(row.rank);
  const stats = PODIUM_STATS.map(s =>
    '<div class="pstat"><div class="pstat-v">' + esc(row[s.k]) + '</div><div class="pstat-l">' + esc(s.label) + '</div></div>'
  ).join('');
  return '<article class="podium-card ' + rc + '">' +
    '<div class="podium-hd">' +
    '<span class="prank">' + row.rank + '</span>' +
    '<span class="avatar ' + rc + '">' + esc(initials(row.name)) + '</span>' +
    '<div class="podium-id"><div class="podium-name">' + esc(row.name) +
    (row.rank === 1 && row.cashCents > 0 ? ' <span class="leading-tag">Leading</span>' : '') + '</div>' +
    buildBadgeChips((row.badges || []).filter(b => b !== 'Leading')) +
    '</div>' +
    trendBadge(row.trend, row.trendNote) +
    '</div>' +
    '<div class="podium-cash"><span class="pc-amt ' + (row.cashCents > 0 ? 'ok' : '') + '">' + esc(row.cash) + '</span>' +
    '<span class="pc-note">' + esc(row.gapNote) + '</span></div>' +
    '<div class="pstats">' + stats + '</div>' +
    '</article>';
}

function trendBadge(trend, note) {
  if (trend === 'na') return '<span class="trend-tag na">career</span>';
  const glyph = trend === 'up' ? '&#9650;' : trend === 'down' ? '&#9660;' : '&#9679;';
  return '<span class="trend-tag ' + trend + '" title="' + esc(note) + '">' + glyph + '</span>';
}

function buildTable(rows, totals) {
  const head = '<tr><th></th>' + COLS.map(c => '<th class="' + c.cls + '">' + c.label + '</th>').join('') + '</tr>';
  const body = rows.map(r => {
    const cells = COLS.map(c => {
      if (c.k === 'trend') return '<td class="' + c.cls + '">' + trendBadge(r.trend, r.trendNote) + '</td>';
      const raw = c.k === 'callHours' ? Number(r[c.k]).toFixed(1) : r[c.k];
      const v = c.k === 'name' ? esc(r.name) : esc(raw);
      return '<td class="' + c.cls + '">' + v + '</td>';
    }).join('');
    return '<tr><td class="rank">' + medal(r.rank) + '</td>' + cells + '</tr>';
  }).join('\n');
  const totalCells = COLS.map(c => {
    if (c.k === 'name') return '<td class="foot">Team total</td>';
    if (c.k === 'trend') return '<td class="num foot">' + trendBadge(totals.trend, totals.trendNote) + '</td>';
    const raw = c.k === 'callHours' ? Number(totals[c.k]).toFixed(1) : totals[c.k];
    return '<td class="num foot">' + esc(raw) + '</td>';
  }).join('');
  const foot = '<tr class="totalrow"><td></td>' + totalCells + '</tr>';
  return '<div class="boardwrap"><table class="board">' +
    '<thead>' + head + '</thead><tbody>' + body + '</tbody><tfoot>' + foot + '</tfoot></table></div>';
}

// Shared toggle: one set of buttons controls every .wpanel on the page, in whichever
// section it lives, since both the scorecard and the leaderboard table render their
// panels with the same data-win attribute and .wpanel class.
function buildWindowTabs() {
  const tabs = WINS.map(w =>
    '<button class="wtab' + (w.key === DEFAULT_WIN ? ' active' : '') + '" data-win="' + w.key + '" onclick="slSwitchWindow(\'' + w.key + '\')">' + esc(w.label) + '</button>'
  ).join('');
  const script = '<script>function slSwitchWindow(k){' +
    'document.querySelectorAll(".wtab").forEach(function(b){b.classList.toggle("active", b.dataset.win===k);});' +
    'document.querySelectorAll(".wpanel").forEach(function(p){p.classList.toggle("active", p.dataset.win===k);});' +
    '}</script>';
  return '<div class="wtabs">' + tabs + '</div>' + script;
}

function leaderCard(tile, leader, winKey) {
  if (!leader) {
    return '<div class="leadercard"><span class="lc-tag">' + esc(tile.label) + '</span>' +
      '<div class="lc-main"><span class="avatar sm">-</span>' +
      '<div><div class="lc-name">Awaiting data</div></div></div></div>';
  }
  // Color the avatar by this closer's actual overall rank in the same window, so the
  // gold/silver/bronze thread is consistent with the podium cards below.
  const rankRow = d.leaderboard[winKey].find(r => r.key === leader.key);
  const rc = rankClass(rankRow ? rankRow.rank : 0);
  return '<div class="leadercard ' + rc + '"><span class="lc-tag">' + esc(tile.label) + '</span>' +
    '<div class="lc-main"><span class="avatar sm ' + rc + '">' + esc(initials(leader.name)) + '</span>' +
    '<div><div class="lc-name">' + esc(leader.name) + '</div>' +
    '<div class="lc-value">' + esc(leader.value) + '</div></div></div></div>';
}

function buildScorecardBlock() {
  const panels = WINS.map(w => {
    const t = d.totals[w.key];
    const tiles = SCORECARD_TILES.map(tile =>
      '<div class="tile"><div class="tv ' + tile.cls + '">' + esc(t[tile.k]) + '</div><div class="tl">' + esc(tile.label) + '</div></div>'
    ).join('');
    const lead = d.leaders[w.key];
    const cards = LEADER_TILES.map(tile => leaderCard(tile, lead[tile.k], w.key)).join('');
    return '<div class="wpanel' + (w.key === DEFAULT_WIN ? ' active' : '') + '" data-win="' + w.key + '">' +
      '<div class="wlabel">' + esc(d.windows[w.key].label) + '</div>' +
      '<div class="tiles">' + tiles + '</div>' +
      '<div class="leaders-hd">Leaders, this window</div>' +
      '<div class="leaders">' + cards + '</div>' +
      '</div>';
  }).join('\n');
  return buildWindowTabs() + panels;
}

function buildLeaderboardBlock() {
  return WINS.map(w => {
    const rows = d.leaderboard[w.key];
    const podium = rows.map(buildPodiumCard).join('');
    return '<div class="wpanel' + (w.key === DEFAULT_WIN ? ' active' : '') + '" data-win="' + w.key + '">' +
      '<div class="wlabel">' + esc(d.windows[w.key].label) + '</div>' +
      '<div class="podium">' + podium + '</div>' +
      '<h3 class="sub-sec">Full detail</h3>' +
      buildTable(rows, d.totals[w.key]) +
      '</div>';
  }).join('\n');
}

function buildCareerBanner() {
  const t = d.totals.allTime;
  const top = d.leaders.allTime.topCash;
  const topText = top ? (esc(top.name) + ' leads with ' + esc(top.value)) : 'No cash collected yet';
  return '<div class="career"><span class="career-tag">ALL TIME</span> ' +
    '<b>' + esc(t.cash) + '</b> collected &middot; <b>' + esc(t.dealsClosed) + '</b> deal' + (t.dealsClosed === 1 ? '' : 's') + ' closed &middot; ' +
    topText + ' &middot; since ' + esc(d.windows.allTime.start) +
    '</div>';
}

// --- Pipeline Health page: no window toggle, always full history / current snapshot ---

function svgBarChart(rows, valueKey, opts) {
  const W = 700, H = 130, padL = 6, padR = 6, padB = 18, padT = 6;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const max = Math.max(1, ...rows.map(r => r[valueKey]));
  const bw = innerW / rows.length;
  const bars = rows.map((r, i) => {
    const v = r[valueKey];
    const bh = (v / max) * innerH;
    const x = padL + i * bw + bw * 0.15;
    const y = padT + innerH - bh;
    const w = bw * 0.7;
    const label = (i % 4 === 0) ? '<text x="' + (x + w / 2) + '" y="' + (H - 4) + '" font-size="9" fill="#64748B" text-anchor="middle">' + esc(r.date.slice(5)) + '</text>' : '';
    const title = '<title>' + esc(r.date) + ': ' + esc(String(v)) + '</title>';
    return '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + Math.max(bh, v > 0 ? 2 : 0).toFixed(1) + '" fill="' + (opts.color || '#3B82F6') + '" rx="2">' + title + '</rect>' + label;
  }).join('');
  return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="chart">' + bars + '</svg>';
}

function svgLineChart(rows, valueKey, opts) {
  const W = 700, H = 130, padL = 6, padR = 6, padB = 18, padT = 10;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const max = opts.max || Math.max(1, ...rows.map(r => r[valueKey] || 0));
  const step = innerW / Math.max(1, rows.length - 1);
  const pt = (i, v) => [padL + i * step, padT + innerH - (v / max) * innerH];
  let segs = [], cur = [];
  rows.forEach((r, i) => {
    const v = r[valueKey];
    if (v === null || v === undefined) {
      if (cur.length) segs.push(cur);
      cur = [];
    } else {
      cur.push(pt(i, v));
    }
  });
  if (cur.length) segs.push(cur);
  const lines = segs.map(seg =>
    '<polyline points="' + seg.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ') + '" fill="none" stroke="' + (opts.color || '#3B82F6') + '" stroke-width="2"/>' +
    seg.map(p => '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="2.5" fill="' + (opts.color || '#3B82F6') + '"/>').join('')
  ).join('');
  const labels = rows.map((r, i) => (i % 4 === 0) ?
    '<text x="' + pt(i, 0)[0].toFixed(1) + '" y="' + (H - 4) + '" font-size="9" fill="#64748B" text-anchor="middle">' + esc(r.date.slice(5)) + '</text>' : '').join('');
  return '<svg viewBox="0 0 ' + W + ' ' + H + '" class="chart">' + lines + labels + '</svg>';
}

function buildTrendCharts() {
  const daily = d.daily;
  const showRateRows = daily.map(r => ({ date: r.date, v: (r.showed + r.noShow) > 0 ? Math.round(100 * r.showed / (r.showed + r.noShow)) : null }));
  let cum = 0;
  const cumCash = daily.map(r => { cum += r.cashCents; return { date: r.date, v: cum / 100 }; });
  return (
    '<div class="charthd">Calls booked per day, since launch</div>' +
    svgBarChart(daily, 'callsBooked', { color: '#3B82F6' }) +
    '<div class="charthd">Show rate per day (blank = no calls resolved that day)</div>' +
    svgLineChart(showRateRows.map(r => ({ date: r.date, pct: r.v })), 'pct', { color: '#059669', max: 100 }) +
    '<div class="charthd">Cumulative cash collected, since launch</div>' +
    svgBarChart(cumCash.map(r => ({ date: r.date, cum: r.v })), 'cum', { color: '#059669' })
  );
}

function buildFunnel() {
  const max = Math.max(1, ...d.funnel.map(f => f.count));
  const rows = d.funnel.map(f => {
    const pctW = Math.max(2, Math.round(100 * f.count / max));
    return '<div class="frow"><div class="flabel">' + esc(f.label) + '</div>' +
      '<div class="fbarwrap"><div class="fbar" style="width:' + pctW + '%"></div></div>' +
      '<div class="fcount">' + esc(f.count) + '</div></div>';
  }).join('');
  return '<div class="funnel">' + rows + '</div>' +
    '<div class="note" style="margin-top:8px">Board-exact snapshot, all ' + esc(d.funnelTotal) + ' opportunities on the pipeline right now (includes internal/test records, same as the live GHL board columns).</div>';
}

function buildPipelineHealthBlock() {
  return '<div class="charts">' + buildTrendCharts() + '</div>' +
    '<h3 class="sub-sec">Whole pipeline, by stage</h3>' + buildFunnel();
}

function buildAuditBlock() {
  const a = d.audit;
  const items = [
    ['Opportunities pulled from the pipeline board', a.totalOpportunitiesPulled],
    ['Excluded as internal/test records', a.excludedTestRecords],
    ['Calls all time by non-closer team members (setters, VAs), excluded from the board', a.nonCloserCallsAllTime],
    ['Cash collected all time not yet attributed to a closer', a.unattributedCashAllTime],
  ];
  return '<table class="audit"><tbody>' + items.map(([l, v]) =>
    '<tr><td>' + esc(l) + '</td><td class="num">' + esc(v) + '</td></tr>'
  ).join('') + '</tbody></table>';
}

let html = fs.readFileSync('index.template.html', 'utf8');

const MARKERS = [
  ['CAREER', buildCareerBanner],
  ['SCORECARD', buildScorecardBlock],
  ['LEADERBOARD', buildLeaderboardBlock],
  ['PIPELINE', buildPipelineHealthBlock],
  ['AUDIT', buildAuditBlock],
];
for (const [name, fn] of MARKERS) {
  const re = new RegExp('<!--' + name + '_START-->[\\s\\S]*?<!--' + name + '_END-->');
  if (!re.test(html)) { console.error('ERROR: ' + name + ' markers not found'); process.exit(1); }
  html = html.replace(re, '<!--' + name + '_START-->' + fn() + '<!--' + name + '_END-->');
}

// --- Live tokens: {%dotted.path%} filled from data.json ---
function flatten(obj, prefix, out) {
  const keys = Array.isArray(obj) ? obj.map((_, i) => i) : Object.keys(obj);
  for (const k of keys) {
    const v = obj[k];
    const key = prefix ? prefix + '.' + k : String(k);
    if (v && typeof v === 'object') {
      flatten(v, key, out);
    } else {
      out[key] = v;
    }
  }
  return out;
}
const T = flatten(d, '', {});
html = html.replace(/\{%\s*([a-zA-Z0-9_.]+)\s*%\}/g, (m, key) => (key in T ? esc(T[key]) : m));
const leftover = html.match(/\{%\s*[a-zA-Z0-9_.]+\s*%\}/g);
if (leftover) {
  console.error('ERROR: unresolved live tokens: ' + [...new Set(leftover)].join(', '));
  process.exit(1);
}

// --- Dash guard: no em/en dashes anywhere in the rendered output ---
const DASH = /[–—]/;
if (DASH.test(html)) {
  console.error('ERROR: em/en dash in rendered output');
  process.exit(1);
}

fs.writeFileSync('index.html', html);
console.log('OK index.html written from data.json (asOf ' + d.asOf + ')');
