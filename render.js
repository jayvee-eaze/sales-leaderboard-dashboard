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
  { k: 'status', label: 'Status', cls: '' },
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

function statusPill(status) {
  return status === 'active' ?
    '<span class="status-pill active">ACTIVE</span>' :
    '<span class="status-pill offboarded">OFFBOARDED</span>';
}

function buildTable(rows, totals) {
  const head = '<tr><th></th>' + COLS.map(c => '<th class="' + c.cls + '">' + c.label + '</th>').join('') + '</tr>';
  const body = rows.map(r => {
    const cells = COLS.map(c => {
      if (c.k === 'trend') return '<td class="' + c.cls + '">' + trendBadge(r.trend, r.trendNote) + '</td>';
      if (c.k === 'status') return '<td class="' + c.cls + '">' + statusPill(r.status) + '</td>';
      const raw = c.k === 'callHours' ? Number(r[c.k]).toFixed(1) : r[c.k];
      const v = c.k === 'name' ? esc(r.name) : esc(raw);
      return '<td class="' + c.cls + '">' + v + '</td>';
    }).join('');
    return '<tr><td class="rank">' + medal(r.rank) + '</td>' + cells + '</tr>';
  }).join('\n');
  const totalCells = COLS.map(c => {
    if (c.k === 'name') return '<td class="foot">Team total</td>';
    if (c.k === 'status') return '<td class="foot"></td>';
    if (c.k === 'trend') return '<td class="num foot">' + trendBadge(totals.trend, totals.trendNote) + '</td>';
    const raw = c.k === 'callHours' ? Number(totals[c.k]).toFixed(1) : totals[c.k];
    return '<td class="num foot">' + esc(raw) + '</td>';
  }).join('');
  const foot = '<tr class="totalrow"><td></td>' + totalCells + '</tr>';
  return '<div class="boardwrap"><table class="board">' +
    '<thead>' + head + '</thead><tbody>' + body + '</tbody><tfoot>' + foot + '</tfoot></table></div>';
}

// Shared toggle: which roster view the Full Detail table shows. Both variants are
// pre-rendered server-side (no client-side number computation); the toggle only shows or
// hides pre-built markup, exactly like the window toggle.
function buildRosterTabs() {
  const script = '<script>function slSwitchRoster(k){' +
    'document.querySelectorAll(".rtab").forEach(function(b){b.classList.toggle("active", b.dataset.roster===k);});' +
    'document.querySelectorAll(".rosterpanel").forEach(function(p){p.classList.toggle("active", p.dataset.roster===k);});' +
    '}</script>';
  return '<div class="rtabs">' +
    '<button class="rtab active" data-roster="active" onclick="slSwitchRoster(\'active\')">Active Closer</button>' +
    '<button class="rtab" data-roster="all" onclick="slSwitchRoster(\'all\')">All Closer</button>' +
    '</div>' + script;
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
    const podium = d.leaderboard[w.key].map(buildPodiumCard).join('');
    const activeTable = buildTable(d.leaderboard[w.key], d.activeTotals[w.key]);
    const allTable = buildTable(d.leaderboardAll[w.key], d.totals[w.key]);
    return '<div class="wpanel' + (w.key === DEFAULT_WIN ? ' active' : '') + '" data-win="' + w.key + '">' +
      '<div class="wlabel">' + esc(d.windows[w.key].label) + '</div>' +
      '<div class="podium">' + podium + '</div>' +
      '<div class="detailhd"><h3 class="sub-sec">Full detail</h3>' + buildRosterTabs() + '</div>' +
      '<div class="rosterpanel active" data-roster="active">' + activeTable + '</div>' +
      '<div class="rosterpanel" data-roster="all">' + allTable + '</div>' +
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

const CHART_W = 700, CHART_H = 150, CHART_PAD_L = 6, CHART_PAD_R = 6, CHART_PAD_B = 18, CHART_PAD_T = 20;
const CHART_INNER_W = CHART_W - CHART_PAD_L - CHART_PAD_R;
const CHART_INNER_H = CHART_H - CHART_PAD_T - CHART_PAD_B;

function svgBarChart(rows, valueKey, opts) {
  const max = Math.max(1, ...rows.map(r => r[valueKey]));
  const bw = CHART_INNER_W / rows.length;
  const peakIdx = rows.reduce((best, r, i) => (r[valueKey] > rows[best][valueKey] ? i : best), 0);
  const bars = rows.map((r, i) => {
    const v = r[valueKey];
    const bh = (v / max) * CHART_INNER_H;
    const x = CHART_PAD_L + i * bw + bw * 0.15;
    const y = CHART_PAD_T + CHART_INNER_H - bh;
    const w = bw * 0.7;
    const dateLbl = (i % 4 === 0 || i === rows.length - 1) ?
      '<text x="' + (x + w / 2).toFixed(1) + '" y="' + (CHART_H - 4) + '" font-size="9" fill="#94A3B8" text-anchor="middle">' + esc(r.date.slice(5)) + '</text>' : '';
    const peakLbl = (i === peakIdx && v > 0) ?
      '<text x="' + (x + w / 2).toFixed(1) + '" y="' + (y - 5).toFixed(1) + '" font-size="10" font-weight="700" fill="' + (opts.color || '#3B82F6') + '" text-anchor="middle">' + esc(String(v)) + '</text>' : '';
    const title = '<title>' + esc(r.date) + ': ' + esc(String(v)) + '</title>';
    return '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + Math.max(bh, v > 0 ? 2 : 0).toFixed(1) + '" fill="' + (opts.color || '#3B82F6') + '" rx="2">' + title + '</rect>' + peakLbl + dateLbl;
  }).join('');
  return '<svg viewBox="0 0 ' + CHART_W + ' ' + CHART_H + '" class="chart">' + bars + '</svg>';
}

function svgLineChart(rows, valueKey, opts) {
  const max = opts.max || Math.max(1, ...rows.map(r => r[valueKey] || 0));
  const step = CHART_INNER_W / Math.max(1, rows.length - 1);
  const pt = (i, v) => [CHART_PAD_L + i * step, CHART_PAD_T + CHART_INNER_H - (v / max) * CHART_INNER_H];
  let segs = [], cur = [];
  rows.forEach((r, i) => {
    const v = r[valueKey];
    if (v === null || v === undefined) {
      if (cur.length) segs.push(cur);
      cur = [];
    } else {
      cur.push({ i, v, xy: pt(i, v) });
    }
  });
  if (cur.length) segs.push(cur);
  const baseline = CHART_PAD_T + CHART_INNER_H;
  const areas = opts.fill ? segs.map(seg => {
    const pts = seg.map(p => p.xy[0].toFixed(1) + ',' + p.xy[1].toFixed(1)).join(' ');
    const first = seg[0].xy[0].toFixed(1), last = seg[seg.length - 1].xy[0].toFixed(1);
    return '<polygon points="' + first + ',' + baseline + ' ' + pts + ' ' + last + ',' + baseline + '" fill="' + (opts.color || '#3B82F6') + '" opacity="0.1"/>';
  }).join('') : '';
  const lines = segs.map(seg =>
    '<polyline points="' + seg.map(p => p.xy[0].toFixed(1) + ',' + p.xy[1].toFixed(1)).join(' ') + '" fill="none" stroke="' + (opts.color || '#3B82F6') + '" stroke-width="2"/>' +
    seg.map(p => '<circle cx="' + p.xy[0].toFixed(1) + '" cy="' + p.xy[1].toFixed(1) + '" r="2.5" fill="' + (opts.color || '#3B82F6') + '"/>').join('')
  ).join('');
  const refLine = (opts.refValue !== undefined) ? (function () {
    const y = CHART_PAD_T + CHART_INNER_H - (opts.refValue / max) * CHART_INNER_H;
    return '<line x1="' + CHART_PAD_L + '" y1="' + y.toFixed(1) + '" x2="' + (CHART_W - CHART_PAD_R) + '" y2="' + y.toFixed(1) + '" stroke="#94A3B8" stroke-width="1" stroke-dasharray="4,3"/>' +
      '<text x="' + (CHART_W - CHART_PAD_R) + '" y="' + (y - 4).toFixed(1) + '" font-size="9" fill="#94A3B8" text-anchor="end">' + esc(opts.refLabel || '') + '</text>';
  })() : '';
  const flat = segs.flat();
  const peak = flat.length ? flat.reduce((best, p) => (p.v > best.v ? p : best), flat[0]) : null;
  const peakLbl = peak ? '<text x="' + peak.xy[0].toFixed(1) + '" y="' + (peak.xy[1] - 8).toFixed(1) + '" font-size="10" font-weight="700" fill="' + (opts.color || '#3B82F6') + '" text-anchor="middle">' + esc(opts.peakFormat ? opts.peakFormat(peak.v) : String(Math.round(peak.v))) + '</text>' : '';
  const labels = rows.map((r, i) => (i % 4 === 0 || i === rows.length - 1) ?
    '<text x="' + pt(i, 0)[0].toFixed(1) + '" y="' + (CHART_H - 4) + '" font-size="9" fill="#94A3B8" text-anchor="middle">' + esc(r.date.slice(5)) + '</text>' : '').join('');
  return '<svg viewBox="0 0 ' + CHART_W + ' ' + CHART_H + '" class="chart">' + refLine + areas + lines + peakLbl + labels + '</svg>';
}

// Step-area chart: correct for a running total, which does not go back down and should
// never read as "new value earned every day" the way discrete bars would.
function svgStepArea(rows, valueKey, opts) {
  const max = Math.max(1, ...rows.map(r => r[valueKey]));
  const step = CHART_INNER_W / Math.max(1, rows.length - 1);
  const x = i => CHART_PAD_L + i * step;
  const y = v => CHART_PAD_T + CHART_INNER_H - (v / max) * CHART_INNER_H;
  const baseline = CHART_PAD_T + CHART_INNER_H;
  let pts = [[x(0), y(rows[0][valueKey])]];
  for (let i = 1; i < rows.length; i++) {
    pts.push([x(i), y(rows[i - 1][valueKey])]);
    pts.push([x(i), y(rows[i][valueKey])]);
  }
  const lineStr = pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
  const areaStr = x(0).toFixed(1) + ',' + baseline + ' ' + lineStr + ' ' + x(rows.length - 1).toFixed(1) + ',' + baseline;
  const last = rows[rows.length - 1][valueKey];
  const peakLbl = '<text x="' + x(rows.length - 1).toFixed(1) + '" y="' + (y(last) - 8).toFixed(1) + '" font-size="10" font-weight="700" fill="' + (opts.color || '#059669') + '" text-anchor="end">' + esc(opts.peakFormat ? opts.peakFormat(last) : String(last)) + '</text>';
  const labels = rows.map((r, i) => (i % 4 === 0 || i === rows.length - 1) ?
    '<text x="' + x(i).toFixed(1) + '" y="' + (CHART_H - 4) + '" font-size="9" fill="#94A3B8" text-anchor="middle">' + esc(r.date.slice(5)) + '</text>' : '').join('');
  return '<svg viewBox="0 0 ' + CHART_W + ' ' + CHART_H + '" class="chart">' +
    '<polygon points="' + areaStr + '" fill="' + (opts.color || '#059669') + '" opacity="0.12"/>' +
    '<polyline points="' + lineStr + '" fill="none" stroke="' + (opts.color || '#059669') + '" stroke-width="2"/>' +
    peakLbl + labels + '</svg>';
}

function buildChartCard(title, note, chartHtml) {
  return '<div class="chartcard"><div class="charthd">' + esc(title) + '</div>' + chartHtml +
    '<div class="chartnote">' + esc(note) + '</div></div>';
}

function buildPipelineKpis() {
  const ins = d.dailyInsights;
  const tiles = [
    { v: ins.totalCallsBooked, l: 'Calls booked, all time' },
    { v: ins.bestDay ? (ins.bestDay.value + ' (' + ins.bestDay.label + ')') : 'n/a', l: 'Best single day' },
    { v: ins.activeDays + ' of ' + ins.totalDays, l: 'Active days since launch' },
    { v: d.totals.allTime.cash, l: 'Cash collected, all time' },
  ];
  return '<div class="tiles">' + tiles.map(t =>
    '<div class="tile"><div class="tv">' + esc(t.v) + '</div><div class="tl">' + esc(t.l) + '</div></div>'
  ).join('') + '</div>';
}

function buildTrendCharts() {
  const daily = d.daily;
  const ins = d.dailyInsights;
  const showRateRows = daily.map(r => ({ date: r.date, pct: (r.showed + r.noShow) > 0 ? Math.round(100 * r.showed / (r.showed + r.noShow)) : null }));
  let cum = 0;
  const cumCash = daily.map(r => { cum += r.cashCents; return { date: r.date, cum: cum / 100 }; });
  return (
    buildChartCard('Calls booked per day, since launch', ins.callsBookedNote,
      svgBarChart(daily, 'callsBooked', { color: '#3B82F6' })) +
    buildChartCard('Show rate per day (blank = no calls resolved that day)', ins.showRateNote,
      svgLineChart(showRateRows, 'pct', { color: '#059669', max: 100, fill: true, refValue: 50, refLabel: '50%', peakFormat: v => Math.round(v) + '%' })) +
    buildChartCard('Cumulative cash collected, since launch', ins.cashNote,
      svgStepArea(cumCash, 'cum', { color: '#059669', peakFormat: v => '$' + v.toLocaleString() }))
  );
}

function buildFunnel() {
  const fins = d.funnelInsights;
  const max = Math.max(1, ...d.funnel.map(f => f.count));
  const rows = d.funnel.map(f => {
    const pctW = Math.max(2, Math.round(100 * f.count / max));
    return '<div class="frow"><div class="flabel">' + esc(f.label) + '</div>' +
      '<div class="fbarwrap"><div class="fbar" style="width:' + pctW + '%"></div></div>' +
      '<div class="fcount">' + esc(f.count) + '<span class="fpct">' + esc(f.pct) + '</span></div></div>';
  }).join('');
  return '<div class="funnel">' + rows + '</div>' +
    '<div class="funnel-insights">' +
    '<div class="finsight">' + esc(fins.leadNote) + '</div>' +
    '<div class="finsight">' + esc(fins.closeNote) + '</div>' +
    '</div>' +
    '<div class="note" style="margin-top:10px">Board-exact snapshot, all ' + esc(d.funnelTotal) + ' opportunities on the pipeline right now (includes internal/test records, same as the live GHL board columns).</div>';
}

function buildPipelineHealthBlock() {
  return buildPipelineKpis() +
    '<h3 class="sub-sec">Trends since launch</h3>' +
    '<div class="charts">' + buildTrendCharts() + '</div>' +
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
  if (a.offboardedClosers && a.offboardedClosers.length) {
    items.push(['Offboarded (' + a.offboardedClosers.join(', ') + '): deals closed, included in team totals but not ranked', a.offboardedDealsAllTime]);
    items.push(['Offboarded (' + a.offboardedClosers.join(', ') + '): cash collected, included in team totals but not ranked', a.offboardedCashAllTime]);
  }
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
