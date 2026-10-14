"""NHL Elo model vs market.

1. Pull 2024-25 onward results from the public NHL API.
2. Grid-search Elo hyperparameters on past games (walk-forward log loss).
3. Rate every team, predict upcoming games, compare to the devigged
   multi-book consensus from SBR, and blend (market prior, model tilt).

Usage: python3 -I tools/nhl_model.py [YYYY-MM-DD]        model run (default: today UTC)
       python3 -I tools/nhl_model.py --finals YYYY-MM-DD  finals on that date, for grading

Goalie workaround: starters and Confirmed/Likely status come from DailyFaceoff.
  Confirmed or Likely -> call is allowed but names the goalie and is void if he does not start.
  No starter listed   -> no call (PENDING).
Also: model/market gap above 8 pts -> no call (usually news the model cannot see),
      price band -300..+300, only games starting within 36 hours.

Tiers (stake is % of bankroll):
  STRONG       blended EV >= 2%    quarter Kelly, cap 2%
  MODEL PICK   model-only EV >= 3% eighth Kelly, cap 1%
  NO CALL      neither
"""
import json, math, re, subprocess, sys, statistics as st, datetime as dt
from itertools import product

FINALS = len(sys.argv) > 2 and sys.argv[1] == "--finals"
_arg = sys.argv[2] if FINALS else (sys.argv[1] if len(sys.argv) > 1 else None)
TODAY = dt.date.fromisoformat(_arg) if _arg else dt.datetime.now(dt.timezone.utc).date()
START = dt.date(2024, 10, 4)
imp = lambda o: -o / (-o + 100) if o < 0 else 100 / (o + 100)
dec = lambda o: 1 + 100 / -o if o < 0 else 1 + o / 100

def get(url):
    r = subprocess.run(["curl", "-sS", "-m", "30", url], capture_output=True, text=True)
    return json.loads(r.stdout)

NAMES = {}  # nickname -> abbrev

def fetch():
    games, upcoming, d = {}, [], START
    while d <= TODAY + dt.timedelta(days=1):
        wk = get(f"https://api-web.nhle.com/v1/schedule/{d}")
        for day in wk["gameWeek"]:
            for g in day["games"]:
                for side in ("awayTeam", "homeTeam"):
                    NAMES[g[side]["commonName"]["default"]] = g[side]["abbrev"]
                if g["gameType"] not in (2, 3):
                    continue
                if g["gameState"] in ("OFF", "FINAL") and "score" in g["awayTeam"]:
                    games[g["id"]] = (g["startTimeUTC"], g["awayTeam"]["abbrev"], g["homeTeam"]["abbrev"],
                                      g["awayTeam"]["score"], g["homeTeam"]["score"], g["season"])
                elif g["gameState"] in ("FUT", "PRE"):
                    upcoming.append((g["startTimeUTC"], g["awayTeam"]["abbrev"], g["homeTeam"]["abbrev"]))
        d += dt.timedelta(days=7)
    return sorted(games.values()), sorted(set(upcoming))

def run_elo(games, K, HA, carry, upto=None):
    """Walk forward. Return ratings, log-loss, n, and per-game probs."""
    R, ll, n, season = {}, 0.0, 0, None
    for t, a, h, sa, sh, s in games:
        if season is not None and s != season:
            for k in R:
                R[k] = 1500 + carry * (R[k] - 1500)
        season = s
        ra, rh = R.get(a, 1500.0), R.get(h, 1500.0)
        ph = 1 / (1 + 10 ** (-(rh + HA - ra) / 400))
        y = 1.0 if sh > sa else 0.0
        if n >= 200:  # burn-in
            ll -= y * math.log(ph) + (1 - y) * math.log(1 - ph)
        n += 1
        mult = math.log(abs(sh - sa) + 1) + 1  # goal-diff scaling
        d = K * mult * (y - ph)
        R[h], R[a] = rh + d, ra - d
    return R, ll / max(n - 200, 1), n

def consensus():
    h = subprocess.run(["curl", "-sS", "-m", "30", "-A", "Mozilla/5.0",
                        "https://www.sportsbookreview.com/betting-odds/nhl-hockey/"],
                       capture_output=True, text=True).stdout
    d = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))
    out = []
    for t in d["props"]["pageProps"]["oddsTables"]:
        for g in t["oddsTableModel"]["gameRows"]:
            v = g["gameView"]
            rows = [(o["sportsbook"], o["currentLine"]["awayOdds"], o["currentLine"]["homeOdds"]) for o in g["oddsViews"]
                    if o and "MoneyLine" in o["viewType"] and o.get("currentLine")
                    and o["currentLine"].get("awayOdds") and o["currentLine"].get("homeOdds")]
            if len(rows) >= 4:
                out.append((v["awayTeam"]["nickname"], v["homeTeam"]["nickname"], v["startDate"], rows))
    return out

if FINALS:
    wk = get(f"https://api-web.nhle.com/v1/schedule/{TODAY}")
    for day in wk["gameWeek"]:
        if day["date"] != str(TODAY):
            continue
        for g in day["games"]:
            if g["gameState"] in ("OFF", "FINAL") and "score" in g["awayTeam"]:
                print(f"{TODAY} {g['awayTeam']['abbrev']} {g['awayTeam']['score']} @ {g['homeTeam']['abbrev']} {g['homeTeam']['score']}")
    sys.exit()

games, upcoming = fetch()
print(f"{len(games)} finished games, {len(upcoming)} upcoming, through {TODAY}")
home_rate = sum(1 for g in games if g[4] > g[3]) / len(games)
base = -(home_rate * math.log(home_rate) + (1 - home_rate) * math.log(1 - home_rate))
best = min(((run_elo(games, K, HA, c)[1], K, HA, c) for K, HA, c in product((2, 4, 6, 9), (20, 35, 50), (0.5, 0.7, 0.9))))
ll, K, HA, carry = best
print(f"Elo K={K} HA={HA} carry={carry}  walk-forward logloss {ll:.4f}  vs home-rate baseline {base:.4f}  vs coin 0.6931")
R, _, _ = run_elo(games, K, HA, carry)
# if a new season has started, regress first-game ratings is already handled in walk-forward

W = 0.30  # weight on model in the blend; raise only after the ledger earns it
print(f"\nBlend weight on model: {W} (market prior {1-W})\n")

def goalies():
    """team nickname -> (goalie name, status or None) from DailyFaceoff."""
    out = {}
    try:
        h = subprocess.run(["curl", "-sSL", "-m", "30", "-A", "Mozilla/5.0", "https://www.dailyfaceoff.com/starting-goalies"],
                           capture_output=True, text=True).stdout
        d = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))
        for g in d["props"]["pageProps"]["data"]:
            for side in ("home", "away"):
                out[(g[side + "TeamName"].split()[-1], g["date"])] = (g[side + "GoalieName"], g[side + "NewsStrengthName"])
    except Exception as e:
        print("goalie pull failed", repr(e))
    return out

def goalie_adj(abbrev, name):
    """Elo adjustment for today's goalie vs the team's usual mix, from last season's save %.

    Save % is shrunk toward .905 with 40 games of prior. 0.010 of save % is
    treated as about 35 Elo (assumption, not fitted). Unmatched name -> 0.
    """
    y = NOW.year if NOW.month >= 8 else NOW.year - 1
    d = get(f"https://api-web.nhle.com/v1/club-stats/{abbrev}/{y-1}{y}/2")
    gs = [(f"{g['firstName']['default']} {g['lastName']['default']}", g["gamesPlayed"], g["savePercentage"])
          for g in (d or {}).get("goalies", []) if g.get("savePercentage")]
    shrunk = lambda sv, gp: (sv * gp + 0.905 * 40) / (gp + 40)
    tot = sum(gp for _, gp, _ in gs)
    if not tot or not name:
        return 0.0, "no data"
    team = shrunk(sum(sv * gp for _, gp, sv in gs) / tot, tot)
    m = [x for x in gs if x[0] == name]
    if not m:
        return 0.0, "goalie unrated"
    _, gp, sv = m[0]
    return 3500 * (shrunk(sv, gp) - team), f"{shrunk(sv, gp):.3f} vs team {team:.3f}"

def stake(ev, p, d, frac, cap):
    k = ev / (d - 1)
    return min(k * frac, cap) * 100

try:
    slate = consensus()
except Exception as e:
    print("odds pull failed", repr(e)); slate = []
calls = []
G = goalies()
NOW = dt.datetime.now(dt.timezone.utc)
for away, home, start, rows in slate:
    if not (NOW < dt.datetime.fromisoformat(start) < NOW + dt.timedelta(hours=36)):
        continue
    a, h = NAMES.get(away), NAMES.get(home)
    if a not in R or h not in R:
        print(f"{away} @ {home}  UNRATED (add mapping)"); continue
    mk_h = 1 - st.mean(imp(x) / (imp(x) + imp(y)) for _, x, y in rows)
    gk = {}
    for nick, ab in ((away, a), (home, h)):
        gk[ab] = G.get((nick, start[:10])) or G.get((nick, (dt.datetime.fromisoformat(start) - dt.timedelta(hours=5)).strftime("%Y-%m-%d"))) or (None, None)
    gnote = "goalies " + ", ".join(f"{ab} {n} ({s_ or 'unlisted'})" for ab, (n, s_) in gk.items())
    pending = any(n is None or s_ is None for n, s_ in gk.values())
    adjs = {ab: goalie_adj(ab, n) for ab, (n, _) in gk.items()}
    pm_h = 1 / (1 + 10 ** (-((R[h] + adjs[h][0]) + HA - (R[a] + adjs[a][0])) / 400))
    gnote += " | goalie adj Elo " + ", ".join(f"{ab} {x[0]:+.0f} ({x[1]})" for ab, x in adjs.items())
    p_h = (1 - W) * mk_h + W * pm_h
    gap = abs(pm_h - mk_h)
    print(f"{a} @ {h}  {start[11:16]}Z  home: model {pm_h:.3f}  market {mk_h:.3f}  blend {p_h:.3f}  books={len(rows)}  gap {gap:.3f}\n   {gnote}")
    for side, team, pb, pmod, i in (("away", a, 1 - p_h, 1 - pm_h, 1), ("home", h, p_h, pm_h, 2)):
        b = max(rows, key=lambda r: dec(r[i]))
        d = dec(b[i])
        ev_b = pb * (d - 1) - (1 - pb)
        ev_m = pmod * (d - 1) - (1 - pmod)
        tier = "STRONG" if ev_b >= .02 else ("MODEL PICK" if ev_m >= .03 else "")
        why = ""
        if tier and not (-300 <= b[i] <= 300): tier, why = "", "outside price band"
        if tier and gap > 0.08: tier, why = "", "model/market gap too big (likely lineup news)"
        if tier and pending: tier, why = "", "goalie not listed"
        if tier == "STRONG":
            stk = stake(ev_b, pb, d, .25, .02)
        elif tier:
            stk = stake(ev_m, pmod, d, .125, .01)
        else:
            stk = 0
        print(f"   {team:3} blend {pb:.3f} model {pmod:.3f}  best {b[0]} {b[i]:+d}  EV blend {ev_b*100:+.1f}% model {ev_m*100:+.1f}%"
              + (f"  <-- {tier} stake {stk:.2f}%" if tier else (f"  [no call: {why}]" if why else "")))
        if tier:
            calls.append(dict(sport="nhl", event_id=f"nhl:{start[:10]}:{a}@{h}", starters={ab: f"{n} ({s_})" for ab, (n, s_) in gk.items()},
                              conditional="bet only after goalie confirmed; void if the goalie does not start", books=len(rows), tier=tier, game=f"{a}@{h}", team=team, side=side, book=b[0], price=b[i],
                              model=round(pmod, 3), market=round(1 - mk_h if side == "away" else mk_h, 3),
                              ev_blend=round(ev_b, 4), ev_model=round(ev_m, 4), stake_pct=round(stk, 2), start=start))
print("\nCALLS_JSON", json.dumps(calls))
