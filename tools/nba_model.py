"""NBA Elo model vs market.

Usage: python3 -I tools/nba_model.py
       python3 -I tools/nba_model.py --finals YYYY-MM-DD     (ET date)

Data: ESPN public scoreboards, one request per day (a date range is rejected).
Model: Elo with the NBA margin-of-victory multiplier, home court, neutral sites,
a back-to-back penalty, and a pull toward average each new SEASON (labelled by
ESPN's season year, not the calendar year). Only regular-season games (ESPN
season type 2) train the model or qualify for calls; preseason is ignored.
Hyperparameters are tuned on seasons before the last full one and scored on it.

Lineup workaround:
  * "Stars" = the two players who most often led their team in points over its last
    20 games (from the scoreboard leaders data).
  * If either star of either team is Out, Doubtful, Questionable or Day-To-Day on
    the ESPN injury feed, no call: the price knows, the model does not.
  * Gap above 12 pts between model and market -> no call. Price band -300..+300.
  * Only games starting later today by the America/New_York calendar.
"""
import json, math, re, subprocess, sys, statistics as st, datetime as dt
from concurrent.futures import ThreadPoolExecutor
from itertools import product
from collections import Counter, deque
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
NOW = dt.datetime.now(dt.timezone.utc)
TODAY_ET = NOW.astimezone(ET).date()
SEASON = TODAY_ET.year + (1 if TODAY_ET.month >= 9 else 0)  # ESPN season year = year the season ends
FIRST = SEASON - 3
W = 0.20
DISAGREE_CAP = 0.12
BAND = (-300, 300)
imp = lambda o: -o / (-o + 100) if o < 0 else 100 / (o + 100)
dec = lambda o: 1 + 100 / -o if o < 0 else 1 + o / 100
ALIAS = {"losangelesclippers": "laclippers"}
def canon(s):
    n = re.sub(r"[^a-z0-9]", "", s.lower())
    return ALIAS.get(n, n)

FETCH_FAILURES = []
def get(url, need=None):
    for _ in range(4):
        r = subprocess.run(["curl", "-sS", "--compressed", "-m", "40", "-A", "Mozilla/5.0", url], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            if need is None or need in d:
                return d
        except Exception:
            pass
    FETCH_FAILURES.append(url)
    return None

def day(d):
    return get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d:%Y%m%d}", need="events")

def parse(e):
    c = e["competitions"][0]
    h = next(x for x in c["competitors"] if x["homeAway"] == "home")
    a = next(x for x in c["competitors"] if x["homeAway"] == "away")
    def lead(x):
        for l in x.get("leaders", []):
            if l["name"] == "points" and l.get("leaders"):
                p = l["leaders"][0]["athlete"]
                return p["id"], p["displayName"]
        return None, None
    return c, h, a, lead(h), lead(a)

if "--finals" in sys.argv:
    d0 = dt.date.fromisoformat(sys.argv[sys.argv.index("--finals") + 1])
    for dd in (d0, d0 + dt.timedelta(days=1)):
        for e in (day(dd) or {}).get("events", []):
            c, h, a, _, _ = parse(e)
            t = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(ET).date()
            if t == d0 and e["status"]["type"]["name"] == "STATUS_FINAL":
                print(f"{d0} {a['team']['displayName']} {a['score']} @ {h['team']['displayName']} {h['score']}")
    sys.exit()

def fetch_games():
    days = []
    for y in range(FIRST, SEASON + 1):
        d, end = dt.date(y - 1, 10, 1), min(dt.date(y, 6, 30), TODAY_ET)
        while d <= end:
            days.append(d); d += dt.timedelta(days=1)
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(day, days))
    games = {}
    for d in res:
        for e in (d or {}).get("events", []):
            if e["season"]["type"] != 2 or e["status"]["type"]["name"] != "STATUS_FINAL":
                continue
            c, h, a, lh, la = parse(e)
            try:
                sh, sa = float(h["score"]), float(a["score"])
            except Exception:
                continue
            games[e["id"]] = dict(id=e["id"], t=e["date"], y=e["season"]["year"], a=canon(a["team"]["displayName"]), h=canon(h["team"]["displayName"]),
                                  sa=sa, sh=sh, neutral=bool(c.get("neutralSite")), la=la, lh=lh)
    return sorted(games.values(), key=lambda g: (g["t"], g["id"]))

def run(games, K, HA, carry, B2B, score_from=None):
    R, last, season, ll, n = {}, {}, None, 0.0, 0
    lead = {}  # team -> deque of recent scoring-leader (id, name)
    for g in games:
        if season is not None and g["y"] != season:
            for k in R:
                R[k] = 1500 + carry * (R[k] - 1500)
        season = g["y"]
        gd = dt.datetime.fromisoformat(g["t"].replace("Z", "+00:00")).astimezone(ET).date()
        def tired(tm):
            return last.get(tm) is not None and (gd - last[tm]).days == 1
        ra, rh = R.get(g["a"], 1500.0), R.get(g["h"], 1500.0)
        ha = 0 if g["neutral"] else HA
        diff = rh + ha - B2B * tired(g["h"]) + B2B * tired(g["a"]) - ra
        ph = 1 / (1 + 10 ** (-diff / 400))
        y = 1.0 if g["sh"] > g["sa"] else 0.0
        if score_from and g["y"] >= score_from:
            ll -= y * math.log(ph) + (1 - y) * math.log(1 - ph); n += 1
        mov = abs(g["sh"] - g["sa"]); wd = diff if y == 1 else -diff
        mult = ((mov + 3) ** 0.8) / (7.5 + 0.006 * max(wd, 0))
        d = K * mult * (y - ph)
        R[g["h"]], R[g["a"]] = rh + d, ra - d
        last[g["h"]] = last[g["a"]] = gd
        for tm, l in ((g["h"], g["lh"]), (g["a"], g["la"])):
            if l[0]:
                lead.setdefault(tm, deque(maxlen=20)).append(l)
    return R, last, lead, (ll / n if n else None), n

def stars(lead, tm):
    cnt = Counter(lead.get(tm, []))
    return [(i, nme) for (i, nme), _ in cnt.most_common(2)]

def consensus():
    h = subprocess.run(["curl", "-sS", "-m", "30", "-A", "Mozilla/5.0",
                        "https://www.sportsbookreview.com/betting-odds/nba-basketball/money-line/full-game/"], capture_output=True, text=True).stdout
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
per = Counter(g["y"] for g in games)
print(f"nba: {len(games)} regular-season games, per season {dict(per)}")
last_full = SEASON - 1 if per.get(SEASON, 0) < 1000 else SEASON
tune = [g for g in games if g["y"] < last_full]
best = min(((run(tune, K, HA, ca, b, score_from=min(g["y"] for g in tune) + 1)[3], K, HA, ca, b)
            for K, HA, ca, b in product((12, 18, 24), (60, 90, 120), (0.6, 0.75, 0.9), (0, 25, 50))))
_, K, HA, carry, B2B = best
oos = run([g for g in games if g["y"] <= last_full], K, HA, carry, B2B, score_from=last_full)
hr = sum(1 for g in games if g["y"] == last_full and g["sh"] > g["sa"]) / max(1, per[last_full])
base = -(hr * math.log(hr) + (1 - hr) * math.log(1 - hr))
print(f"Elo K={K} HA={HA} carry={carry} back-to-back={B2B} Elo, tuned before season {last_full}")
print(f"FIT nba out-of-sample season {last_full}: logloss {oos[3]:.4f} over {oos[4]} games, home-rate baseline {base:.4f}")
R, last, lead, _, _ = run(games, K, HA, carry, B2B)

# today's regular-season games and injuries
info = {}
for dd in (TODAY_ET, TODAY_ET + dt.timedelta(days=1)):
    for e in (day(dd) or {}).get("events", []):
        c, h, a, _, _ = parse(e)
        t = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
        info[(canon(a["team"]["displayName"]), canon(h["team"]["displayName"]), t)] = (e["season"]["type"], bool(c.get("neutralSite")), a["team"]["displayName"], h["team"]["displayName"])
inj = {}
for t in (get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries", need="injuries") or {}).get("injuries", []):
    inj[canon(t["displayName"])] = {str(i["athlete"].get("id")): i.get("status", "") for i in t.get("injuries", []) if i.get("athlete") and i["athlete"].get("id")}
BAD = {"Out", "Doubtful", "Questionable", "Day-To-Day"}

try:
    market = consensus()
except Exception as e:
    print("odds pull failed", repr(e)); market = []
calls = []
stake = lambda ev, d, f, cap: min(ev / (d - 1) * f, cap) * 100
for away, home, start, rows in market:
    t = dt.datetime.fromisoformat(start); ets = t.astimezone(ET)
    if not (NOW < t and ets.date() == TODAY_ET):
        continue
    ca, ch = canon(away), canon(home)
    m = [(k, v) for k, v in info.items() if k[0] == ca and k[1] == ch and abs((k[2] - t).total_seconds()) < 900]
    if not m:
        print(f"{away} @ {home}  not matched in ESPN slate (UNRATED)"); continue
    stype, neutral, _, _ = m[0][1]
    if stype != 2:
        print(f"{away} @ {home}  {ets:%a %d %b %H:%M} ET  skipped: not a regular-season game (type {stype})"); continue
    if ca not in R or ch not in R:
        print(f"{away} @ {home}  UNRATED"); continue
    tired = lambda tm: last.get(tm) is not None and (TODAY_ET - last[tm]).days == 1
    ha = 0 if neutral else HA
    pm_h = 1 / (1 + 10 ** (-(R[ch] + ha - B2B * tired(ch) + B2B * tired(ca) - R[ca]) / 400))
    mk_h = 1 - st.mean(imp(x) / (imp(x) + imp(y)) for _, x, y in rows)
    p_h = (1 - W) * mk_h + W * pm_h
    gap = abs(pm_h - mk_h)
    flagged = []
    for tm in (ca, ch):
        for pid, nme in stars(lead, tm):
            s_ = inj.get(tm, {}).get(pid, "")
            if s_ in BAD:
                flagged.append(f"{nme} {s_}")
    print(f"{away} @ {home}  {ets:%a %d %b %H:%M} ET{' neutral' if neutral else ''}  home: model {pm_h:.3f} market {mk_h:.3f} blend {p_h:.3f} gap {gap:.3f} books={len(rows)}"
          + (f"  B2B: {', '.join(x for x, f in ((away, tired(ca)), (home, tired(ch))) if f)}" if tired(ca) or tired(ch) else ""))
    print(f"   stars: {', '.join(n for tm in (ca, ch) for _, n in stars(lead, tm)) or 'n/a'}" + (f"  STAR FLAG: {'; '.join(flagged)}" if flagged else ""))
    for side, team, pb, pmod, i in (("away", away, 1 - p_h, 1 - pm_h, 1), ("home", home, p_h, pm_h, 2)):
        b = max(rows, key=lambda r: dec(r[i])); d = dec(b[i])
        ev_b = pb * (d - 1) - (1 - pb); ev_m = pmod * (d - 1) - (1 - pmod)
        tier = "STRONG" if ev_b >= .02 else ("MODEL PICK" if ev_m >= .03 and ev_b >= 0 else "")
        why = ""
        if tier and not (BAND[0] <= b[i] <= BAND[1]): tier, why = "", "outside price band"
        if tier and gap > DISAGREE_CAP: tier, why = "", "model/market gap too big"
        if tier and flagged: tier, why = "", "star player status"
        if tier and len(rows) < 6: tier, why = "", "fewer than 6 books"
        stk = stake(ev_b, d, .25, .02) if tier == "STRONG" else (stake(ev_m, d, .125, .01) if tier else 0)
        print(f"   {team[:22]:22} blend {pb:.3f} model {pmod:.3f} best {b[0]} {b[i]:+d} EV blend {ev_b*100:+.1f}% model {ev_m*100:+.1f}%"
              + (f"  <-- {tier} stake {stk:.2f}%" if tier else (f"  [no call: {why}]" if why else "")))
        if tier:
            calls.append(dict(sport="nba", tier=tier, event_id=f"nba:{ets:%Y-%m-%d}:{ca}@{ch}", date_et=f"{ets:%Y-%m-%d}", start_et=f"{ets:%a %d %b %H:%M} ET",
                              game=f"{away}@{home}", team=team, side=side, book=b[0], price=b[i], model=round(pmod, 3),
                              market=round((1 - mk_h) if side == "away" else mk_h, 3), ev_blend=round(ev_b, 4), ev_model=round(ev_m, 4),
                              stake_pct=round(stk, 2), start=start, books=len(rows),
                              starters={tm: [n for _, n in stars(lead, tm)] for tm in (ca, ch)},
                              conditional="bet only after the stars listed are confirmed available; void if one is a late scratch"))
print("\nCALLS_JSON", json.dumps(calls))
