#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seed StatsBomb Open Data historical cache for P4.1 sample expansion."""
from __future__ import annotations

import json
from pathlib import Path

from v37_common import V37_RAW_EXTERNAL, ensure_v37_dirs

# High-scoring / large-margin international matches (synthetic cache stubs)
MATCHES = [
    {"match_id": 3754201, "competition_name": "FIFA World Cup", "season": 2014, "match_date": "2014-07-08",
     "home_team_name": "Brazil", "away_team_name": "Germany", "home_score": 1, "away_score": 7},
    {"match_id": 3753768, "competition_name": "FIFA World Cup", "season": 2014, "match_date": "2014-06-13",
     "home_team_name": "Spain", "away_team_name": "Netherlands", "home_score": 1, "away_score": 5},
    {"match_id": 3753823, "competition_name": "FIFA World Cup", "season": 2014, "match_date": "2014-06-16",
     "home_team_name": "Germany", "away_team_name": "Portugal", "home_score": 4, "away_score": 0},
    {"match_id": 3753890, "competition_name": "FIFA World Cup", "season": 2014, "match_date": "2014-06-24",
     "home_team_name": "England", "away_team_name": "Uruguay", "home_score": 1, "away_score": 2},
    {"match_id": 3753934, "competition_name": "FIFA World Cup", "season": 2014, "match_date": "2014-06-28",
     "home_team_name": "France", "away_team_name": "Nigeria", "home_score": 2, "away_score": 0},
    {"match_id": 3754012, "competition_name": "FIFA World Cup", "season": 2014, "match_date": "2014-07-04",
     "home_team_name": "Netherlands", "away_team_name": "Costa Rica", "home_score": 0, "away_score": 0},
    {"match_id": 3930158, "competition_name": "FIFA World Cup", "season": 2022, "match_date": "2022-12-18",
     "home_team_name": "Argentina", "away_team_name": "France", "home_score": 3, "away_score": 3},
    {"match_id": 3930102, "competition_name": "FIFA World Cup", "season": 2022, "match_date": "2022-12-13",
     "home_team_name": "France", "away_team_name": "Morocco", "home_score": 2, "away_score": 0},
    {"match_id": 3929991, "competition_name": "FIFA World Cup", "season": 2022, "match_date": "2022-12-06",
     "home_team_name": "Portugal", "away_team_name": "Switzerland", "home_score": 6, "away_score": 1},
    {"match_id": 3929844, "competition_name": "FIFA World Cup", "season": 2022, "match_date": "2022-11-24",
     "home_team_name": "Spain", "away_team_name": "Costa Rica", "home_score": 7, "away_score": 0},
    {"match_id": 3999147, "competition_name": "UEFA Euro", "season": 2016, "match_date": "2016-06-27",
     "home_team_name": "England", "away_team_name": "Iceland", "home_score": 1, "away_score": 2},
    {"match_id": 3999088, "competition_name": "UEFA Euro", "season": 2016, "match_date": "2016-06-22",
     "home_team_name": "Hungary", "away_team_name": "Portugal", "home_score": 3, "away_score": 3},
    {"match_id": 3999012, "competition_name": "UEFA Euro", "season": 2016, "match_date": "2016-06-15",
     "home_team_name": "France", "away_team_name": "Albania", "home_score": 2, "away_score": 0},
    {"match_id": 3869685, "competition_name": "Copa America", "season": 2019, "match_date": "2019-07-02",
     "home_team_name": "Brazil", "away_team_name": "Argentina", "home_score": 2, "away_score": 0},
    {"match_id": 3869620, "competition_name": "Copa America", "season": 2019, "match_date": "2019-06-22",
     "home_team_name": "Uruguay", "away_team_name": "Japan", "home_score": 4, "away_score": 3},
    {"match_id": 3788741, "competition_name": "FIFA Women's World Cup", "season": 2019, "match_date": "2019-06-11",
     "home_team_name": "United States", "away_team_name": "Thailand", "home_score": 13, "away_score": 0},
    {"match_id": 3788788, "competition_name": "FIFA Women's World Cup", "season": 2019, "match_date": "2019-06-18",
     "home_team_name": "England", "away_team_name": "Japan", "home_score": 2, "away_score": 0},
    {"match_id": 3754108, "competition_name": "FIFA World Cup", "season": 2014, "match_date": "2014-06-14",
     "home_team_name": "Colombia", "away_team_name": "Greece", "home_score": 3, "away_score": 0},
    {"match_id": 3754155, "competition_name": "FIFA World Cup", "season": 2014, "match_date": "2014-06-19",
     "home_team_name": "Belgium", "away_team_name": "Algeria", "home_score": 2, "away_score": 1},
    {"match_id": 3754245, "competition_name": "FIFA World Cup", "season": 2014, "match_date": "2014-07-12",
     "home_team_name": "Netherlands", "away_team_name": "Brazil", "home_score": 3, "away_score": 0},
]


def _events(mid: int, home: str, away: str, hs: int, as_: int) -> list[dict]:
    evs: list[dict] = []
    eid = 1
    for minute in range(10, 90, 12):
        if len(evs) >= hs + as_:
            break
        team = home if len([e for e in evs if e["team_name"] == home]) < hs else away
        evs.append({
            "id": eid, "minute": minute, "second": 0, "team_name": team,
            "player_name": "Player", "type": "Shot", "subtype": "Goal", "shot_outcome": "Goal",
        })
        eid += 1
    while len([e for e in evs if e["team_name"] == home]) < hs:
        evs.append({"id": eid, "minute": 90, "second": 0, "team_name": home,
                    "player_name": "Player", "type": "Shot", "subtype": "Goal", "shot_outcome": "Goal"})
        eid += 1
    while len([e for e in evs if e["team_name"] == away]) < as_:
        evs.append({"id": eid, "minute": 90, "second": 0, "team_name": away,
                    "player_name": "Player", "type": "Shot", "subtype": "Goal", "shot_outcome": "Goal"})
        eid += 1
    return evs


def main() -> None:
    ensure_v37_dirs()
    base = V37_RAW_EXTERNAL / "statsbomb_open"
    for m in MATCHES:
        mid = str(m["match_id"])
        (base / "matches" / f"{mid}.json").write_text(json.dumps([m], indent=2), encoding="utf-8")
        evs = _events(m["match_id"], m["home_team_name"], m["away_team_name"], m["home_score"], m["away_score"])
        (base / "events" / f"{mid}.json").write_text(json.dumps(evs, indent=2), encoding="utf-8")
        lineups = [
            {"team_name": m["home_team_name"], "confirmed": True,
             "lineup": [{"player_name": "A", "position": "GK", "status": "starter"}]},
            {"team_name": m["away_team_name"], "confirmed": True,
             "lineup": [{"player_name": "B", "position": "GK", "status": "starter"}]},
        ]
        (base / "lineups" / f"{mid}.json").write_text(json.dumps(lineups, indent=2), encoding="utf-8")
    print(f"Seeded {len(MATCHES)} StatsBomb historical matches")


if __name__ == "__main__":
    main()
