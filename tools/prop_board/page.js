(function () {
  var D = DATA, T = D.teams;
  var CUR = D.thru.season, PREV = CUR - 1;
  var $ = function (id) { return document.getElementById(id); };
  var M = {
    pass_yds: { l: 'Passing yards', f: function (g) { return g[7]; }, ks: ['pass_yds'] },
    pass_att: { l: 'Pass attempts', f: function (g) { return g[5]; }, ks: ['pass_att'] },
    pass_cmp: { l: 'Completions', f: function (g) { return g[6]; }, ks: ['pass_cmp'] },
    pass_td: { l: 'Passing TDs', f: function (g) { return g[8]; }, ks: ['pass_td'] },
    rush_yds: { l: 'Rushing yards', f: function (g) { return g[11]; }, ks: ['rush_yds'] },
    rush_att: { l: 'Carries', f: function (g) { return g[10]; }, ks: ['rush_att'] },
    rec: { l: 'Receptions', f: function (g) { return g[14]; }, ks: ['rec'] },
    rec_yds: { l: 'Receiving yards', f: function (g) { return g[15]; }, ks: ['rec_yds'] },
    tgt: { l: 'Targets', f: function (g) { return g[13]; }, ks: ['tgt'] },
    rr_yds: { l: 'Rush + rec yards', f: function (g) { return g[11] + g[15]; }, ks: ['rush_yds', 'rec_yds'] },
    any_td: { l: 'Rush + rec TDs (0.5 = anytime)', f: function (g) { return g[12] + g[16]; }, ks: ['rush_td', 'rec_td'] }
  };
  var BY_POS = {
    QB: ['pass_yds', 'pass_att', 'pass_cmp', 'pass_td', 'rush_yds'],
    RB: ['rush_yds', 'rush_att', 'rec', 'rec_yds', 'rr_yds', 'any_td'],
    WR: ['rec_yds', 'rec', 'tgt', 'any_td'],
    TE: ['rec_yds', 'rec', 'tgt', 'any_td']
  };
  var DEFAULT_STAT = { QB: 'pass_yds', RB: 'rush_yds', WR: 'rec_yds', TE: 'rec_yds' };
  var USAGE = [['tgt', 'Targets'], ['rush_att', 'Carries'], ['pass_att', 'Pass attempts'], ['rec', 'Receptions'], ['rec_yds', 'Receiving yards'], ['rush_yds', 'Rushing yards'], ['pass_yds', 'Passing yards'], ['tsh', 'Target share']];
  var USAGE_FN = { tsh: function (g) { return g[17] / 10; } };
  var MIN_BASE = { tgt: 3, rush_att: 6, pass_att: 15, rec: 2, rec_yds: 20, rush_yds: 20, pass_yds: 120, tsh: 8 };
  var USAGE_POS = { tgt: ['RB', 'WR', 'TE'], tsh: ['RB', 'WR', 'TE'], rush_att: ['QB', 'RB'], pass_att: ['QB'], pass_yds: ['QB'], rush_yds: ['QB', 'RB'], rec: ['RB', 'WR', 'TE'], rec_yds: ['RB', 'WR', 'TE'] };

  function fmt(n, d) { return (Math.round(n * Math.pow(10, d || 0)) / Math.pow(10, d || 0)).toFixed(d || 0); }
  function avg(a) { return a.length ? a.reduce(function (x, y) { return x + y; }, 0) / a.length : NaN; }
  function median(a) { if (!a.length) return NaN; var s = a.slice().sort(function (x, y) { return x - y; }), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; }
  function ord(n) { var s = ['th', 'st', 'nd', 'rd'], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  /* player lookups */
  var P = D.players, byLabel = {}, byId = {};
  function label(p) { return p.n + ' (' + p.p + ', ' + T[p.t] + ')'; }
  function volume26(p) { return p.g.filter(function (g) { return g[0] === CUR; }).reduce(function (s, g) { return s + g[5] + g[10] + g[13]; }, 0); }
  P.forEach(function (p) { p.vol = volume26(p); byLabel[label(p).toLowerCase()] = p; byId[p.id] = p; });
  var sorted = P.slice().sort(function (a, b) { return b.vol - a.vol; });
  $('players').innerHTML = sorted.map(function (p) { return '<option value="' + esc(label(p)) + '"></option>'; }).join('');
  $('bwk').textContent = D.next.week; $('stamp').innerHTML = 'Through <b>' + CUR + ' week ' + D.thru.week + '</b> &middot; source nflverse &middot; week ' + D.next.week + ' slate loaded';

  /* allowed-per-game rank */
  function allowedVal(m, pos, opp) {
    var yr = D.allowed[CUR] && D.allowed[CUR][pos] && D.allowed[CUR][pos][opp] && D.allowed[CUR][pos][opp].n >= 3 ? CUR : PREV;
    var d = D.allowed[yr] && D.allowed[yr][pos] && D.allowed[yr][pos][opp];
    if (!d) return null;
    return { v: M[m].ks.reduce(function (s, k) { return s + d[k]; }, 0), yr: yr };
  }
  function allowedRank(m, pos, opp) {
    var me = allowedVal(m, pos, opp); if (!me) return null;
    var all = [];
    Object.keys(D.allowed[me.yr][pos]).forEach(function (t) { var a = allowedVal(m, pos, +t); if (a && a.yr === me.yr) all.push(a.v); });
    all.sort(function (a, b) { return b - a; });
    return { v: me.v, rank: all.indexOf(me.v) + 1, of: all.length, yr: me.yr };
  }
  function nextGame(p) { return p.g.length && p.g[p.g.length - 1][0] === CUR ? (D.next.games[p.t] || null) : null; }

  /* ---------- player view ---------- */
  var cur = null, tipEl;
  function setPlayer(p, keepStat) {
    cur = p;
    $('q').value = label(p);
    var opts = BY_POS[p.p];
    var prev = $('stat').value;
    $('stat').innerHTML = opts.map(function (k) { return '<option value="' + k + '">' + M[k].l + '</option>'; }).join('');
    $('stat').value = keepStat && opts.indexOf(prev) >= 0 ? prev : DEFAULT_STAT[p.p];
    if (!keepStat) $('line').value = '';
    renderPlayer();
  }
  function windowGames(p, w) {
    var g = p.g;
    if (w === 'l5') return g.slice(-5);
    if (w === 'l10') return g.slice(-10);
    if (w === 'y26') return g.filter(function (x) { return x[0] === CUR; });
    return g.filter(function (x) { return x[0] === PREV; });
  }
  function tally(vals, line) {
    var o = 0, pu = 0, u = 0;
    vals.forEach(function (v) { if (v > line) o++; else if (v === line) pu++; else u++; });
    return { o: o, p: pu, u: u, n: vals.length };
  }
  function parseLine() { var s = $('line').value.trim(); if (s === '') return null; var n = parseFloat(s); return isFinite(n) ? n : null; }

  function renderPlayer() {
    var p = cur; if (!p) return;
    var m = $('stat').value, f = M[m].f, line = parseLine();
    var games = windowGames(p, $('win').value), vals = games.map(f);
    var active = p.g.length && p.g[p.g.length - 1][0] === CUR, nx = active ? nextGame(p) : null, html = '';
    html += '<div class="who"><h2>' + esc(p.n) + '</h2><span class="meta">' + p.p + ' &middot; ' + T[p.t] + '</span></div>';
    if (nx) {
      var ar = allowedRank(m, p.p, nx.o), fav = nx.f;
      html += '<div class="next"><span>Week ' + D.next.week + ': <b>' + (nx.h ? 'vs ' : 'at ') + T[nx.o] + '</b></span><span>' + esc(nx.d) + ' ' + esc(nx.t) + ' ET</span>';
      if (fav !== null) html += '<span>' + (fav > 0 ? 'Favored by ' + fav : (fav < 0 ? 'Underdog by ' + (-fav) : 'Pick&rsquo;em')) + '</span>';
      if (nx.tot !== null) html += '<span>Game total <b>' + nx.tot + '</b></span>';
      if (ar) html += '<span>' + T[nx.o] + ' allows <b>' + fmt(ar.v, 1) + '</b> to ' + p.p + 's per game (' + ord(ar.rank) + ' most of ' + ar.of + (ar.yr !== CUR ? ', ' + ar.yr + ' data' : '') + ')</span>';
      html += '</div>';
    } else if (!active) {
      html += '<div class="next"><span>No ' + CUR + ' games yet, so no week ' + D.next.week + ' matchup is shown.</span></div>';
    } else {
      html += '<div class="next"><span>' + T[p.t] + ' has no game in week ' + D.next.week + ' (bye).</span></div>';
    }
    var med = median(vals), suggested = isFinite(med) ? (Math.floor(med) + 0.5) : null;
    html += '<div class="hits">';
    if (line === null) {
      html += '<div class="hit"><span class="lab">Average</span><span class="big">' + (vals.length ? fmt(avg(vals), 1) : '-') + '</span><span class="sub">' + vals.length + ' games</span></div>';
      html += '<div class="hit"><span class="lab">Median</span><span class="big">' + (vals.length ? fmt(med, 1) : '-') + '</span><span class="sub">middle game</span></div>';
      html += '<div class="hit"><span class="lab">High / low</span><span class="big">' + (vals.length ? Math.max.apply(null, vals) + ' / ' + Math.min.apply(null, vals) : '-') + '</span><span class="sub">in this window</span></div>';
    } else {
      [['Last 5', 'l5'], ['Last 10', 'l10'], [CUR + ' season', 'y26'], [PREV + ' season', 'y25']].forEach(function (w) {
        var t = tally(windowGames(p, w[1]).map(f), line);
        var pct = t.n ? Math.round(t.o / t.n * 100) + '%' : '-';
        html += '<div class="hit"><span class="lab">Over, ' + w[0] + '</span><span class="big">' + pct + '</span><span class="sub">' + t.o + ' of ' + t.n + (t.p ? ', ' + t.p + ' push' : '') + '</span></div>';
      });
      html += '<div class="hit"><span class="lab">Average</span><span class="big">' + (vals.length ? fmt(avg(vals), 1) : '-') + '</span><span class="sub">median ' + (vals.length ? fmt(med, 1) : '-') + '</span></div>';
    }
    html += '</div>';
    if (line === null && suggested !== null) {
      html += '<p class="note">Enter the book&rsquo;s line above to see hit rates. For a starting point, the median of this window is ' + fmt(med, 1) + ': <button type="button" class="chip" id="usemed">Try ' + suggested + '</button> (not a book line).</p>';
    }
    html += '<div class="legend">' + (line === null
      ? '<span><i class="sw" style="background:var(--accent)"></i>Game result</span>'
      : '<span><i class="sw" style="background:var(--accent)"></i>Over ' + line + '</span><span><i class="sw" style="background:var(--under)"></i>At or under</span><span><i class="sw" style="background:transparent;border-top:2px dashed var(--ink);height:0;width:16px;vertical-align:3px"></i>Line</span>')
      + '<span>' + esc(M[m].l) + ', each bar is one game (week, opponent)</span></div>';
    html += '<div class="chartbox" id="chartbox">' + chart(games, vals, line) + '<div class="tip" id="tip" hidden></div></div>';
    html += '<div class="tablewrap"><table><thead><tr><th>Season</th><th>Wk</th><th>Opp</th><th class="n">' + esc(M[m].l) + '</th>' + (line === null ? '' : '<th>vs line</th>') + '<th class="n">Tgt share</th></tr></thead><tbody>' +
      games.slice().reverse().map(function (g) {
        var v = f(g), rel = line === null ? '' : '<td>' + (v > line ? '<span class="up">&#9650; Over</span>' : (v === line ? 'Push' : '<span class="down">&#9660; Under</span>')) + '</td>';
        return '<tr><td>' + g[0] + (g[2] ? ' post' : '') + '</td><td>' + g[1] + '</td><td>' + T[g[4]] + (g[3] !== p.t ? ' <span style="color:var(--muted)">(with ' + T[g[3]] + ')</span>' : '') + '</td><td class="n">' + v + '</td>' + rel + '<td class="n">' + (g[17] ? fmt(g[17] / 10, 1) + '%' : '-') + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    $('pcard').innerHTML = html;
    var um = $('usemed'); if (um) um.addEventListener('click', function () { $('line').value = suggested; renderPlayer(); });
    bindTips();
  }

  function chart(games, vals, line) {
    if (!games.length) return '<p class="note">No games in this window.</p>';
    var W = 720, H = 250, L = 38, R = 74, Tm = 16, B = 40;
    var mx = Math.max.apply(null, vals.concat(line === null ? [1] : [line, 1])) * 1.15;
    var step = niceStep(mx / 4), top = Math.ceil(mx / step) * step;
    var iw = W - L - R, ih = H - Tm - B, n = games.length, slot = iw / n, bw = Math.min(46, slot * 0.66);
    var y = function (v) { return Tm + ih - v / top * ih; };
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Game by game bar chart">';
    for (var t = 0; t <= top + 1e-9; t += step) s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(t) + '" y2="' + y(t) + '" stroke="var(--line)" stroke-width="1"/><text x="' + (L - 6) + '" y="' + (y(t) + 4) + '" text-anchor="end">' + (step < 1 ? fmt(t, 1) : Math.round(t)) + '</text>';
    games.forEach(function (g, i) {
      var v = vals[i], x = L + slot * i + (slot - bw) / 2, hh = Math.max(0, ih - (y(v) - Tm)), over = line !== null && v > line;
      var fill = line === null ? 'var(--accent)' : (over ? 'var(--accent)' : 'var(--under)');
      var tip = g[0] + ' wk ' + g[1] + ' vs ' + T[g[4]] + ': ' + v;
      s += '<g class="bar" data-tip="' + esc(tip) + '"><title>' + esc(tip) + '</title><rect x="' + x + '" y="' + y(v) + '" width="' + bw + '" height="' + hh + '" rx="3" fill="' + fill + '"/>' +
        '<rect x="' + (L + slot * i) + '" y="' + Tm + '" width="' + slot + '" height="' + ih + '" fill="transparent"/></g>';
      if (n <= 12) s += '<text class="val" x="' + (x + bw / 2) + '" y="' + (y(v) - 5) + '" text-anchor="middle">' + v + '</text>';
      s += '<text x="' + (x + bw / 2) + '" y="' + (H - 22) + '" text-anchor="middle">' + g[1] + (g[2] ? 'p' : '') + '</text><text x="' + (x + bw / 2) + '" y="' + (H - 9) + '" text-anchor="middle">' + T[g[4]] + '</text>';
      if (i > 0 && games[i - 1][0] !== g[0]) s += '<line x1="' + (L + slot * i) + '" x2="' + (L + slot * i) + '" y1="' + Tm + '" y2="' + (H - B + 4) + '" stroke="var(--muted)" stroke-dasharray="2 4"/><text x="' + (L + slot * i + 4) + '" y="' + (Tm + 10) + '">' + g[0] + '</text>';
    });
    if (line !== null) s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(line) + '" y2="' + y(line) + '" stroke="var(--ink)" stroke-width="2" stroke-dasharray="6 4"/><text class="val" y="' + (y(line) + 4) + '" x="' + (W - R + 6) + '" text-anchor="start">line ' + line + '</text>';
    return s + '</svg>';
  }
  function niceStep(r) { if (r <= 0) return 1; var p = Math.pow(10, Math.floor(Math.log(r) / Math.LN10)), f = r / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; }
  function bindTips() {
    var box = $('chartbox'); if (!box) return; var tip = $('tip');
    box.querySelectorAll('.bar').forEach(function (b) {
      b.addEventListener('pointermove', function (e) {
        var r = box.getBoundingClientRect();
        tip.textContent = b.getAttribute('data-tip'); tip.hidden = false;
        tip.style.left = Math.min(e.clientX - r.left + 12 + box.scrollLeft, box.scrollWidth - 160) + 'px'; tip.style.top = (e.clientY - r.top - 34) + 'px';
      });
      b.addEventListener('pointerleave', function () { tip.hidden = true; });
    });
  }

  /* ---------- trend board ---------- */
  USAGE.forEach(function (u) { var o = document.createElement('option'); o.value = u[0]; o.textContent = u[1]; $('bmet').appendChild(o); });
  function usageFn(k) { return USAGE_FN[k] || (M[k] ? M[k].f : null); }
  function renderBoard() {
    syncBoardMetrics();
    var k = $('bmet').value, pos = $('bpos').value, dir = $('bdir').value, minG = +$('bmin').value, fn = usageFn(k), rows = [];
    P.forEach(function (p) {
      if (pos && p.p !== pos) return;
      if (USAGE_POS[k].indexOf(p.p) < 0) return;
      if ($('bplay').checked && !nextGame(p)) return;
      var g26 = p.g.filter(function (g) { return g[0] === CUR && !g[2]; }), g25 = p.g.filter(function (g) { return g[0] === PREV && !g[2]; });
      if (g26.length < minG || g25.length < 8) return;
      var base = avg(g25.map(fn)); if (!(base >= MIN_BASE[k])) return;
      var l3 = avg(g26.slice(-3).map(fn)), s26 = avg(g26.map(fn));
      rows.push({ p: p, base: base, l3: l3, s26: s26, ch: (l3 - base) / base, n: g26.length });
    });
    rows.sort(function (a, b) { return dir === 'up' ? b.ch - a.ch : a.ch - b.ch; });
    rows = rows.slice(0, 40);
    var d = k === 'tsh' ? 1 : 1, uom = k === 'tsh' ? '%' : '';
    $('bnote').textContent = 'Last 3 games of ' + CUR + ' against each player’s ' + PREV + ' regular-season per-game average. Needs ' + minG + '+ games this year and 8+ last year, so rookies and new starters are not listed. Click a row to open the player.';
    $('btable').innerHTML = '<thead><tr><th>Player</th><th>Team</th><th class="n">Last 3</th><th class="n">' + CUR + ' avg</th><th class="n">' + PREV + ' avg</th><th class="n">Change</th><th>Next</th></tr></thead><tbody>' +
      (rows.length ? rows.map(function (r, i) {
        var nx = nextGame(r.p), mkey = BY_POS[r.p.p].indexOf(k) >= 0 ? k : null;
        var nextTxt = nx ? (nx.h ? 'vs ' : 'at ') + T[nx.o] : 'Bye';
        var up = r.ch >= 0;
        return '<tr class="pick" tabindex="0" data-id="' + r.p.id + '" data-m="' + k + '"><td><b>' + esc(r.p.n) + '</b> <span style="color:var(--muted)">' + r.p.p + '</span></td><td>' + T[r.p.t] + '</td><td class="n">' + fmt(r.l3, d) + uom + '</td><td class="n">' + fmt(r.s26, d) + uom + '</td><td class="n">' + fmt(r.base, d) + uom + '</td><td class="n ' + (up ? 'up' : 'down') + '">' + (up ? '&#9650; +' : '&#9660; ') + Math.round(r.ch * 100) + '%</td><td>' + nextTxt + '</td></tr>';
      }).join('') : '<tr><td colspan="7">No players match these filters.</td></tr>') + '</tbody>';
    $('btable').querySelectorAll('tr.pick').forEach(function (tr) {
      function open() {
        var p = byId[tr.getAttribute('data-id')], k2 = tr.getAttribute('data-m');
        showTab('player'); setPlayer(p, false);
        if (BY_POS[p.p].indexOf(k2) >= 0) { $('stat').value = k2; renderPlayer(); }
        window.scrollTo(0, 0);
      }
      tr.addEventListener('click', open);
      tr.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    });
  }

  /* ---------- wiring ---------- */
  function showTab(name) {
    ['player', 'board'].forEach(function (t) {
      $('panel-' + t).hidden = t !== name; $('tab-' + t).setAttribute('aria-selected', t === name ? 'true' : 'false');
    });
  }
  $('tab-player').addEventListener('click', function () { showTab('player'); });
  $('tab-board').addEventListener('click', function () { showTab('board'); renderBoard(); });
  function norm(s) { return s.toLowerCase().replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim(); }
  P.forEach(function (p) { p.nn = norm(p.n); });
  function findPlayer(txt) {
    var exact = byLabel[txt.trim().toLowerCase()]; if (exact) return exact;
    var q = norm(txt.replace(/\(.*$/, '')); if (q.length < 2) return null;
    var starts = P.filter(function (p) { return p.nn.indexOf(q) === 0 || p.nn.split(' ').slice(1).join(' ').indexOf(q) === 0; });
    var pool = starts.length ? starts : P.filter(function (p) { return p.nn.indexOf(q) >= 0; });
    pool.sort(function (a, b) { return b.vol - a.vol; });
    return pool[0] || null;
  }
  function pickFromBox() { var p = findPlayer($('q').value); if (p) setPlayer(p, false); }
  $('q').addEventListener('input', function () { var p = byLabel[$('q').value.trim().toLowerCase()]; if (p) setPlayer(p, false); });
  $('q').addEventListener('change', pickFromBox);
  $('q').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); pickFromBox(); $('q').blur(); } });
  $('stat').addEventListener('change', function () { $('line').value = ''; renderPlayer(); });
  $('win').addEventListener('change', renderPlayer);
  $('line').addEventListener('input', renderPlayer);
  ['bpos', 'bmet', 'bdir', 'bmin', 'bplay'].forEach(function (id) { $(id).addEventListener('change', renderBoard); });
  function syncBoardMetrics() {
    var pos = $('bpos').value, keep = $('bmet').value;
    Array.prototype.forEach.call($('bmet').options, function (o) { o.hidden = pos && USAGE_POS[o.value].indexOf(pos) < 0; o.disabled = o.hidden; });
    if ($('bmet').selectedOptions[0].disabled) { for (var i = 0; i < $('bmet').options.length; i++) if (!$('bmet').options[i].disabled) { $('bmet').selectedIndex = i; break; } }
  }
  var start = sorted.filter(function (p) { return p.p === 'WR' && nextGame(p); })[0] || sorted[0];
  setPlayer(start, false);
  $('bmet').value = 'tgt';
})();
