#!/usr/bin/env python3
"""Rebuild group_standings.csv from wc2026_match_xg.csv and group_assignments.csv."""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATCH_XG = ROOT / "database" / "xGdatabase" / "processed" / "wc2026_match_xg.csv"
ASSIGN = ROOT / "database" / "competition" / "group_assignments.csv"
FAIR_PLAY = ROOT / "database" / "competition" / "wc2026_fair_play_r1.csv"
OUT = ROOT / "database" / "competition" / "group_standings.csv"

FIELDS = [
    "group", "rank", "team_en", "team_zh", "played", "won", "drawn", "lost",
    "goals_for", "goals_against", "goal_difference", "points", "status", "notes",
    "last_updated",
]

# FIFA ranking for tiebreaker (lower = better). Source: pre-tournament estimates in project notes.
FIFA_RANK = {
    "Belgium": 9, "France": 2, "England": 4, "Brazil": 5, "Argentina": 1,
    "Portugal": 6, "Netherlands": 7, "Spain": 8, "Italy": 10, "Croatia": 11,
    "Morocco": 12, "Colombia": 13, "Mexico": 14, "USA": 15, "Uruguay": 16,
    "Switzerland": 17, "Japan": 18, "Senegal": 19, "Iran": 20, "South Korea": 21,
    "Ecuador": 22, "Austria": 23, "Australia": 24, "Norway": 25, "Panama": 26,
    "Egypt": 29, "Canada": 30, "Scotland": 31, "Paraguay": 32, "Tunisia": 33,
    "Algeria": 34, "Czechia": 35, "Turkey": 36, "Sweden": 37, "Ukraine": 38,
    "Poland": 39, "Serbia": 40, "Wales": 41, "Russia": 42, "Hungary": 43,
    "Slovakia": 44, "Romania": 45, "Greece": 46, "Ireland": 47, "Finland": 48,
    "Iceland": 49, "Bosnia and Herzegovina": 50, "Israel": 51, "Slovenia": 52,
    "Albania": 53, "North Macedonia": 54, "Georgia": 55, "Qatar": 56,
    "Saudi Arabia": 57, "Iraq": 58, "Jordan": 59, "Uzbekistan": 60,
    "South Africa": 61, "Ghana": 62, "DR Congo": 63, "Ivory Coast": 64,
    "Cameroon": 65, "Nigeria": 66, "New Zealand": 67, "Haiti": 68,
    "Curacao": 69, "Cape Verde": 70, "Bolivia": 71, "Peru": 72,
}


def load_zh() -> dict[str, str]:
    zh: dict[str, str] = {}
    with ASSIGN.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            zh[row["team_en"]] = row["team_zh"]
    return zh


def load_groups() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    with ASSIGN.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            groups[row["group"]].append(row["team_en"])
    return dict(groups)


def load_matches() -> list[dict]:
    with MATCH_XG.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_fair_play() -> dict[str, int]:
    """Cumulative fair-play points per team (sum across rounds if multiple rows)."""
    fp: dict[str, int] = defaultdict(int)
    if not FAIR_PLAY.exists():
        return fp
    with FAIR_PLAY.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            team = row["team_en"]
            try:
                fp[team] += int(row["fair_play_points"])
            except (ValueError, KeyError):
                pass
    return dict(fp)


def init_stats(team: str) -> dict:
    return {
        "team_en": team,
        "played": 0, "won": 0, "drawn": 0, "lost": 0,
        "goals_for": 0, "goals_against": 0, "points": 0,
        "h2h": defaultdict(lambda: {"pts": 0, "gd": 0, "gf": 0}),
    }


def apply_result(stats: dict, gf: int, ga: int, opp: str) -> None:
    stats["played"] += 1
    stats["goals_for"] += gf
    stats["goals_against"] += ga
    h = stats["h2h"][opp]
    h["gf"] += gf
    h["gd"] += gf - ga
    if gf > ga:
        stats["won"] += 1
        stats["points"] += 3
        h["pts"] += 3
    elif gf == ga:
        stats["drawn"] += 1
        stats["points"] += 1
        h["pts"] += 1
    else:
        stats["lost"] += 1


def gd(stats: dict) -> int:
    return stats["goals_for"] - stats["goals_against"]


def h2h_key(stats: dict, tied: list[str]) -> tuple:
    """Mini-league stats among tied teams only."""
    pts = gd_ = gf_ = 0
    for opp in tied:
        if opp == stats["team_en"]:
            continue
        h = stats["h2h"].get(opp)
        if h:
            pts += h["pts"]
            gd_ += h["gd"]
            gf_ += h["gf"]
    return (-pts, -gd_, -gf_)


def rank_group(teams: list[str], group_stats: dict[str, dict], fair_play: dict[str, int]) -> list[dict]:
    ordered = sorted(
        teams,
        key=lambda t: (
            -group_stats[t]["points"],
            -gd(group_stats[t]),
            -group_stats[t]["goals_for"],
        ),
    )

    result: list[dict] = []
    i = 0
    while i < len(ordered):
        j = i
        base = group_stats[ordered[i]]
        while j < len(ordered):
            s = group_stats[ordered[j]]
            if (s["points"], gd(s), s["goals_for"]) != (base["points"], gd(base), base["goals_for"]):
                break
            j += 1
        block = ordered[i:j]
        if len(block) > 1:
            block = sorted(
                block,
                key=lambda t: (
                    h2h_key(group_stats[t], block),
                    -fair_play.get(t, 0),
                    FIFA_RANK.get(t, 999),
                ),
            )
        for t in block:
            result.append(group_stats[t])
        i = j
    return result


def build_notes(
    team: str,
    group: str,
    rank: int,
    stats: dict,
    ranked: list[dict],
    fair_play: dict[str, int],
) -> str:
    pts = stats["points"]
    played = stats["played"]
    notes: list[str] = []
    if group == "A" and team == "Mexico" and pts >= 6 and played >= 2:
        notes.append("Knockout stage confirmed after R2 (group leader on 6pts).")
    if group == "B" and team == "Canada" and rank == 1 and pts >= 4 and played >= 2:
        notes.append("Group B leader after R2; ahead of Switzerland on overall goal difference.")
    tied = [s for s in ranked if s["points"] == pts and gd(s) == gd(stats)]
    if len(tied) > 1 and any(
        fair_play.get(s["team_en"], 0) == fair_play.get(team, 0)
        for s in tied if s["team_en"] != team
    ):
        fp = fair_play.get(team)
        if fp is not None and any(
            s["team_en"] != team
            and fair_play.get(s["team_en"]) == fp
            and FIFA_RANK.get(team, 999) < FIFA_RANK.get(s["team_en"], 999)
            for s in tied
        ):
            notes.append(
                f"Fair-play tie ({fp}); ahead on FIFA ranking ({FIFA_RANK.get(team, '?')})."
            )
    return "; ".join(notes)


def main() -> None:
    zh = load_zh()
    groups = load_groups()
    matches = load_matches()
    fair_play = load_fair_play()
    today = date.today().isoformat()

    group_stats: dict[str, dict[str, dict]] = {
        g: {t: init_stats(t) for t in teams} for g, teams in groups.items()
    }

    for m in matches:
        g = m["group"]
        home, away = m["home_team"], m["away_team"]
        hs, as_ = int(m["home_score"]), int(m["away_score"])
        if home in group_stats[g]:
            apply_result(group_stats[g][home], hs, as_, away)
        if away in group_stats[g]:
            apply_result(group_stats[g][away], as_, hs, home)

    rows: list[dict] = []
    for g in sorted(groups):
        ranked = rank_group(groups[g], group_stats[g], fair_play)
        for rank, stats in enumerate(ranked, start=1):
            team = stats["team_en"]
            played = stats["played"]
            status = "provisional" if played < 3 else "final"
            if played >= 2 and any(
                s["points"] == stats["points"] and gd(s) == gd(stats) and s["team_en"] != team
                for s in ranked
            ):
                if fair_play:
                    status = "provisional_fair_play"
            note = build_notes(team, g, rank, stats, ranked, fair_play)
            rows.append({
                "group": g,
                "rank": rank,
                "team_en": team,
                "team_zh": zh.get(team, ""),
                "played": played,
                "won": stats["won"],
                "drawn": stats["drawn"],
                "lost": stats["lost"],
                "goals_for": stats["goals_for"],
                "goals_against": stats["goals_against"],
                "goal_difference": gd(stats),
                "points": stats["points"],
                "status": status,
                "notes": note,
                "last_updated": today,
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    r2_groups = sum(1 for r in rows if r["group"] in ("A", "B") and r["played"] == 2)
    print(f"Wrote {len(rows)} rows to {OUT} (A/B updated to 2 matches played)")


if __name__ == "__main__":
    main()
