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

const COLS = [
  { k: 'name', label: 'Closer', cls: '' },
  { k: 'dealsClosed', label: 'Deals closed', cls: 'num' },
  { k: 'cash', label: 'Cash collected', cls: 'num ok' },
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

function medal(rank) {
  if (rank === 1) return '<span class="medal g">1</span>';
  if (rank === 2) return '<span class="medal s">2</span>';
  if (rank === 3) return '<span class="medal b">3</span>';
  return '<span class="medal">' + rank + '</span>';
}

function buildTable(winKey, rows, totals) {
  const head = '<tr><th></th>' + COLS.map(c => '<th class="' + c.cls + '">' + c.label + '</th>').join('') + '</tr>';
  const body = rows.map(r => {
    const cells = COLS.map(c => {
      const v = c.k === 'name' ? esc(r.name) : esc(r[c.k]);
      return '<td class="' + c.cls + '">' + v + '</td>';
    }).join('');
    return '<tr><td class="rank">' + medal(r.rank) + '</td>' + cells + '</tr>';
  }).join('\n');
  const totalCells = COLS.map(c => {
    if (c.k === 'name') return '<td class="foot">Team total</td>';
    return '<td class="num foot">' + esc(totals[c.k]) + '</td>';
  }).join('');
  const foot = '<tr class="totalrow"><td></td>' + totalCells + '</tr>';
  return '<div class="boardwrap"><table class="board" data-win="' + winKey + '">' +
    '<thead>' + head + '</thead><tbody>' + body + '</tbody><tfoot>' + foot + '</tfoot></table></div>';
}

function buildLeaderboardBlock() {
  const wins = [
    { key: 'day', label: 'Today', windowLabel: d.windows.day.label },
    { key: 'week', label: 'This week', windowLabel: d.windows.week.label },
    { key: 'month', label: 'This month', windowLabel: d.windows.month.label },
  ];
  const tabs = wins.map((w, i) =>
    '<button class="wtab' + (i === 0 ? ' active' : '') + '" data-win="' + w.key + '" onclick="slSwitchWindow(\'' + w.key + '\')">' + w.label + '</button>'
  ).join('');
  const panels = wins.map((w, i) =>
    '<div class="wpanel' + (i === 0 ? ' active' : '') + '" data-win="' + w.key + '">' +
    '<div class="wlabel">' + esc(w.windowLabel) + '</div>' +
    buildTable(w.key, d.leaderboard[w.key], d.totals[w.key]) +
    '</div>'
  ).join('\n');
  const script = '<script>function slSwitchWindow(k){' +
    'document.querySelectorAll(".wtab").forEach(function(b){b.classList.toggle("active", b.dataset.win===k);});' +
    'document.querySelectorAll(".wpanel").forEach(function(p){p.classList.toggle("active", p.dataset.win===k);});' +
    '}</script>';
  return '<div class="wtabs">' + tabs + '</div>' + panels + script;
}

function buildAuditBlock() {
  const a = d.audit;
  const items = [
    ['Opportunities pulled from the pipeline board', a.totalOpportunitiesPulled],
    ['Excluded as internal/test records', a.excludedTestRecords],
    ['Calls this month by non-closer team members (setters, VAs), excluded from the board', a.nonCloserCallsThisMonth],
    ['Cash collected this month not yet attributed to a closer', a.unattributedCashMonth],
  ];
  return '<table class="audit"><tbody>' + items.map(([l, v]) =>
    '<tr><td>' + esc(l) + '</td><td class="num">' + esc(v) + '</td></tr>'
  ).join('') + '</tbody></table>';
}

let html = fs.readFileSync('index.template.html', 'utf8');

// --- Marker region: LEADERBOARD ---
const reLb = /<!--LEADERBOARD_START-->[\s\S]*?<!--LEADERBOARD_END-->/;
if (!reLb.test(html)) { console.error('ERROR: LEADERBOARD markers not found'); process.exit(1); }
html = html.replace(reLb, '<!--LEADERBOARD_START-->' + buildLeaderboardBlock() + '<!--LEADERBOARD_END-->');

// --- Marker region: AUDIT ---
const reAudit = /<!--AUDIT_START-->[\s\S]*?<!--AUDIT_END-->/;
if (!reAudit.test(html)) { console.error('ERROR: AUDIT markers not found'); process.exit(1); }
html = html.replace(reAudit, '<!--AUDIT_START-->' + buildAuditBlock() + '<!--AUDIT_END-->');

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
