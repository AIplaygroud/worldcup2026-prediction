#!/usr/bin/env python3
"""Fetch R1 lineups from FotMob __NEXT_DATA__ and write CSV outputs."""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCH_CSV = ROOT / "processed" / "wc2026_match_xg.csv"
LINEUPS_OUT = ROOT / "processed" / "wc2026_lineups_r1.csv"
PRIORS_OUT = ROOT / "processed" / "wc2026_lineup_priors.csv"
TODAY = date.today().isoformat()
SOURCE = "FotMob/Opta"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

LINEUP_FIELDS = [
    "match_date", "group", "team", "opponent", "formation", "player", "shirt_no",
    "position", "is_starter", "minutes", "sub_in", "sub_out", "sub_reason",
    "source", "source_url", "last_verified",
]
PRIOR_FIELDS = [
    "team", "default_formation", "formation_flex", "nailed_starters",
    "rotation_risk_players", "protected_players", "r1_minutes_load",
    "congestion_note", "confidence", "source", "last_verified",
]

POSITION_ID_MAP = {
    11: "GK",
    32: "RB", 34: "CB", 36: "CB", 38: "LB",
    64: "DM", 65: "CDM", 66: "DM", 67: "DM",
    82: "RM", 84: "CM", 86: "CAM", 88: "LM",
    100: "RW", 102: "RW", 103: "RW",
    104: "ST", 105: "ST", 106: "ST", 107: "LW",
}
USUAL_POS_MAP = {0: "GK", 1: "DEF", 2: "MID", 3: "FWD"}

TEAM_ALIASES = {
    "Turkiye": "Turkey",
    "Türkiye": "Turkey",
    "Cote d'Ivoire": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "Korea Republic": "South Korea",
    "USA": "USA",
    "United States": "USA",
    "Congo DR": "DR Congo",
    "Congo, DR": "DR Congo",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def get_position(player: dict) -> str:
    pid = player.get("positionId")
    if pid in POSITION_ID_MAP:
        return POSITION_ID_MAP[pid]
    up = player.get("usualPlayingPositionId")
    return USUAL_POS_MAP.get(up, "")


def minutes_from_stats(player_stats: dict, player_id: int) -> int | None:
    entry = player_stats.get(str(player_id))
    if not entry:
        return None
    for block in entry.get("stats", []):
        mins = block.get("stats", {}).get("Minutes played", {})
        stat = mins.get("stat", {})
        if stat.get("type") == "integer" and "value" in stat:
            return int(stat["value"])
    return None


def parse_sub_events(performance: dict) -> tuple[str, str, str]:
    sub_in, sub_out, reason = "", "", ""
    for ev in performance.get("substitutionEvents", []) or []:
        t = ev.get("type", "")
        minute = str(ev.get("time", ""))
        r = ev.get("reason", "") or ""
        if t == "subIn":
            sub_in = minute
            reason = r
        elif t == "subOut":
            sub_out = minute
            reason = r or reason
    return sub_in, sub_out, reason


def card_flags(performance: dict) -> tuple[bool, bool]:
    yellow = red = False
    for ev in performance.get("events", []) or []:
        if ev.get("type") == "yellowCard":
            yellow = True
        elif ev.get("type") == "redCard":
            red = True
    return yellow, red


def resolve_team_name(fotmob_name: str, home: str, away: str) -> str | None:
    if fotmob_name in (home, away):
        return fotmob_name
    alias = TEAM_ALIASES.get(fotmob_name)
    if alias and alias in (home, away):
        return alias
    for candidate in (home, away):
        if candidate in fotmob_name or fotmob_name in candidate:
            return candidate
    return None


def extract_players(
    team_block: dict,
    is_starter_flag: bool,
    player_stats: dict,
) -> list[dict]:
    rows = []
    key = "starters" if is_starter_flag else "subs"
    for p in team_block.get(key, []) or []:
        perf = p.get("performance", {}) or {}
        sub_in, sub_out, sub_reason = parse_sub_events(perf)
        yellow, red = card_flags(perf)

        # Only include subs who actually entered
        if not is_starter_flag and not sub_in:
            continue

        minutes = minutes_from_stats(player_stats, p["id"])
        if minutes is None:
            if is_starter_flag:
                minutes = int(sub_out) if sub_out else 90
            else:
                minutes = 90 - int(sub_in) if sub_in else ""
                if sub_out:
                    minutes = int(sub_out) - int(sub_in)

        if red:
            sub_reason = "red_card"

        rows.append({
            "player": p["name"],
            "shirt_no": p.get("shirtNumber", ""),
            "position": get_position(p),
            "is_starter": "yes" if is_starter_flag else "no",
            "minutes": minutes,
            "sub_in": sub_in,
            "sub_out": sub_out,
            "sub_reason": sub_reason,
            "_yellow": yellow,
            "_red": red,
        })
    return rows


def parse_match(html: str, home: str, away: str) -> dict[str, dict]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("no __NEXT_DATA__")
    data = json.loads(m.group(1))
    content = data["props"]["pageProps"]["content"]
    lineup = content["lineup"]
    player_stats = content.get("playerStats", {})

    result = {}
    for side in ("homeTeam", "awayTeam"):
        block = lineup[side]
        team = resolve_team_name(block["name"], home, away)
        if not team:
            raise ValueError(f"cannot map team {block['name']!r} to {home}/{away}")
        players = extract_players(block, True, player_stats)
        players += extract_players(block, False, player_stats)
        result[team] = {
            "formation": block.get("formation", ""),
            "players": players,
            "starters_count": len(block.get("starters", []) or []),
        }
    return result


def load_matches() -> list[dict]:
    with open(MATCH_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_priors(team_agg: dict) -> list[dict]:
    priors = []
    for team in sorted(team_agg):
        info = team_agg[team]
        formation = info.get("formation", "")
        players = info.get("players", [])
        nailed, rotation_risk, protected = [], [], []
        total_mins = 0

        for p in players:
            if p.get("_yellow"):
                protected.append(p["player"])
            if p.get("_red") or p.get("sub_reason") == "red_card":
                protected.append(p["player"])

            if p["is_starter"] != "yes":
                continue
            mins = p.get("minutes")
            if isinstance(mins, int):
                total_mins += mins
            elif mins != "" and mins is not None:
                try:
                    total_mins += int(mins)
                except (TypeError, ValueError):
                    pass

            if p.get("sub_out"):
                try:
                    if int(p["sub_out"]) <= 70:
                        rotation_risk.append(p["player"])
                except (TypeError, ValueError):
                    pass
            elif mins == 90 or (isinstance(mins, int) and mins >= 85):
                nailed.append(p["player"])

        priors.append({
            "team": team,
            "default_formation": formation,
            "formation_flex": "",
            "nailed_starters": "|".join(nailed),
            "rotation_risk_players": "|".join(rotation_risk),
            "protected_players": "|".join(dict.fromkeys(protected)),
            "r1_minutes_load": str(total_mins),
            "congestion_note": "R1 prior only; override with official lineup before R2",
            "confidence": "r1_prior",
            "source": SOURCE,
            "last_verified": TODAY,
        })
    return priors


def main() -> int:
    matches = load_matches()
    lineup_rows: list[dict] = []
    coverage: list[str] = []
    team_agg: dict = defaultdict(lambda: {"formation": "", "players": []})

    for i, m in enumerate(matches):
        home, away = m["home_team"], m["away_team"]
        url = m["source_url"]
        label = f"{home} vs {away}"
        print(f"[{i + 1}/24] {label} ...", flush=True)
        try:
            html = fetch(url)
            parsed = parse_match(html, home, away)
        except Exception as exc:
            coverage.append(f"{label}: ERROR - {exc}")
            time.sleep(0.5)
            continue

        match_ok = True
        for team in (home, away):
            if team not in parsed:
                coverage.append(f"{label} ({team}): MISSING")
                match_ok = False
                continue
            pdata = parsed[team]
            sc = pdata["starters_count"]
            if sc != 11:
                coverage.append(f"{label} ({team}): gap {sc}/11 starters")
                match_ok = False
            else:
                coverage.append(f"{label} ({team}): complete 11 starters")

            opp = away if team == home else home
            if not team_agg[team]["formation"]:
                team_agg[team]["formation"] = pdata["formation"]
            team_agg[team]["players"].extend(pdata["players"])

            for p in pdata["players"]:
                lineup_rows.append({
                    "match_date": m["match_date"],
                    "group": m["group"],
                    "team": team,
                    "opponent": opp,
                    "formation": pdata["formation"],
                    "player": p["player"],
                    "shirt_no": p["shirt_no"],
                    "position": p["position"],
                    "is_starter": p["is_starter"],
                    "minutes": p["minutes"],
                    "sub_in": p["sub_in"],
                    "sub_out": p["sub_out"],
                    "sub_reason": p["sub_reason"],
                    "source": SOURCE,
                    "source_url": url,
                    "last_verified": TODAY,
                })

        if match_ok:
            pass  # both teams complete
        time.sleep(0.6)

    LINEUPS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(LINEUPS_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LINEUP_FIELDS)
        w.writeheader()
        w.writerows(lineup_rows)

    priors = build_priors(team_agg)
    with open(PRIORS_OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PRIOR_FIELDS)
        w.writeheader()
        w.writerows(priors)

    complete_matches = sum(
        1 for c in coverage if "complete 11 starters" in c
    ) // 2
    print("\n=== COVERAGE ===")
    for c in coverage:
        print(c)
    print(f"\nMatches with both teams complete: {complete_matches}/24")
    print(f"Wrote {len(lineup_rows)} lineup rows -> {LINEUPS_OUT}")
    print(f"Wrote {len(priors)} team priors -> {PRIORS_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
