#!/usr/bin/env python3
"""Download nflverse weekly player stats + schedule and write compact JSON for the Prop Board page.
Usage: python3 build_nfl_props.py OUT_DIR   (writes OUT_DIR/data.json)"""
import csv, io, json, sys, urllib.request, collections

BASE = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_%d.csv"
SCHED = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
SEASONS = (2024, 2025, 2026)
POS = ("QB", "RB", "WR", "TE")
# order matters: index in each game row after the 5 id fields
STATS = [("pass_att","attempts"),("pass_cmp","completions"),("pass_yds","passing_yards"),("pass_td","passing_tds"),
         ("pass_int","passing_interceptions"),("rush_att","carries"),("rush_yds","rushing_yards"),("rush_td","rushing_tds"),
         ("tgt","targets"),("rec","receptions"),("rec_yds","receiving_yards"),("rec_td","receiving_tds")]

def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))

def num(v):
    try: return float(v)
    except (TypeError, ValueError): return 0.0

rows = []
for y in SEASONS:
    try: rows += get(BASE % y)
    except Exception as e: print("skip", y, e, file=sys.stderr)
rows = [r for r in rows if r["position"] in POS]
teams = sorted({r["team"] for r in rows} | {r["opponent_team"] for r in rows})
tix = {t: i for i, t in enumerate(teams)}

# team games per season/week/type, to measure missing rows
team_games = collections.defaultdict(set)
for r in rows: team_games[(r["season"], r["team"])].add((r["season_type"], int(r["week"])))

by = collections.defaultdict(list)
for r in rows: by[r["player_id"]].append(r)

def keep(rs):
    cur = [r for r in rs if r["season"] in ("2025", "2026")]
    return (sum(num(r["attempts"]) for r in cur) >= 50 or sum(num(r["carries"]) for r in cur) >= 30
            or sum(num(r["targets"]) for r in cur) >= 20)

players = []
for pid, rs in by.items():
    if not keep(rs): continue
    rs.sort(key=lambda r: (int(r["season"]), r["season_type"] == "POST", int(r["week"])))
    games = []
    for r in rs:
        g = [int(r["season"]), int(r["week"]), 1 if r["season_type"] == "POST" else 0, tix[r["team"]], tix[r["opponent_team"]]]
        g += [int(num(r[c])) for _, c in STATS]
        g.append(int(round(num(r["target_share"]) * 1000)))
        games.append(g)
    last = rs[-1]
    players.append({"id": pid, "n": last["player_display_name"], "p": last["position"], "t": tix[last["team"]], "g": games})

# opponent allowed per game by position (2025 full, 2026 to date), fantasy-relevant stats
def allowed(season):
    agg = collections.defaultdict(lambda: collections.defaultdict(float))
    gm = collections.defaultdict(set)
    for r in rows:
        if r["season"] != str(season) or r["season_type"] != "REG": continue
        k = (r["opponent_team"], r["position"])
        gm[r["opponent_team"]].add(int(r["week"]))
        for s, c in STATS: agg[k][s] += num(r[c])
    out = {}
    for (opp, pos), d in agg.items():
        n = len(gm[opp])
        out.setdefault(pos, {})[tix[opp]] = {s: round(v / n, 1) for s, v in d.items()} | {"n": n}
    return out

# schedule: next unplayed week
sched = get(SCHED)
cur = [g for g in sched if g["season"] == str(max(SEASONS)) and g["game_type"] == "REG"]
played = [int(g["week"]) for g in cur if g["result"] != ""]
nextwk = (max(played) + 1) if played else 1
nxt = {}
for g in cur:
    if int(g["week"]) != nextwk: continue
    spread = float(g["spread_line"]) if g["spread_line"] else None  # positive = home favored
    total = float(g["total_line"]) if g["total_line"] else None
    for side, team, opp in (("a", g["away_team"], g["home_team"]), ("h", g["home_team"], g["away_team"])):
        if team not in tix or opp not in tix: continue
        fav = None if spread is None else (spread if side == "h" else -spread)
        nxt[tix[team]] = {"o": tix[opp], "h": 1 if side == "h" else 0, "d": g["gameday"], "t": g["gametime"], "f": fav, "tot": total}

weeks26 = sorted({int(r["week"]) for r in rows if r["season"] == "2026" and r["season_type"] == "REG"})
out = {"src": "nflverse", "thru": {"season": max(SEASONS), "week": max(weeks26) if weeks26 else 0},
       "stats": [s for s, _ in STATS], "teams": teams, "players": players,
       "allowed": {"2025": allowed(2025), "2026": allowed(2026)}, "next": {"week": nextwk, "games": nxt}}
json.dump(out, open(sys.argv[1].rstrip("/") + "/data.json", "w"), separators=(",", ":"))
print("players", len(players), "teams", len(teams), "next week", nextwk, "games", len(nxt))

# assemble the page from templates next to this script
import os
tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prop_board")
data = open(sys.argv[1].rstrip("/") + "/data.json").read()
page = (open(os.path.join(tpl, "head.html")).read() + open(os.path.join(tpl, "body.html")).read()
        + "<script>\nvar DATA=" + data + ";\n" + open(os.path.join(tpl, "page.js")).read() + "</script>\n")
open(sys.argv[1].rstrip("/") + "/prop-board.html", "w").write(page)
print("wrote prop-board.html")
