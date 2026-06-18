"""Fetch WC2026 round-1 player match stats from FotMob page __NEXT_DATA__."""
import csv
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

XG_ROOT = Path(__file__).resolve().parents[3]
MATCH_CSV = XG_ROOT / "processed" / "wc2026_match_xg.csv"
OUT_CSV = XG_ROOT / "processed" / "wc2026_player_match_stats.csv"

TEAM_NAME_NORMALIZE = {
    "Turkiye": "Turkey",
}


def canonical_team(name):
    return TEAM_NAME_NORMALIZE.get(name, name)


HEADER = [
    "match_date", "group", "team", "opponent", "player", "position", "minutes",
    "goals", "assists", "shots", "xg", "xa", "key_passes", "rating", "big_chances",
    "source", "source_url", "quality_flag",
]

POS_MAP = {
    0: "GK",
    1: "DF",
    2: "MF",
    3: "FW",
}


def fetch_page_data(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(request, timeout=45).read().decode("utf-8", "replace")
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not match:
        raise RuntimeError("No __NEXT_DATA__ found")
    return json.loads(match.group(1))


def format_player_name(player):
    first = (player.get("firstName") or "").strip()
    last = (player.get("lastName") or "").strip()
    if first and last:
        return f"{first} {last.upper()}"
    name = (player.get("name") or "").strip()
    parts = name.split()
    if len(parts) >= 2:
        return " ".join(parts[:-1] + [parts[-1].upper()])
    return name.upper()


def player_position(player):
    if player.get("isGoalkeeper"):
        return "GK"
    usual = player.get("usualPosition")
    if isinstance(usual, int) and usual in POS_MAP:
        return POS_MAP[usual]
    if isinstance(usual, dict):
        key = usual.get("key") or usual.get("shortName") or ""
        short = {
            "keeper": "GK",
            "defender": "DF",
            "midfielder": "MF",
            "forward": "FW",
            "striker": "FW",
            "attacker": "FW",
        }
        if key in short:
            return short[key]
    pid = player.get("positionId")
    if isinstance(pid, int) and pid in POS_MAP:
        return POS_MAP[pid]
    upid = player.get("usualPlayingPositionId")
    if isinstance(upid, int) and upid in POS_MAP:
        return POS_MAP[upid]
    return ""


def flatten_stats(pdata):
    out = {}
    for section in pdata.get("stats", []) or []:
        for _title, item in (section.get("stats") or {}).items():
            key = item.get("key")
            if not key:
                continue
            stat = item.get("stat") or {}
            out[key] = stat.get("value")
    return out


def safe_num(val, decimals=3):
    if val is None or val == "":
        return ""
    try:
        num = float(val)
        if decimals == 0:
            return str(int(num))
        s = f"{num:.{decimals}f}".rstrip("0").rstrip(".")
        return s
    except (TypeError, ValueError):
        return ""


def has_contribution(stat_map, perf):
    goals = stat_map.get("goals") or perf.get("goals") or 0
    assists = stat_map.get("assists") or perf.get("assists") or 0
    if goals or assists:
        return True
    for key in (
        "chances_created",
        "expected_goals",
        "expected_assists",
        "total_shots",
        "big_chance_created",
        "big_chance_created_team_title",
        "big_chance_missed",
    ):
        if stat_map.get(key):
            return True
    return False


def build_row(player, pdata, team, opponent, match_date, group, source_url, is_starter):
    perf = player.get("performance") or {}
    stat_map = flatten_stats(pdata) if pdata else {}

    minutes = stat_map.get("minutes_played")
    if minutes is None:
        minutes = perf.get("minutesPlayed")
    goals = stat_map.get("goals", perf.get("goals", 0)) or 0
    assists = stat_map.get("assists", perf.get("assists", 0)) or 0
    shots = stat_map.get("total_shots", "")
    xg = safe_num(stat_map.get("expected_goals"))
    xa = safe_num(stat_map.get("expected_assists"))
    key_passes = stat_map.get("chances_created", "")
    rating = safe_num(perf.get("rating") or stat_map.get("rating_title"))
    big_chances = stat_map.get("big_chance_created") or stat_map.get("big_chance_created_team_title") or ""

    if not is_starter:
        if not minutes:
            return None
        if not has_contribution(stat_map, perf):
            return None

    has_adv = any(v not in ("", None) for v in [xg, xa, rating, key_passes, big_chances, shots])
    has_basic = minutes not in ("", None)
    quality = "ok" if has_adv and has_basic else "partial"

    return {
        "match_date": match_date,
        "group": group,
        "team": team,
        "opponent": opponent,
        "player": format_player_name(player if pdata else player),
        "position": player_position(pdata if pdata else player),
        "minutes": safe_num(minutes, 0),
        "goals": int(goals) if goals is not None else 0,
        "assists": int(assists) if assists is not None else 0,
        "shots": safe_num(shots, 0) if shots != "" else "",
        "xg": xg,
        "xa": xa,
        "key_passes": safe_num(key_passes, 0) if key_passes != "" else "",
        "rating": rating,
        "big_chances": safe_num(big_chances, 0) if big_chances != "" else "",
        "source": "FotMob/Opta",
        "source_url": source_url,
        "quality_flag": quality,
    }


def parse_match(page_data, match_date, group, source_url):
    content = page_data["props"]["pageProps"]["content"]
    general = page_data["props"]["pageProps"]["general"]
    player_stats = content.get("playerStats") or {}
    lineup = content.get("lineup") or {}
    rows = []

    home_name = canonical_team(general["homeTeam"]["name"])
    away_name = canonical_team(general["awayTeam"]["name"])

    for side_key, team, opponent in (
        ("homeTeam", home_name, away_name),
        ("awayTeam", away_name, home_name),
    ):
        side = lineup.get(side_key) or {}
        for p in side.get("starters") or []:
            pdata = player_stats.get(str(p["id"]), {})
            row = build_row(p, pdata, team, opponent, match_date, group, source_url, True)
            if row:
                rows.append(row)
        for p in side.get("subs") or []:
            pdata = player_stats.get(str(p["id"]), {})
            row = build_row(p, pdata, team, opponent, match_date, group, source_url, False)
            if row:
                rows.append(row)
    return rows


def main():
    matches = list(csv.DictReader(MATCH_CSV.open(encoding="utf-8")))
    all_rows = []
    failures = []

    for i, m in enumerate(matches):
        url = m["source_url"]
        label = f"{m['home_team']} vs {m['away_team']}"
        try:
            page = fetch_page_data(url)
            rows = parse_match(page, m["match_date"], m["group"], url)
            all_rows.extend(rows)
            print(f"[{i+1}/{len(matches)}] OK {label}: {len(rows)} players")
        except Exception as exc:
            failures.append((label, str(exc)))
            print(f"[{i+1}/{len(matches)}] FAIL {label}: {exc}")
        time.sleep(1.2)

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nWrote {len(all_rows)} rows -> {OUT_CSV}")
    if failures:
        print("Failures:")
        for label, err in failures:
            print(f"  {label}: {err}")


if __name__ == "__main__":
    main()
