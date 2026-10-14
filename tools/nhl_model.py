"""NHL Elo model vs market.

1. Pull 2024-25 onward results from the public NHL API.
2. Grid-search Elo hyperparameters on past games (walk-forward log loss).
3. Rate every team, predict upcoming games, compare to the devigged
   multi-book consensus from SBR, and blend (market prior, model tilt).

Usage: python3 -I tools/nhl_model.py [YYYY-MM-DD]        model run (default: today UTC)
       python3 -I tools/nhl_model.py --finals YYYY-MM-DD  finals on that date, for grading

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

def stake(ev, p, d, frac, cap):
    k = ev / (d - 1)
    return min(k * frac, cap) * 100

try:
    slate = consensus()
except Exception as e:
    print("odds pull failed", repr(e)); slate = []
calls = []
for away, home, start, rows in slate:
    a, h = NAMES.get(away), NAMES.get(home)
    if a not in R or h not in R:
        print(f"{away} @ {home}  UNRATED (add mapping)"); continue
    pm_h = 1 / (1 + 10 ** (-(R[h] + HA - R[a]) / 400))
    mk_h = 1 - st.mean(imp(x) / (imp(x) + imp(y)) for _, x, y in rows)
    p_h = (1 - W) * mk_h + W * pm_h
    print(f"{a} @ {h}  {start[11:16]}Z  home: model {pm_h:.3f}  market {mk_h:.3f}  blend {p_h:.3f}  books={len(rows)}")
    for side, team, pb, pmod, i in (("away", a, 1 - p_h, 1 - pm_h, 1), ("home", h, p_h, pm_h, 2)):
        b = max(rows, key=lambda r: dec(r[i]))
        d = dec(b[i])
        ev_b = pb * (d - 1) - (1 - pb)
        ev_m = pmod * (d - 1) - (1 - pmod)
        tier = "STRONG" if ev_b >= .02 else ("MODEL PICK" if ev_m >= .03 else "")
        if tier == "STRONG":
            stk = stake(ev_b, pb, d, .25, .02)
        elif tier:
            stk = stake(ev_m, pmod, d, .125, .01)
        else:
            stk = 0
        print(f"   {team:3} blend {pb:.3f} model {pmod:.3f}  best {b[0]} {b[i]:+d}  EV blend {ev_b*100:+.1f}% model {ev_m*100:+.1f}%"
              + (f"  <-- {tier} stake {stk:.2f}%" if tier else ""))
        if tier:
            calls.append(dict(tier=tier, game=f"{a}@{h}", team=team, side=side, book=b[0], price=b[i],
                              model=round(pmod, 3), market=round(1 - mk_h if side == "away" else mk_h, 3),
                              ev_blend=round(ev_b, 4), ev_model=round(ev_m, 4), stake_pct=round(stk, 2), start=start))
print("\nCALLS_JSON", json.dumps(calls))
