"""NFL / college football Elo model vs market.

Usage: python3 -I tools/football_model.py nfl|cfb
       python3 -I tools/football_model.py nfl|cfb --finals YYYY-MM-DD

Data: ESPN public scoreboards (results) + SBR money-line page (prices).
Model: Elo with the standard football margin multiplier, home field, neutral
sites, ties as 0.5, and a pull back toward average each new season.
Hyperparameters are tuned on seasons BEFORE the last full season; log loss is
reported on that last full season, so it is out of sample.

Lineup workaround (no live QB feed is reliable):
  * NFL: QB1 from the ESPN depth chart, status from the ESPN injury feed.
    Out/Doubtful -> rate that team with a backup penalty. Questionable -> no call.
  * Disagreement cap: model vs market gap above 12 pts -> no call, because a gap that
    large is usually lineup news the model cannot see.
  * Price band: only moneylines between -300 and +300.
  * Conditional: every call names the QB it assumes and is void if he does not start.
"""
import json, math, re, subprocess, sys, statistics as st, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from itertools import product

LEAGUE = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("nfl", "cfb") else "nfl"
CFG = {
    "nfl": dict(espn="nfl", slug="nfl-football", weeks=range(1, 19), first=2019, extra="", min_games=0),
    "cfb": dict(espn="college-football", slug="college-football", weeks=range(1, 16), first=2023, extra="&groups=80&limit=400", min_games=6),
}[LEAGUE]
NOW = dt.datetime.now(dt.timezone.utc)
YEAR = NOW.year if NOW.month >= 8 else NOW.year - 1
QB_PENALTY = 125  # Elo, about 5 points; a fixed assumption, not a fitted value
DISAGREE_CAP = 0.12
BAND = (-300, 300)
imp = lambda o: -o / (-o + 100) if o < 0 else 100 / (o + 100)
dec = lambda o: 1 + 100 / -o if o < 0 else 1 + o / 100
norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())

def get(url):
    r = subprocess.run(["curl", "-sS", "-m", "40", "-A", "Mozilla/5.0", url], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return None

def sb(q):
    return get(f"https://site.api.espn.com/apis/site/v2/sports/football/{CFG['espn']}/scoreboard?{q}")

def parse_event(e):
    c = e["competitions"][0]
    h = next(x for x in c["competitors"] if x["homeAway"] == "home")
    a = next(x for x in c["competitors"] if x["homeAway"] == "away")
    return e, c, h, a

if "--finals" in sys.argv:
    day = sys.argv[sys.argv.index("--finals") + 1]
    d = sb(f"dates={day.replace('-', '')}{CFG['extra']}")
    for e in (d or {}).get("events", []):
        e, c, h, a = parse_event(e)
        if e["status"]["type"]["name"] == "STATUS_FINAL":
            print(f"{day} {a['team']['displayName']} {a['score']} @ {h['team']['displayName']} {h['score']}")
    sys.exit()

def fetch_games():
    jobs = [(y, w) for y in range(CFG["first"], YEAR + 1) for w in CFG["weeks"]]
    def one(j):
        y, w = j
        return j, sb(f"dates={y}&seasontype=2&week={w}{CFG['extra']}")
    games = []
    with ThreadPoolExecutor(8) as ex:
        for (y, w), d in ex.map(one, jobs):
            for e in (d or {}).get("events", []):
                e, c, h, a = parse_event(e)
                if e["status"]["type"]["name"] != "STATUS_FINAL":
                    continue
                try:
                    sh, sa = float(h["score"]), float(a["score"])
                except Exception:
                    continue
                games.append(dict(t=e["date"], y=y, a=a["team"]["displayName"], h=h["team"]["displayName"],
                                  sa=sa, sh=sh, neutral=bool(c.get("neutralSite"))))
    games.sort(key=lambda g: g["t"])
    if CFG["min_games"]:  # drop non-FBS opponents
        cnt = {}
        for g in games:
            for k in ((g["y"], g["a"]), (g["y"], g["h"])):
                cnt[k] = cnt.get(k, 0) + 1
        games = [g for g in games if cnt[(g["y"], g["a"])] >= CFG["min_games"] and cnt[(g["y"], g["h"])] >= CFG["min_games"]]
    return games

def run_elo(games, K, HA, carry, qb=None, score_from=None):
    """Walk forward. Returns ratings and log loss over games with y >= score_from."""
    R, season, ll, n = {}, None, 0.0, 0
    for g in games:
        if season is not None and g["y"] != season:
            for k in R:
                R[k] = 1500 + carry * (R[k] - 1500)
        season = g["y"]
        ra, rh = R.get(g["a"], 1500.0), R.get(g["h"], 1500.0)
        ha = 0 if g["neutral"] else HA
        diff = rh + ha - ra
        ph = 1 / (1 + 10 ** (-diff / 400))
        y = 1.0 if g["sh"] > g["sa"] else (0.5 if g["sh"] == g["sa"] else 0.0)
        if score_from and g["y"] >= score_from:
            ll -= y * math.log(ph) + (1 - y) * math.log(1 - ph)
            n += 1
        mov = abs(g["sh"] - g["sa"])
        wdiff = diff if y == 1 else -diff
        mult = math.log(mov + 1) * 2.2 / (0.001 * max(wdiff, 0) + 2.2) if mov else 1.0
        d = K * mult * (y - ph)
        R[g["h"]], R[g["a"]] = rh + d, ra - d
    return R, (ll / n if n else None), n

def consensus():
    h = subprocess.run(["curl", "-sS", "-m", "30", "-A", "Mozilla/5.0",
                        f"https://www.sportsbookreview.com/betting-odds/{CFG['slug']}/money-line/full-game/"],
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
                out.append((v["awayTeam"]["fullName"], v["homeTeam"]["fullName"], v["startDate"], rows))
    return out

def qb_status():
    """NFL only. team displayName -> (qb1 name, status or 'Healthy')."""
    out = {}
    inj = get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries")
    bad = {}
    for t in (inj or {}).get("injuries", []):
        for i in t.get("injuries", []):
            a = i.get("athlete", {})
            if a.get("position", {}).get("abbreviation") == "QB" or i.get("position") == "QB":
                bad[(t["displayName"], a.get("displayName"))] = i.get("status", "")
    teams = get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams?limit=40")
    tl = [x["team"] for x in teams["sports"][0]["leagues"][0]["teams"]]
    def one(t):
        d = get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{t['id']}/depthcharts")
        name = None
        for ch in (d or {}).get("depthchart", []):
            q = ch.get("positions", {}).get("qb")
            if q and q.get("athletes"):
                a = q["athletes"][0]
                name = (a.get("athlete") or a).get("displayName") or a.get("displayName")
                break
        return t["displayName"], name
    with ThreadPoolExecutor(8) as ex:
        for tn, name in ex.map(one, tl):
            out[tn] = (name, bad.get((tn, name), "Healthy"))
    return out

def neutral_map():
    m = {}
    for dd in {(NOW + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(0, 3)}:
        d = sb(f"dates={dd}{CFG['extra']}")
        for e in (d or {}).get("events", []):
            e, c, h, a = parse_event(e)
            m[(norm(a["team"]["displayName"]), norm(h["team"]["displayName"]))] = bool(c.get("neutralSite"))
    return m

games = fetch_games()
last_full = YEAR - 1
tune = [g for g in games if g["y"] < last_full]
grid = product((10, 15, 20, 28), (30, 48, 65), (0.55, 0.7, 0.85)) if LEAGUE == "nfl" else product((12, 20, 30, 40), (45, 65, 85), (0.5, 0.65, 0.8))
tuned = min(((run_elo(tune, K, HA, c, score_from=min(g["y"] for g in tune) + 1)[1], K, HA, c) for K, HA, c in grid))
_, K, HA, carry = tuned
_, ll_oos, n_oos = run_elo([g for g in games if g["y"] <= last_full], K, HA, carry, score_from=last_full)
hr = sum(1 for g in games if g["y"] == last_full and g["sh"] > g["sa"]) / max(1, sum(1 for g in games if g["y"] == last_full))
base = -(hr * math.log(hr) + (1 - hr) * math.log(1 - hr))
print(f"{LEAGUE}: {len(games)} games {CFG['first']}-{YEAR}. Elo K={K} HA={HA} carry={carry} tuned before {last_full}")
print(f"FIT {LEAGUE} out-of-sample {last_full}: logloss {ll_oos:.4f} over {n_oos} games, home-rate baseline {base:.4f}")
R, _, _ = run_elo(games, K, HA, carry)
by_norm = {norm(k): k for k in R}

W = 0.30
slate = []
try:
    slate = consensus()
except Exception as e:
    print("odds pull failed", repr(e))
qbs = qb_status() if LEAGUE == "nfl" else {}
nm = neutral_map()
calls = []

def stake(ev, d, frac, cap):
    return min(ev / (d - 1) * frac, cap) * 100

for away, home, start, rows in slate:
    st_dt = dt.datetime.fromisoformat(start)
    if not (NOW < st_dt < NOW + dt.timedelta(hours=36)):
        continue
    a, h = by_norm.get(norm(away)), by_norm.get(norm(home))
    if not a or not h:
        print(f"{away} @ {home}  UNRATED"); continue
    neutral = nm.get((norm(away), norm(home)), False)
    ha = 0 if neutral else HA
    adj = {a: 0, h: 0}
    notes = []
    if LEAGUE == "nfl":
        for tm in (a, h):
            nme, status = qbs.get(tm, (None, "Unknown"))
            if status in ("Out", "Doubtful", "Injured Reserve"):
                adj[tm] = -QB_PENALTY; notes.append(f"{tm} QB1 {nme} {status}: backup penalty")
            elif status in ("Questionable", "Day-To-Day", "Unknown"):
                notes.append(f"{tm} QB1 {nme} {status}: PENDING")
    pending = any("PENDING" in n for n in notes)
    pm_h = 1 / (1 + 10 ** (-((R[h] + adj[h]) + ha - (R[a] + adj[a])) / 400))
    mk_h = 1 - st.mean(imp(x) / (imp(x) + imp(y)) for _, x, y in rows)
    p_h = (1 - W) * mk_h + W * pm_h
    gap = abs(pm_h - mk_h)
    starters = {tm: qbs.get(tm, (None, ""))[0] for tm in (a, h)} if LEAGUE == "nfl" else {}
    print(f"{a} @ {h}  {start[:16]}Z{' neutral' if neutral else ''}  home: model {pm_h:.3f} market {mk_h:.3f} blend {p_h:.3f} gap {gap:.3f} books={len(rows)}"
          + ("  " + "; ".join(notes) if notes else ""))
    for side, team, pb, pmod, i in (("away", a, 1 - p_h, 1 - pm_h, 1), ("home", h, p_h, pm_h, 2)):
        b = max(rows, key=lambda r: dec(r[i]))
        d = dec(b[i])
        ev_b = pb * (d - 1) - (1 - pb)
        ev_m = pmod * (d - 1) - (1 - pmod)
        tier = "STRONG" if ev_b >= .02 else ("MODEL PICK" if ev_m >= .03 else "")
        why = ""
        if tier and not (BAND[0] <= b[i] <= BAND[1]): tier, why = "", "outside price band"
        if tier and gap > DISAGREE_CAP: tier, why = "", "model/market gap too big (likely lineup news)"
        if tier and pending: tier, why = "", "QB1 status pending"
        stk = stake(ev_b, d, .25, .02) if tier == "STRONG" else (stake(ev_m, d, .125, .01) if tier else 0)
        print(f"   {team[:22]:22} blend {pb:.3f} model {pmod:.3f} best {b[0]} {b[i]:+d} EV blend {ev_b*100:+.1f}% model {ev_m*100:+.1f}%"
              + (f"  <-- {tier} stake {stk:.2f}%" if tier else (f"  [no call: {why}]" if why else "")))
        if tier:
            calls.append(dict(sport=LEAGUE, tier=tier, event_id=f"{LEAGUE}:{start[:10]}:{a}@{h}", game=f"{a}@{h}", team=team,
                              side=side, book=b[0], price=b[i], model=round(pmod, 3),
                              market=round((1 - mk_h) if side == "away" else mk_h, 3), ev_blend=round(ev_b, 4),
                              ev_model=round(ev_m, 4), stake_pct=round(stk, 2), start=start, books=len(rows),
                              starters=starters, conditional="bet only after starter confirmed; void if QB1 does not start" if LEAGUE == "nfl" else "no lineup data; bet only after checking QB news"))
print("\nCALLS_JSON", json.dumps(calls))
