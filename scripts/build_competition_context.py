#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build structured competition context per match (EventFlow V3.4)."""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from competition_state_engine import (
    controlled_win_incentive,
    evaluate_match_state,
    must_win_pressure,
    top_spot_incentive,
)
from group_state_common import kickoff_utc_from_mapping_row

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "database" / "competition"
MATCH_XG = ROOT / "database" / "xGdatabase" / "processed" / "wc2026_match_xg.csv"
OUT = COMP / "competition_context.csv"
SCHEMA_OUT = COMP / "competition_context_schema.csv"

HOST_NATIONS = {"USA", "Mexico", "Canada"}

FIELDS = [
    "match_id", "group", "round", "home", "away",
    "home_points", "away_points", "home_rank", "away_rank",
    "home_goal_difference", "away_goal_difference",
    "home_draw_acceptance", "away_draw_acceptance", "mutual_draw_acceptance",
    "home_must_win_pressure", "away_must_win_pressure",
    "home_top_spot_incentive", "away_top_spot_incentive",
    "home_controlled_win_incentive", "away_controlled_win_incentive",
    "home_path_state", "away_path_state",
    "home_state_reason_code", "away_state_reason_code",
    "late_draw_control_index", "late_chase_suppression",
    "first_place_slot", "second_place_slot", "third_place_candidate_slots",
    "bracket_path_known", "context_quality", "context_reason", "last_updated",
]

SCHEMA_ROWS = [
    ("match_id", "string", "Internal match ID, e.g. WC2026-D32"),
    ("group", "string", "Group letter"),
    ("round", "int", "Group stage round 1/2/3"),
    ("home", "string", "Home team English name"),
    ("away", "string", "Away team English name"),
    ("home_points", "int", "Pre-match points"),
    ("away_points", "int", "Pre-match points"),
    ("home_rank", "int", "Pre-match group rank"),
    ("away_rank", "int", "Pre-match group rank"),
    ("home_goal_difference", "int", "Pre-match goal difference"),
    ("away_goal_difference", "int", "Pre-match goal difference"),
    ("home_draw_acceptance", "float", "Home draw acceptance 0-1"),
    ("away_draw_acceptance", "float", "Away draw acceptance 0-1"),
    ("mutual_draw_acceptance", "float", "Mutual draw acceptance 0-1"),
    ("home_must_win_pressure", "float", "Home must-win pressure 0-1"),
    ("away_must_win_pressure", "float", "Away must-win pressure 0-1"),
    ("home_top_spot_incentive", "float", "Home top-spot incentive 0-1"),
    ("away_top_spot_incentive", "float", "Away top-spot incentive 0-1"),
    ("home_controlled_win_incentive", "float", "Home controlled-win incentive 0-1"),
    ("away_controlled_win_incentive", "float", "Away controlled-win incentive 0-1"),
    ("home_path_state", "string", "Canonical home advancement state"),
    ("away_path_state", "string", "Canonical away advancement state"),
    ("home_state_reason_code", "string", "Canonical home state reason code"),
    ("away_state_reason_code", "string", "Canonical away state reason code"),
    ("late_draw_control_index", "float", "Late draw control if level after 60' 0-1"),
    ("late_chase_suppression", "float", "S07 late-chase suppression cap 0-1"),
    ("first_place_slot", "string", "Knockout slot for group winner, e.g. 1D"),
    ("second_place_slot", "string", "Knockout slot for runner-up, e.g. 2D"),
    ("third_place_candidate_slots", "string", "Possible R32 slots if third qualifies"),
    ("bracket_path_known", "bool", "Whether knockout path is reliably known from template"),
    ("context_quality", "string", "Structured data quality A/B/C"),
    ("context_reason", "string", "Short traceable explanation"),
    ("last_updated", "string", "ISO date of build"),
]


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def compute_draw_acceptance(points: int, opponent_points: int, round_no: int) -> float:
    if round_no < 2:
        return 0.0
    if round_no == 2:
        if points >= 3 and opponent_points >= 3:
            return 0.82
        if points >= 3 and opponent_points <= 1:
            return 0.38
        if points == 1:
            return 0.48
        if points == 0:
            return 0.10
    if round_no == 3:
        if points >= 4:
            return 0.76
        if points == 3:
            return 0.58
        if points <= 1:
            return 0.18
    return 0.22


def compute_must_win_pressure(points: int, gd: int, round_no: int) -> float:
    if round_no < 2:
        return 0.0
    if points == 0 and round_no == 2:
        return 0.90
    if points <= 1 and gd < -2 and round_no == 2:
        return 0.75
    if points <= 1 and round_no == 3:
        return 0.80
    return 0.0


def compute_top_spot_incentive(points: int, rank: int, gd: int, round_no: int, is_host: bool) -> float:
    if round_no < 2:
        return 0.0
    base = 0.0
    if rank <= 2 and points >= 3:
        base += 0.45
    if rank == 1:
        base += 0.15
    if gd >= 2:
        base += 0.08
    if is_host:
        base += 0.12
    return min(1.0, base)


def compute_controlled_win_incentive(top_spot: float, draw_acceptance: float, must_win: float) -> float:
    return max(0.0, min(1.0, top_spot * 0.70 + draw_acceptance * 0.20 - must_win * 0.35))


def compute_late_draw_control(mutual_draw: float, max_must_win: float) -> float:
    return max(0.0, min(1.0, mutual_draw * (1.0 - 0.55 * max_must_win)))


def compute_late_chase_suppression(late_draw_control: float) -> float:
    return min(0.55, late_draw_control * 0.45)


def init_team_stats(teams: List[str]) -> Dict[str, Dict[str, int]]:
    return {t: {"points": 0, "gf": 0, "ga": 0, "played": 0} for t in teams}


def apply_result(stats: Dict[str, Dict[str, int]], home: str, away: str, hs: int, as_: int) -> None:
    stats[home]["played"] += 1
    stats[away]["played"] += 1
    stats[home]["gf"] += hs
    stats[home]["ga"] += as_
    stats[away]["gf"] += as_
    stats[away]["ga"] += hs
    if hs > as_:
        stats[home]["points"] += 3
    elif hs == as_:
        stats[home]["points"] += 1
        stats[away]["points"] += 1
    else:
        stats[away]["points"] += 3


def rank_teams(stats: Dict[str, Dict[str, int]]) -> Dict[str, int]:
    ordered = sorted(
        stats.keys(),
        key=lambda t: (-stats[t]["points"], -(stats[t]["gf"] - stats[t]["ga"]), -stats[t]["gf"]),
    )
    return {team: i + 1 for i, team in enumerate(ordered)}


def load_group_teams() -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = defaultdict(list)
    for row in read_csv(COMP / "group_assignments.csv"):
        groups[row["group"]].append(row["team_en"])
    return dict(groups)


def load_completed_results() -> Dict[Tuple[str, str, str], Tuple[int, int]]:
    """Key: (group, home, away) -> (home_score, away_score)."""
    out: Dict[Tuple[str, str, str], Tuple[int, int]] = {}
    for row in read_csv(MATCH_XG):
        g = row.get("group", "")
        home = row.get("home_team", "")
        away = row.get("away_team", "")
        try:
            out[(g, home, away)] = (int(row["home_score"]), int(row["away_score"]))
        except (KeyError, ValueError):
            continue
    return out


def prematch_stats(
    group: str,
    round_no: int,
    group_teams: List[str],
    results: Dict[Tuple[str, str, str], Tuple[int, int]],
    fixtures: List[Dict[str, str]],
) -> Dict[str, Dict[str, int]]:
    stats = init_team_stats(group_teams)
    for fx in fixtures:
        if fx["group"] != group:
            continue
        fx_round = int(fx["round"])
        if fx_round >= round_no:
            continue
        home, away = fx["home_team_en"], fx["away_team_en"]
        score = results.get((group, home, away))
        if score:
            apply_result(stats, home, away, score[0], score[1])
    return stats


def third_place_candidates(group: str, template_rows: List[Dict[str, str]]) -> str:
    slots: List[str] = []
    for row in template_rows:
        candidates = row.get("third_place_candidate_groups", "")
        home_slot = row.get("home_slot", "")
        away_slot = row.get("away_slot", "")
        if group in [g.strip() for g in candidates.split(";") if g.strip()]:
            opp = away_slot if home_slot == "3rd" else (home_slot if away_slot == "3rd" else "")
            if opp:
                slots.append(f"3{group} candidate for {opp}")
    if not slots:
        return f"3{group} (third-place path TBD until qualifiers known)"
    return "; ".join(sorted(set(slots))[:4])


def build_context_reason(
    round_no: int,
    home: str,
    away: str,
    hp: int,
    ap: int,
    home_draw: float,
    away_draw: float,
    home_top: float,
) -> str:
    if round_no < 2:
        return "R1: no group-table strategic context."
    parts: List[str] = []
    if home_draw >= 0.75 and away_draw >= 0.75:
        parts.append(f"R{round_no} group leaders both on {hp}/{ap} pts; draw protects qualification margin")
    elif max(home_draw, away_draw) <= 0.20:
        parts.append(f"R{round_no} {home} vs {away}: low draw acceptance; must-win pressure dominant")
    elif hp == ap and hp >= 3:
        parts.append(f"R{round_no} tied on {hp} pts; draw still viable for both")
    else:
        parts.append(f"R{round_no} {home}({hp}pts) vs {away}({ap}pts)")
    if home_top > 0.45:
        parts.append("top spot path incentive exists")
    return "; ".join(parts) + "."


def context_quality_for(round_no: int, stats: Dict[str, Dict[str, int]], home: str, away: str) -> str:
    if round_no < 2:
        return "B"
    if stats[home]["played"] >= round_no - 1 and stats[away]["played"] >= round_no - 1:
        return "A"
    if stats[home]["played"] > 0 or stats[away]["played"] > 0:
        return "B"
    return "C"


def main() -> None:
    mappings = read_csv(COMP / "wc2026_match_id_mapping.csv")
    template_rows = read_csv(COMP / "round_of_32_template.csv")
    today = datetime.now(timezone.utc).date().isoformat()
    rows: List[Dict[str, str]] = []

    for m in mappings:
        mid = m["internal_match_id"]
        grp = m["group"]
        rnd = int(m["round"])
        home, away = m["home_team"], m["away_team"]
        kickoff = kickoff_utc_from_mapping_row(m)
        if kickoff is None:
            continue
        state = evaluate_match_state(home, away, grp, kickoff, round_num=rnd)
        hs, aws = state["home"], state["away"]
        hp, ap = int(hs["points"]), int(aws["points"])
        hgd, agd = int(hs["gd"]), int(aws["gd"])
        hr, ar = int(hs["current_rank"]), int(aws["current_rank"])
        # Preserve the EventFlow V3.4 calibration scale while sourcing the
        # state and reason codes exclusively from the canonical engine.
        home_draw = compute_draw_acceptance(hp, ap, rnd)
        away_draw = compute_draw_acceptance(ap, hp, rnd)
        mutual = min(home_draw, away_draw)
        home_mw = must_win_pressure(hs)
        away_mw = must_win_pressure(aws)
        home_top = min(1.0, top_spot_incentive(hs) + (0.12 if home in HOST_NATIONS else 0.0))
        away_top = min(1.0, top_spot_incentive(aws) + (0.12 if away in HOST_NATIONS else 0.0))
        home_cw = 0.0 if rnd < 2 else controlled_win_incentive({**hs, "p_finish_1": home_top})
        away_cw = 0.0 if rnd < 2 else controlled_win_incentive({**aws, "p_finish_1": away_top})
        late_draw = compute_late_draw_control(mutual, max(home_mw, away_mw))
        late_chase = compute_late_chase_suppression(late_draw)
        quality = "B" if rnd < 2 else ("A" if min(int(hs.get("remaining_matches", 0)), int(aws.get("remaining_matches", 0))) >= 1 else "B")
        reason = build_context_reason(rnd, home, away, hp, ap, home_draw, away_draw, home_top)

        rows.append({
            "match_id": mid,
            "group": grp,
            "round": str(rnd),
            "home": home,
            "away": away,
            "home_points": str(hp),
            "away_points": str(ap),
            "home_rank": str(hr),
            "away_rank": str(ar),
            "home_goal_difference": str(hgd),
            "away_goal_difference": str(agd),
            "home_draw_acceptance": f"{home_draw:.4f}",
            "away_draw_acceptance": f"{away_draw:.4f}",
            "mutual_draw_acceptance": f"{mutual:.4f}",
            "home_must_win_pressure": f"{home_mw:.4f}",
            "away_must_win_pressure": f"{away_mw:.4f}",
            "home_top_spot_incentive": f"{home_top:.4f}",
            "away_top_spot_incentive": f"{away_top:.4f}",
            "home_controlled_win_incentive": f"{home_cw:.4f}",
            "away_controlled_win_incentive": f"{away_cw:.4f}",
            "home_path_state": hs["path_state"],
            "away_path_state": aws["path_state"],
            "home_state_reason_code": hs["state_reason_code"],
            "away_state_reason_code": aws["state_reason_code"],
            "late_draw_control_index": f"{late_draw:.4f}",
            "late_chase_suppression": f"{late_chase:.4f}",
            "first_place_slot": f"1{grp}",
            "second_place_slot": f"2{grp}",
            "third_place_candidate_slots": third_place_candidates(grp, template_rows),
            "bracket_path_known": "true" if rnd >= 2 else "false",
            "context_quality": quality,
            "context_reason": reason,
            "last_updated": today,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    with SCHEMA_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["field", "type", "description"])
        w.writerows(SCHEMA_ROWS)

    print(f"Wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
