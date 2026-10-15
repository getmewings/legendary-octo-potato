"""MLB Elo + starting-pitcher model vs market.

Usage: python3 -I tools/mlb_model.py
       python3 -I tools/mlb_model.py --finals YYYY-MM-DD     (ET date; finals with gamePk)

Data: MLB StatsAPI (results + probable pitchers), SBR money-line page (prices).
Model: team Elo (home field, carry between seasons) plus a starting-pitcher term.
Pitcher quality is walk-forward only: runs the pitcher's team allowed in his
earlier starts, shrunk toward the league mean, half-decayed each new season.
No future data is ever used for a game. The pitcher weight c (Elo per run) is tuned
on seasons before the last full season, and scored out of sample on that season
against the same model with c = 0, so the pitcher term has to earn its place.

Guards:
  * both probable pitchers must be listed, else no call (PENDING)
  * a call is void if a named pitcher does not start
  * model/market gap above 8 pts -> no call; price band -300..+300
  * only games starting later today by the America/New_York calendar
"""
import json, math, re, subprocess, sys, statistics as st, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from itertools import product
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
NOW = dt.datetime.now(dt.timezone.utc)
YEAR = NOW.year
FIRST = YEAR - 4
PRIOR_STARTS = 12
DISAGREE_CAP = 0.08
BAND = (-300, 300)
imp = lambda o: -o / (-o + 100) if o < 0 else 100 / (o + 100)
dec = lambda o: 1 + 100 / -o if o < 0 else 1 + o / 100
ALIAS = {"oaklandathletics": "athletics", "sacramentoathletics": "athletics", "lasvegasathletics": "athletics"}
def canon(s):
    n = re.sub(r"[^a-z0-9]", "", s.lower())
    return ALIAS.get(n, n)

FETCH_FAILURES = []
def get(url, need=None):
    for _ in range(4):
        r = subprocess.run(["curl", "-sS", "--compressed", "-m", "60", "-A", "Mozilla/5.0", url], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            if need is None or need in d:
                return d
        except Exception:
            pass
    FETCH_FAILURES.append(url)
    return None

def sched(a, b, extra=""):
    return get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={a}&endDate={b}&hydrate=probablePitcher{extra}", need="dates")

def pp(side):
    p = side.get("probablePitcher")
    return (p["id"], p["fullName"]) if p else (None, None)

if "--finals" in sys.argv:
    day = sys.argv[sys.argv.index("--finals") + 1]
    d = sched(day, day)
    for dd in (d or {}).get("dates", []):
        for g in dd["games"]:
            if g["status"]["abstractGameState"] == "Final":
                print(f"{day} gamePk {g['gamePk']} {g['teams']['away']['team']['name']} {g['teams']['away'].get('score')} @ "
                      f"{g['teams']['home']['team']['name']} {g['teams']['home'].get('score')}  SP {pp(g['teams']['away'])[1]} / {pp(g['teams']['home'])[1]}")
    sys.exit()

def fetch_games():
    jobs = []
    for y in range(FIRST, YEAR + 1):
        for m in range(3, 11):
            a = dt.date(y, m, 1)
            b = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
            jobs.append((a, b))
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda j: sched(j[0], j[1]), jobs))
    games = {}
    for d in res:
        for dd in (d or {}).get("dates", []):
            for g in dd["games"]:
                if g["gameType"] != "R" or g["status"]["abstractGameState"] != "Final":
                    continue
                a, h = g["teams"]["away"], g["teams"]["home"]
                if a.get("score") is None or h.get("score") is None:
                    continue
                games[g["gamePk"]] = dict(pk=g["gamePk"], t=g["gameDate"], y=int(g["season"]), a=canon(a["team"]["name"]), h=canon(h["team"]["name"]),
                                          sa=a["score"], sh=h["score"], pa=pp(a)[0], ph=pp(h)[0])
    return sorted(games.values(), key=lambda g: (g["t"], g["pk"]))

def run(games, K, HA, carry, c, score_from=None):
    """Walk forward. Returns ratings, pitcher state, log loss on y >= score_from."""
    R, P, season, ll, n = {}, {}, None, 0.0, 0
    lg_sum, lg_n = 4.5 * 50, 50.0  # running league runs-per-team-game, seeded
    for g in games:
        if season is not None and g["y"] != season:
            for k in R:
                R[k] = 1500 + carry * (R[k] - 1500)
            for k in P:
                P[k] = (P[k][0] * 0.5, P[k][1] * 0.5)
        season = g["y"]
        lg = lg_sum / lg_n
        def padj(pid):
            if not pid:
                return 0.0
            s_, n_ = P.get(pid, (0.0, 0.0))
            ra = (s_ + PRIOR_STARTS * lg) / (n_ + PRIOR_STARTS)
            return c * (lg - ra)
        ra_, rh_ = R.get(g["a"], 1500.0), R.get(g["h"], 1500.0)
        diff = rh_ + HA + padj(g["ph"]) - (ra_ + padj(g["pa"]))
        ph = 1 / (1 + 10 ** (-diff / 400))
        y = 1.0 if g["sh"] > g["sa"] else 0.0
        if score_from and g["y"] >= score_from:
            ll -= y * math.log(ph) + (1 - y) * math.log(1 - ph)
            n += 1
        d = K * (1 + math.log(abs(g["sh"] - g["sa"]) + 1) * 0.5) * (y - ph)
        R[g["h"]], R[g["a"]] = rh_ + d, ra_ - d
        # pitcher state updated after the game: runs his opponent scored
        if g["ph"]:
            s_, n_ = P.get(g["ph"], (0.0, 0.0)); P[g["ph"]] = (s_ + g["sa"], n_ + 1)
        if g["pa"]:
            s_, n_ = P.get(g["pa"], (0.0, 0.0)); P[g["pa"]] = (s_ + g["sh"], n_ + 1)
        lg_sum += g["sa"] + g["sh"]; lg_n += 2
    return R, P, (lg_sum / lg_n), (ll / n if n else None), n

def consensus():
    h = subprocess.run(["curl", "-sS", "-m", "30", "-A", "Mozilla/5.0",
                        "https://www.sportsbookreview.com/betting-odds/mlb-baseball/money-line/full-game/"], capture_output=True, text=True).stdout
    d = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))
    out = []
    for t in d["props"]["pageProps"]["oddsTables"]:
        for g in t["oddsTableModel"]["gameRows"]:
            v = g["gameView"]
            rows = [(o["sportsbook"], o["currentLine"]["awayOdds"], o["currentLine"]["homeOdds"]) for o in g["oddsViews"]
                    if o and "MoneyLine" in o["viewType"] and o.get("currentLine")
                    and o["currentLine"].get("awayOdds") and o["currentLine"].get("homeOdds")]
            if len(rows) >= 4:
                out.append((v["awayTeam"]["fullName"], v["homeTeam"]["fullName"], v["startDate"], rows))
    return out

games = fetch_games()
if FETCH_FAILURES:
    print(f"FETCH_FAILURES {len(FETCH_FAILURES)}: results incomplete, refusing to rate.")
    print("CALLS_JSON []"); sys.exit(1)
per = {}
for g in games:
    per[g["y"]] = per.get(g["y"], 0) + 1
miss = sum(1 for g in games if not g["pa"] or not g["ph"]) / max(1, len(games))
print(f"mlb: {len(games)} regular-season games {FIRST}-{YEAR}, per season {per}, missing starter {miss:.1%}")
last_full = YEAR - 1
tune = [g for g in games if g["y"] < last_full]
best = min(((run(tune, K, HA, ca, c, score_from=FIRST + 1)[3], K, HA, ca, c)
            for K, HA, ca, c in product((3, 5, 8), (15, 25, 35), (0.5, 0.7, 0.9), (0, 15, 30, 45, 60))))
_, K, HA, carry, c = best
ll_c = run([g for g in games if g["y"] <= last_full], K, HA, carry, c, score_from=last_full)
ll_0 = run([g for g in games if g["y"] <= last_full], K, HA, carry, 0, score_from=last_full)
hr = sum(1 for g in games if g["y"] == last_full and g["sh"] > g["sa"]) / max(1, per.get(last_full, 1))
base = -(hr * math.log(hr) + (1 - hr) * math.log(1 - hr))
print(f"Elo K={K} HA={HA} carry={carry} pitcher c={c} Elo/run, tuned before {last_full}")
print(f"FIT mlb out-of-sample {last_full}: logloss {ll_c[3]:.4f} over {ll_c[4]} games; without pitcher term {ll_0[3]:.4f}; home-rate baseline {base:.4f}")
R, P, lg, _, _ = run(games, K, HA, carry, c)

# today's slate (ET) with probable pitchers
today_et = NOW.astimezone(ET).date()
sl = sched(today_et, today_et + dt.timedelta(days=1), "&hydrate=team")
slate = {}
for dd in (sl or {}).get("dates", []):
    for g in dd["games"]:
        t = dt.datetime.fromisoformat(g["gameDate"].replace("Z", "+00:00"))
        if g["status"]["abstractGameState"] == "Preview" and NOW < t and t.astimezone(ET).date() == today_et:
            slate[(canon(g["teams"]["away"]["team"]["name"]), canon(g["teams"]["home"]["team"]["name"]), t)] = g

W = 0.15  # MLB: the model adds little over a baseline (see FIT), so it gets a small weight
try:
    market = consensus()
except Exception as e:
    print("odds pull failed", repr(e)); market = []
calls = []
stake = lambda ev, d, f, cap: min(ev / (d - 1) * f, cap) * 100
for away, home, start, rows in market:
    t = dt.datetime.fromisoformat(start)
    m = [(k, g) for k, g in slate.items() if k[0] == canon(away) and k[1] == canon(home) and abs((k[2] - t).total_seconds()) < 900]
    if not m:
        if t > NOW and t.astimezone(ET).date() == today_et:
            print(f"{away} @ {home}  not in today's StatsAPI slate (UNRATED/unmatched)")
        continue
    (ca, ch, _), g = m[0]
    if ca not in R or ch not in R:
        print(f"{away} @ {home}  UNRATED"); continue
    pa_id, pa_n = pp(g["teams"]["away"]); ph_id, ph_n = pp(g["teams"]["home"])
    pending = not pa_id or not ph_id
    def padj(pid):
        if not pid: return 0.0
        s_, n_ = P.get(pid, (0.0, 0.0)); return c * (lg - (s_ + PRIOR_STARTS * lg) / (n_ + PRIOR_STARTS))
    pm_h = 1 / (1 + 10 ** (-((R[ch] + HA + padj(ph_id)) - (R[ca] + padj(pa_id))) / 400))
    mk_h = 1 - st.mean(imp(x) / (imp(x) + imp(y)) for _, x, y in rows)
    p_h = (1 - W) * mk_h + W * pm_h
    gap = abs(pm_h - mk_h)
    ets = t.astimezone(ET)
    print(f"{away} @ {home}  {ets:%a %d %b %H:%M} ET gamePk {g['gamePk']}  home: model {pm_h:.3f} market {mk_h:.3f} blend {p_h:.3f} gap {gap:.3f} books={len(rows)}")
    print(f"   SP {pa_n or 'TBD'} (adj {padj(pa_id):+.0f}) vs {ph_n or 'TBD'} (adj {padj(ph_id):+.0f})")
    for side, team, pb, pmod, i in (("away", away, 1 - p_h, 1 - pm_h, 1), ("home", home, p_h, pm_h, 2)):
        b = max(rows, key=lambda r: dec(r[i])); d = dec(b[i])
        ev_b = pb * (d - 1) - (1 - pb); ev_m = pmod * (d - 1) - (1 - pmod)
        tier = "STRONG" if ev_b >= .02 else ("MODEL PICK" if ev_m >= .03 and ev_b >= 0 else "")
        why = ""
        if tier and not (BAND[0] <= b[i] <= BAND[1]): tier, why = "", "outside price band"
        if tier and gap > DISAGREE_CAP: tier, why = "", "model/market gap too big"
        if tier and pending: tier, why = "", "probable pitcher not listed"
        if tier and len(rows) < 6: tier, why = "", "fewer than 6 books"
        stk = stake(ev_b, d, .25, .02) if tier == "STRONG" else (stake(ev_m, d, .125, .01) if tier else 0)
        print(f"   {team[:22]:22} blend {pb:.3f} model {pmod:.3f} best {b[0]} {b[i]:+d} EV blend {ev_b*100:+.1f}% model {ev_m*100:+.1f}%"
              + (f"  <-- {tier} stake {stk:.2f}%" if tier else (f"  [no call: {why}]" if why else "")))
        if tier:
            calls.append(dict(sport="mlb", tier=tier, event_id=f"mlb:{g['gamePk']}", date_et=f"{ets:%Y-%m-%d}", start_et=f"{ets:%a %d %b %H:%M} ET",
                              game=f"{away}@{home}", team=team, side=side, book=b[0], price=b[i], model=round(pmod, 3),
                              market=round((1 - mk_h) if side == "away" else mk_h, 3), ev_blend=round(ev_b, 4), ev_model=round(ev_m, 4),
                              stake_pct=round(stk, 2), start=start, books=len(rows),
                              starters={"away": pa_n, "home": ph_n},
                              conditional="bet only after both starting pitchers are confirmed; void if either does not start"))
print("\nCALLS_JSON", json.dumps(calls))
