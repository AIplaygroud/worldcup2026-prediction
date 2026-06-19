#!/usr/bin/env python3
"""Build wc2026_group_fixtures.csv — full 72-match group stage schedule."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "database" / "competition" / "wc2026_group_fixtures.csv"
ASSIGN = ROOT / "database" / "competition" / "group_assignments.csv"
MATCH_XG = ROOT / "database" / "xGdatabase" / "processed" / "wc2026_match_xg.csv"
LAST_VERIFIED = "2026-06-19"
SOURCE = "FIFA/Roadtrips schedule cross-checked with FotMob R1"

# FIFA match numbers 1–72; pairings from official draw schedule (Roadtrips/FIFA).
# Dates for R1 overridden below from wc2026_match_xg.csv where played.
FIXTURES = [
    # (fifa_id, group, round, date, et, local, home, away, venue, city, country)
    (1, "A", 1, "2026-06-11", "15:00", "13:00", "Mexico", "South Africa", "Estadio Azteca", "Mexico City", "Mexico"),
    (2, "A", 1, "2026-06-11", "22:00", "20:00", "South Korea", "Czechia", "Estadio Akron", "Guadalajara", "Mexico"),
    (3, "B", 1, "2026-06-12", "15:00", "15:00", "Canada", "Bosnia and Herzegovina", "BMO Field", "Toronto", "Canada"),
    (4, "D", 1, "2026-06-12", "21:00", "18:00", "USA", "Paraguay", "SoFi Stadium", "Los Angeles", "USA"),
    (5, "C", 1, "2026-06-13", "21:00", "21:00", "Haiti", "Scotland", "Gillette Stadium", "Boston", "USA"),
    (6, "D", 1, "2026-06-13", "24:00", "21:00", "Australia", "Turkey", "BC Place", "Vancouver", "Canada"),
    (7, "C", 1, "2026-06-13", "18:00", "18:00", "Brazil", "Morocco", "MetLife Stadium", "New York/New Jersey", "USA"),
    (8, "B", 1, "2026-06-13", "15:00", "12:00", "Qatar", "Switzerland", "Levi's Stadium", "San Francisco Bay Area", "USA"),
    (9, "E", 1, "2026-06-14", "19:00", "19:00", "Ivory Coast", "Ecuador", "Lincoln Financial Field", "Philadelphia", "USA"),
    (10, "E", 1, "2026-06-14", "13:00", "12:00", "Germany", "Curacao", "NRG Stadium", "Houston", "USA"),
    (11, "F", 1, "2026-06-14", "16:00", "15:00", "Netherlands", "Japan", "AT&T Stadium", "Dallas", "USA"),
    (12, "F", 1, "2026-06-14", "22:00", "20:00", "Sweden", "Tunisia", "Estadio BBVA", "Monterrey", "Mexico"),
    (13, "H", 1, "2026-06-15", "18:00", "18:00", "Saudi Arabia", "Uruguay", "Hard Rock Stadium", "Miami", "USA"),
    (14, "H", 1, "2026-06-15", "12:00", "12:00", "Spain", "Cape Verde", "Mercedes-Benz Stadium", "Atlanta", "USA"),
    (15, "G", 1, "2026-06-15", "21:00", "18:00", "Iran", "New Zealand", "SoFi Stadium", "Los Angeles", "USA"),
    (16, "G", 1, "2026-06-15", "15:00", "12:00", "Belgium", "Egypt", "Lumen Field", "Seattle", "USA"),
    (17, "I", 1, "2026-06-16", "15:00", "15:00", "France", "Senegal", "MetLife Stadium", "New York/New Jersey", "USA"),
    (18, "I", 1, "2026-06-16", "18:00", "18:00", "Iraq", "Norway", "Gillette Stadium", "Boston", "USA"),
    (19, "J", 1, "2026-06-16", "21:00", "20:00", "Argentina", "Algeria", "Arrowhead Stadium", "Kansas City", "USA"),
    (20, "J", 1, "2026-06-16", "24:00", "21:00", "Austria", "Jordan", "Levi's Stadium", "San Francisco Bay Area", "USA"),
    (21, "L", 1, "2026-06-17", "19:00", "19:00", "Ghana", "Panama", "BMO Field", "Toronto", "Canada"),
    (22, "L", 1, "2026-06-17", "16:00", "15:00", "England", "Croatia", "AT&T Stadium", "Dallas", "USA"),
    (23, "K", 1, "2026-06-17", "13:00", "12:00", "Portugal", "DR Congo", "NRG Stadium", "Houston", "USA"),
    (24, "K", 1, "2026-06-17", "22:00", "20:00", "Uzbekistan", "Colombia", "Estadio Azteca", "Mexico City", "Mexico"),
    (25, "A", 2, "2026-06-18", "12:00", "12:00", "Czechia", "South Africa", "Mercedes-Benz Stadium", "Atlanta", "USA"),
    (26, "B", 2, "2026-06-18", "15:00", "12:00", "Switzerland", "Bosnia and Herzegovina", "SoFi Stadium", "Los Angeles", "USA"),
    (27, "B", 2, "2026-06-18", "18:00", "15:00", "Canada", "Qatar", "BC Place", "Vancouver", "Canada"),
    (28, "A", 2, "2026-06-18", "21:00", "19:00", "Mexico", "South Korea", "Estadio Akron", "Guadalajara", "Mexico"),
    (29, "C", 2, "2026-06-19", "21:00", "21:00", "Brazil", "Haiti", "Lincoln Financial Field", "Philadelphia", "USA"),
    (30, "C", 2, "2026-06-19", "18:00", "18:00", "Scotland", "Morocco", "Gillette Stadium", "Boston", "USA"),
    (31, "D", 2, "2026-06-19", "23:00", "20:00", "Turkey", "Paraguay", "Levi's Stadium", "San Francisco Bay Area", "USA"),
    (32, "D", 2, "2026-06-19", "15:00", "12:00", "USA", "Australia", "Lumen Field", "Seattle", "USA"),
    (33, "E", 2, "2026-06-20", "16:00", "16:00", "Germany", "Ivory Coast", "BMO Field", "Toronto", "Canada"),
    (34, "E", 2, "2026-06-20", "20:00", "19:00", "Ecuador", "Curacao", "Arrowhead Stadium", "Kansas City", "USA"),
    (35, "F", 2, "2026-06-20", "13:00", "12:00", "Netherlands", "Sweden", "NRG Stadium", "Houston", "USA"),
    (36, "F", 2, "2026-06-20", "24:00", "22:00", "Tunisia", "Japan", "Estadio BBVA", "Monterrey", "Mexico"),
    (37, "H", 2, "2026-06-21", "18:00", "18:00", "Uruguay", "Cape Verde", "Hard Rock Stadium", "Miami", "USA"),
    (38, "H", 2, "2026-06-21", "12:00", "12:00", "Spain", "Saudi Arabia", "Mercedes-Benz Stadium", "Atlanta", "USA"),
    (39, "G", 2, "2026-06-21", "15:00", "12:00", "Belgium", "Iran", "SoFi Stadium", "Los Angeles", "USA"),
    (40, "G", 2, "2026-06-21", "21:00", "18:00", "New Zealand", "Egypt", "BC Place", "Vancouver", "Canada"),
    (41, "I", 2, "2026-06-22", "20:00", "20:00", "Norway", "Senegal", "MetLife Stadium", "New York/New Jersey", "USA"),
    (42, "I", 2, "2026-06-22", "17:00", "17:00", "France", "Iraq", "Lincoln Financial Field", "Philadelphia", "USA"),
    (43, "J", 2, "2026-06-22", "13:00", "12:00", "Argentina", "Austria", "AT&T Stadium", "Dallas", "USA"),
    (44, "J", 2, "2026-06-22", "23:00", "20:00", "Jordan", "Algeria", "Levi's Stadium", "San Francisco Bay Area", "USA"),
    (45, "L", 2, "2026-06-23", "16:00", "16:00", "England", "Ghana", "Gillette Stadium", "Boston", "USA"),
    (46, "L", 2, "2026-06-23", "19:00", "19:00", "Panama", "Croatia", "BMO Field", "Toronto", "Canada"),
    (47, "K", 2, "2026-06-23", "13:00", "12:00", "Portugal", "Uzbekistan", "NRG Stadium", "Houston", "USA"),
    (48, "K", 2, "2026-06-23", "22:00", "20:00", "Colombia", "DR Congo", "Estadio Akron", "Guadalajara", "Mexico"),
    (49, "C", 3, "2026-06-24", "18:00", "18:00", "Scotland", "Brazil", "Hard Rock Stadium", "Miami", "USA"),
    (50, "C", 3, "2026-06-24", "18:00", "18:00", "Morocco", "Haiti", "Mercedes-Benz Stadium", "Atlanta", "USA"),
    (51, "B", 3, "2026-06-24", "15:00", "12:00", "Switzerland", "Canada", "BC Place", "Vancouver", "Canada"),
    (52, "B", 3, "2026-06-24", "15:00", "12:00", "Bosnia and Herzegovina", "Qatar", "Lumen Field", "Seattle", "USA"),
    (53, "A", 3, "2026-06-24", "21:00", "19:00", "Czechia", "Mexico", "Estadio Azteca", "Mexico City", "Mexico"),
    (54, "A", 3, "2026-06-24", "21:00", "19:00", "South Africa", "South Korea", "Estadio BBVA", "Monterrey", "Mexico"),
    (55, "E", 3, "2026-06-25", "16:00", "16:00", "Curacao", "Ivory Coast", "Lincoln Financial Field", "Philadelphia", "USA"),
    (56, "E", 3, "2026-06-25", "16:00", "16:00", "Ecuador", "Germany", "MetLife Stadium", "New York/New Jersey", "USA"),
    (57, "F", 3, "2026-06-25", "19:00", "18:00", "Japan", "Sweden", "AT&T Stadium", "Dallas", "USA"),
    (58, "F", 3, "2026-06-25", "19:00", "18:00", "Tunisia", "Netherlands", "Arrowhead Stadium", "Kansas City", "USA"),
    (59, "D", 3, "2026-06-25", "22:00", "19:00", "Turkey", "USA", "SoFi Stadium", "Los Angeles", "USA"),
    (60, "D", 3, "2026-06-25", "22:00", "19:00", "Paraguay", "Australia", "Levi's Stadium", "San Francisco Bay Area", "USA"),
    (61, "I", 3, "2026-06-26", "15:00", "15:00", "Norway", "France", "Gillette Stadium", "Boston", "USA"),
    (62, "I", 3, "2026-06-26", "15:00", "15:00", "Senegal", "Iraq", "BMO Field", "Toronto", "Canada"),
    (63, "G", 3, "2026-06-26", "23:00", "20:00", "Egypt", "Iran", "Lumen Field", "Seattle", "USA"),
    (64, "G", 3, "2026-06-26", "23:00", "20:00", "New Zealand", "Belgium", "BC Place", "Vancouver", "Canada"),
    (65, "H", 3, "2026-06-26", "20:00", "19:00", "Cape Verde", "Saudi Arabia", "NRG Stadium", "Houston", "USA"),
    (66, "H", 3, "2026-06-26", "20:00", "18:00", "Uruguay", "Spain", "Estadio Akron", "Guadalajara", "Mexico"),
    (67, "L", 3, "2026-06-27", "17:00", "17:00", "Panama", "England", "MetLife Stadium", "New York/New Jersey", "USA"),
    (68, "L", 3, "2026-06-27", "17:00", "17:00", "Croatia", "Ghana", "Lincoln Financial Field", "Philadelphia", "USA"),
    (69, "J", 3, "2026-06-27", "22:00", "21:00", "Algeria", "Austria", "Arrowhead Stadium", "Kansas City", "USA"),
    (70, "J", 3, "2026-06-27", "22:00", "21:00", "Jordan", "Argentina", "AT&T Stadium", "Dallas", "USA"),
    (71, "K", 3, "2026-06-27", "19:30", "19:30", "Colombia", "Portugal", "Hard Rock Stadium", "Miami", "USA"),
    (72, "K", 3, "2026-06-27", "19:30", "19:30", "DR Congo", "Uzbekistan", "Mercedes-Benz Stadium", "Atlanta", "USA"),
]

# R1 calendar dates verified by FotMob/Opta in wc2026_match_xg.csv (UTC+8 file dates).
R1_DATE_OVERRIDE = {
    ("A", "South Korea", "Czechia"): "2026-06-12",
    ("B", "Canada", "Bosnia and Herzegovina"): "2026-06-13",
    ("D", "USA", "Paraguay"): "2026-06-13",
    ("B", "Qatar", "Switzerland"): "2026-06-14",
    ("C", "Brazil", "Morocco"): "2026-06-14",
    ("C", "Haiti", "Scotland"): "2026-06-14",
    ("D", "Australia", "Turkey"): "2026-06-14",
    ("E", "Germany", "Curacao"): "2026-06-15",
    ("F", "Netherlands", "Japan"): "2026-06-15",
    ("E", "Ivory Coast", "Ecuador"): "2026-06-15",
    ("F", "Sweden", "Tunisia"): "2026-06-15",
    ("H", "Spain", "Cape Verde"): "2026-06-16",
    ("G", "Belgium", "Egypt"): "2026-06-16",
    ("H", "Saudi Arabia", "Uruguay"): "2026-06-16",
    ("G", "Iran", "New Zealand"): "2026-06-16",
    ("I", "France", "Senegal"): "2026-06-16",
    ("I", "Iraq", "Norway"): "2026-06-16",
    ("J", "Argentina", "Algeria"): "2026-06-17",
    ("J", "Austria", "Jordan"): "2026-06-17",
    ("K", "Portugal", "DR Congo"): "2026-06-18",
    ("K", "Uzbekistan", "Colombia"): "2026-06-18",
    ("L", "England", "Croatia"): "2026-06-18",
    ("L", "Ghana", "Panama"): "2026-06-18",
}

FIELDS = [
    "fifa_match_id", "group", "round", "match_date", "kickoff_et", "kickoff_local",
    "home_team_en", "away_team_en", "home_team_zh", "away_team_zh",
    "venue", "city", "host_country", "status", "source", "source_url", "last_verified",
]

SOURCE_URL = "https://www.roadtrips.com/world-cup/2026-world-cup-packages/schedule/"


def load_zh() -> dict[str, str]:
    zh: dict[str, str] = {}
    with ASSIGN.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            zh[row["team_en"]] = row["team_zh"]
    return zh


def load_finished() -> set[tuple[str, str, str]]:
    """Group + unordered team pair (FIFA sheet home/away may differ from match-centre)."""
    done: set[tuple[str, str, str]] = set()
    with MATCH_XG.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            a, b = row["home_team"], row["away_team"]
            if a > b:
                a, b = b, a
            done.add((row["group"], a, b))
    return done


def main() -> None:
    zh = load_zh()
    finished = load_finished()
    rows: list[dict] = []

    for fx in FIXTURES:
        fid, group, rnd, date, et, local, home, away, venue, city, country = fx
        if rnd == 1:
            date = R1_DATE_OVERRIDE.get((group, home, away), date)
        a, b = home, away
        if a > b:
            a, b = b, a
        status = "finished" if (group, a, b) in finished else "scheduled"
        rows.append({
            "fifa_match_id": fid,
            "group": group,
            "round": rnd,
            "match_date": date,
            "kickoff_et": et,
            "kickoff_local": local,
            "home_team_en": home,
            "away_team_en": away,
            "home_team_zh": zh.get(home, ""),
            "away_team_zh": zh.get(away, ""),
            "venue": venue,
            "city": city,
            "host_country": country,
            "status": status,
            "source": SOURCE,
            "source_url": SOURCE_URL,
            "last_verified": LAST_VERIFIED,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    n_fin = sum(1 for r in rows if r["status"] == "finished")
    print(f"Wrote {len(rows)} fixtures to {OUT} ({n_fin} finished, {len(rows) - n_fin} scheduled)")


if __name__ == "__main__":
    main()
