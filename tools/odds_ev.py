"""Pull SBR moneylines, devig each book, average, report best-price EV per side.

Usage: python3 -I tools/odds_ev.py [league-slug ...]
Default slugs: nhl-hockey nba-basketball mlb-baseball nfl-football college-football
Prints a table of upcoming games and flags sides with EV >= 2%.
"""
import json, re, statistics as st, subprocess, sys, datetime as dt

SLUGS = sys.argv[1:] or ["nhl-hockey", "nba-basketball", "mlb-baseball", "nfl-football", "college-football"]
THRESH = 0.02

imp = lambda o: -o / (-o + 100) if o < 0 else 100 / (o + 100)
dec = lambda o: 1 + 100 / -o if o < 0 else 1 + o / 100

now = dt.datetime.now(dt.timezone.utc)
print("pulled", now.strftime("%Y-%m-%d %H:%M UTC"))
for slug in SLUGS:
    url = f"https://www.sportsbookreview.com/betting-odds/{slug}/"
    h = subprocess.run(["curl", "-sS", "-m", "30", "-A", "Mozilla/5.0", url],
                       capture_output=True, text=True).stdout
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    if not m:
        print(slug, "no data"); continue
    d = json.loads(m.group(1))
    for t in d["props"]["pageProps"]["oddsTables"]:
        for g in t["oddsTableModel"]["gameRows"]:
            v = g["gameView"]
            start = dt.datetime.fromisoformat(v["startDate"])
            if start < now:
                continue
            rows = [(o["sportsbook"], o["currentLine"]["awayOdds"], o["currentLine"]["homeOdds"])
                    for o in g["oddsViews"]
                    if o and "MoneyLine" in o["viewType"]
                    and o["currentLine"]["awayOdds"] and o["currentLine"]["homeOdds"]]
            if len(rows) < 4:
                continue
            fa = [imp(a) / (imp(a) + imp(h_)) for _, a, h_ in rows]
            vig = [imp(a) + imp(h_) - 1 for _, a, h_ in rows]
            pa = st.mean(fa)
            print(f"\n{v['awayTeam']['shortName']} @ {v['homeTeam']['shortName']}  {start:%H:%M} UTC  "
                  f"books={len(rows)} sd={st.pstdev(fa):.3f} vig={st.mean(vig):.3f}")
            for side, p, i, name in (("away", pa, 1, v["awayTeam"]["shortName"]),
                                     ("home", 1 - pa, 2, v["homeTeam"]["shortName"])):
                b = max(rows, key=lambda r: dec(r[i]))
                ev = p * (dec(b[i]) - 1) - (1 - p)
                flag = "  <-- BET" if ev >= THRESH else ""
                print(f"  {name:4} fair {p*100:.1f}%  best {b[0]} {b[i]:+d}  EV {ev*100:+.1f}%{flag}")
