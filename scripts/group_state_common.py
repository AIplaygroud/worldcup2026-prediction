#!/usr/bin/env python3
"""Shared helpers for Phase 06 group state / advancement path / bracket route."""
from __future__ import annotations

import copy
import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[misc, assignment]

# June 2026: US/Canada daylight, Mexico no DST (standard -6).
CITY_UTC_OFFSET_HOURS: dict[str, int] = {
    "Atlanta": -4,
    "Boston": -4,
    "Miami": -4,
    "Philadelphia": -4,
    "New York/New Jersey": -4,
    "Kansas City": -5,
    "Dallas": -5,
    "Houston": -5,
    "Los Angeles": -7,
    "Seattle": -7,
    "San Francisco Bay Area": -7,
    "Mexico City": -6,
    "Guadalajara": -6,
    "Monterrey": -6,
    "Toronto": -4,
    "Vancouver": -7,
}

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database"
MATCH_XG = DB / "xGdatabase" / "processed" / "wc2026_match_xg.csv"
ASSIGN = DB / "competition" / "group_assignments.csv"
FAIR_PLAY = DB / "competition" / "wc2026_fair_play_r1.csv"
FIXTURES = DB / "competition" / "wc2026_group_fixtures.csv"
MAPPING = DB / "competition" / "wc2026_match_id_mapping.csv"
FAVORITE_TIERS = DB / "competition" / "static" / "team_favorite_tiers.csv"
TEAM_PROFILE = DB / "team_style" / "processed" / "team_tactical_profile.csv"

FIFA_RANK = {
    "Belgium": 9, "France": 2, "England": 4, "Brazil": 5, "Argentina": 1,
    "Portugal": 6, "Netherlands": 7, "Spain": 8, "Italy": 10, "Croatia": 11,
    "Morocco": 12, "Colombia": 13, "Mexico": 14, "USA": 15, "Uruguay": 16,
    "Switzerland": 17, "Japan": 18, "Senegal": 19, "Iran": 20, "South Korea": 21,
    "Ecuador": 22, "Austria": 23, "Australia": 24, "Norway": 25, "Panama": 26,
    "Egypt": 29, "Canada": 30, "Scotland": 31, "Paraguay": 32, "Tunisia": 33,
    "Algeria": 34, "Czechia": 35, "Turkey": 36, "Sweden": 37,
    "Bosnia and Herzegovina": 50, "Qatar": 56, "Saudi Arabia": 57, "Iraq": 58,
    "Jordan": 59, "Uzbekistan": 60, "South Africa": 61, "Ghana": 62,
    "DR Congo": 63, "Ivory Coast": 64, "New Zealand": 67, "Haiti": 68,
    "Curacao": 69, "Cape Verde": 70, "Germany": 3,
}

TIER_SCORE = {
    "elite_contender": 1.00,
    "major_contender": 0.85,
    "strong_seed": 0.70,
    "solid_knockout": 0.55,
    "outsider": 0.35,
    "longshot": 0.20,
}

CITY_TZ: dict[str, str] = {
    "Atlanta": "America/New_York",
    "Boston": "America/New_York",
    "Miami": "America/New_York",
    "Philadelphia": "America/New_York",
    "New York/New Jersey": "America/New_York",
    "Kansas City": "America/Chicago",
    "Dallas": "America/Chicago",
    "Houston": "America/Chicago",
    "Los Angeles": "America/Los_Angeles",
    "Seattle": "America/Los_Angeles",
    "San Francisco Bay Area": "America/Los_Angeles",
    "Mexico City": "America/Mexico_City",
    "Guadalajara": "America/Mexico_City",
    "Monterrey": "America/Monterrey",
    "Toronto": "America/Toronto",
    "Vancouver": "America/Vancouver",
}

R32_OPPONENT_SLOT = {
    "1A": ("3rd", ["C", "E", "F", "H", "I"]),
    "1B": ("3rd", ["E", "F", "G", "I", "J"]),
    "1C": ("2F", []),
    "1D": ("3rd", ["B", "E", "F", "I", "J"]),
    "1E": ("3rd", ["A", "B", "C", "D", "F"]),
    "1F": ("2C", []),
    "1G": ("3rd", ["A", "E", "H", "I", "J"]),
    "1H": ("2J", []),
    "1I": ("3rd", ["C", "D", "F", "G", "H"]),
    "1J": ("2H", []),
    "1K": ("3rd", ["D", "E", "I", "J", "L"]),
    "1L": ("3rd", ["E", "H", "I", "J", "K"]),
    "2A": ("2B", []),
    "2B": ("2A", []),
    "2C": ("1F", []),
    "2D": ("2G", []),
    "2E": ("2I", []),
    "2F": ("1C", []),
    "2G": ("2D", []),
    "2H": ("1J", []),
    "2I": ("2E", []),
    "2J": ("1H", []),
    "2K": ("2L", []),
    "2L": ("2K", []),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def parse_cutoff(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _local_to_utc_with_offset(naive: datetime, offset_hours: int) -> datetime:
    """Local wall time -> UTC using fixed offset (west of UTC: offset is negative)."""
    return (naive - timedelta(hours=offset_hours)).replace(tzinfo=timezone.utc)


def local_kickoff_to_utc(date_s: str, time_s: str, city: str) -> datetime:
    """Convert stadium-local kickoff to UTC. kickoff_local / kickoff_et are display-only."""
    city = city.strip()
    hour, minute = (int(x) for x in time_s.strip().split(":"))
    day = datetime.strptime(date_s.strip(), "%Y-%m-%d").date()
    if hour == 24:
        day = day + timedelta(days=1)
        hour = 0
    naive = datetime(day.year, day.month, day.day, hour, minute)
    if ZoneInfo is not None:
        tz_name = CITY_TZ.get(city, "America/New_York")
        try:
            local = naive.replace(tzinfo=ZoneInfo(tz_name))
            return local.astimezone(timezone.utc)
        except Exception:
            pass
    offset = CITY_UTC_OFFSET_HOURS.get(city, -4)
    return _local_to_utc_with_offset(naive, offset)


def kickoff_utc_from_fixture_row(row: dict[str, str]) -> datetime | None:
    date_s = row.get("match_date", "").strip()
    kick = row.get("kickoff_local", "").strip()
    city = row.get("city", "").strip()
    if not date_s or not kick:
        return None
    try:
        return local_kickoff_to_utc(date_s, kick, city)
    except (ValueError, KeyError):
        return None


def kickoff_utc_from_mapping_row(row: dict[str, str]) -> datetime | None:
    raw = row.get("kickoff_utc", "").strip()
    if raw:
        return parse_cutoff(raw if "T" in raw else raw.replace(" ", "T") + "Z")
    fid = row.get("fifa_match_id", "").strip()
    if fid:
        for fix in read_csv(FIXTURES):
            if fix.get("fifa_match_id") == fid:
                return kickoff_utc_from_fixture_row(fix)
    kt = row.get("kickoff_time", "").strip()
    if not kt:
        return None
    try:
        date_s, time_s = kt.split(" ", 1)
        return local_kickoff_to_utc(date_s, time_s, "Atlanta")
    except ValueError:
        return None


def pre_kickoff_cutoff(kickoff: datetime, epsilon_seconds: int = 60) -> datetime:
    return kickoff.astimezone(timezone.utc) - timedelta(seconds=epsilon_seconds)


def kickoff_utc(fifa_id: str, mapping_rows: list[dict[str, str]]) -> datetime | None:
    for row in mapping_rows:
        if row.get("fifa_match_id") == str(fifa_id):
            return kickoff_utc_from_mapping_row(row)
    return None


def load_fixture_kickoffs() -> dict[str, datetime]:
    """fifa_match_id -> UTC kickoff derived from stadium-local time + city timezone."""
    out: dict[str, datetime] = {}
    for row in read_csv(FIXTURES):
        fid = row.get("fifa_match_id", "").strip()
        ko = kickoff_utc_from_fixture_row(row)
        if fid and ko is not None:
            out[fid] = ko
    return out


def load_mapping_by_fifa() -> dict[str, dict[str, str]]:
    rows = read_csv(MAPPING)
    return {r["fifa_match_id"]: r for r in rows}


def load_groups() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for row in read_csv(ASSIGN):
        groups[row["group"]].append(row["team_en"])
    return dict(groups)


def load_fair_play() -> dict[str, int]:
    fp: dict[str, int] = defaultdict(int)
    for row in read_csv(FAIR_PLAY):
        try:
            fp[row["team_en"]] += int(row["fair_play_points"])
        except (KeyError, ValueError):
            pass
    return dict(fp)


def init_stats(team: str) -> dict[str, Any]:
    return {
        "team": team,
        "played": 0, "wins": 0, "draws": 0, "losses": 0,
        "gf": 0, "ga": 0, "points": 0,
        "h2h": defaultdict(lambda: {"pts": 0, "gd": 0, "gf": 0}),
    }


def apply_result(stats: dict[str, Any], gf: int, ga: int, opp: str) -> None:
    stats["played"] += 1
    stats["gf"] += gf
    stats["ga"] += ga
    h = stats["h2h"][opp]
    h["gf"] += gf
    h["gd"] += gf - ga
    if gf > ga:
        stats["wins"] += 1
        stats["points"] += 3
        h["pts"] += 3
    elif gf == ga:
        stats["draws"] += 1
        stats["points"] += 1
        h["pts"] += 1
    else:
        stats["losses"] += 1


def gd(stats: dict[str, Any]) -> int:
    return stats["gf"] - stats["ga"]


def h2h_key(stats: dict[str, Any], tied: list[str]) -> tuple:
    pts = gd_ = gf_ = 0
    for opp in tied:
        if opp == stats["team"]:
            continue
        h = stats["h2h"].get(opp)
        if h:
            pts += h["pts"]
            gd_ += h["gd"]
            gf_ += h["gf"]
    return (-pts, -gd_, -gf_)


def rank_group(
    teams: list[str],
    group_stats: dict[str, dict[str, Any]],
    fair_play: dict[str, int],
) -> list[tuple[str, dict[str, Any], int]]:
    ordered = sorted(
        teams,
        key=lambda t: (
            -group_stats[t]["points"],
            -gd(group_stats[t]),
            -group_stats[t]["gf"],
        ),
    )
    result: list[tuple[str, dict[str, Any], int]] = []
    i = 0
    while i < len(ordered):
        j = i
        base = group_stats[ordered[i]]
        while j < len(ordered):
            s = group_stats[ordered[j]]
            if (s["points"], gd(s), s["gf"]) != (base["points"], gd(base), base["gf"]):
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
        for rank, t in enumerate(block, start=len(result) + 1):
            result.append((t, group_stats[t], rank))
        i = j
    return result


def load_completed_matches(cutoff: datetime) -> tuple[list[dict[str, str]], int]:
    """Return xG rows with kickoff strictly before cutoff."""
    kickoffs = load_fixture_kickoffs()
    xg_rows = read_csv(MATCH_XG)
    used: list[dict[str, str]] = []
    skipped_future = 0
    for row in xg_rows:
        date_s = row.get("match_date", "")
        matched_ko = None
        for fid, ko in kickoffs.items():
            # Team pairing is the stable key. UTC dates can differ from the
            # local fixture/xG date for evening kickoffs.
            if _teams_match_row(row, fid):
                matched_ko = ko
                break
        if matched_ko is None:
            try:
                matched_ko = datetime.strptime(date_s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        if matched_ko >= cutoff:
            skipped_future += 1
            continue
        used.append(row)
    return used, skipped_future


def _teams_match_row(row: dict[str, str], fifa_id: str) -> bool:
    fix_rows = [r for r in read_csv(FIXTURES) if r.get("fifa_match_id") == fifa_id]
    if not fix_rows:
        return False
    f = fix_rows[0]
    return (
        row.get("home_team") == f.get("home_team_en")
        and row.get("away_team") == f.get("away_team_en")
    )


def build_standings(
    cutoff: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    groups = load_groups()
    fair_play = load_fair_play()
    matches, _ = load_completed_matches(cutoff)

    group_stats: dict[str, dict[str, dict[str, Any]]] = {
        g: {t: init_stats(t) for t in teams} for g, teams in groups.items()
    }

    result_rows_used = 0
    for m in matches:
        g = m["group"]
        home, away = m["home_team"], m["away_team"]
        hs, as_ = int(m["home_score"]), int(m["away_score"])
        if home in group_stats.get(g, {}) and away in group_stats.get(g, {}):
            apply_result(group_stats[g][home], hs, as_, away)
            apply_result(group_stats[g][away], as_, hs, home)
            result_rows_used += 1

    standings_rows: list[dict[str, Any]] = []
    ranked_by_group: dict[str, list[tuple[str, dict[str, Any], int]]] = {}
    for g in sorted(groups):
        ranked = rank_group(groups[g], group_stats[g], fair_play)
        ranked_by_group[g] = ranked
        for team, stats, rank in ranked:
            standings_rows.append({
                "group": g,
                "rank": rank,
                "team": team,
                "played": stats["played"],
                "wins": stats["wins"],
                "draws": stats["draws"],
                "losses": stats["losses"],
                "gf": stats["gf"],
                "ga": stats["ga"],
                "gd": gd(stats),
                "points": stats["points"],
            })

    third_rows: list[dict[str, Any]] = []
    third_candidates: list[dict[str, Any]] = []
    for g, ranked in ranked_by_group.items():
        for team, stats, rank in ranked:
            if rank == 3:
                third_candidates.append({
                    "group": g,
                    "team": team,
                    "points": stats["points"],
                    "gd": gd(stats),
                    "gf": stats["gf"],
                    "conduct_score": fair_play.get(team, 0),
                    "fifa_rank": FIFA_RANK.get(team, 999),
                })
    third_candidates.sort(
        key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["conduct_score"], r["fifa_rank"])
    )
    for i, r in enumerate(third_candidates, start=1):
        status = "strong_position" if i <= 4 else ("bubble" if i <= 10 else "weak_position")
        third_rows.append({**r, "rank_3rd": i, "third_place_status": status})

    meta = {"result_rows_used": result_rows_used, "ranked_by_group": ranked_by_group}
    return standings_rows, third_rows, meta


def remaining_group_matches(cutoff: datetime) -> dict[str, list[dict[str, str]]]:
    kickoffs = load_fixture_kickoffs()
    mapping = load_mapping_by_fifa()
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    for fid, ko in kickoffs.items():
        if ko < cutoff:
            continue
        m = mapping.get(fid)
        if not m:
            continue
        out[m["group"]].append(m)
    return dict(out)


def enumerate_points_bounds(
    team: str,
    group: str,
    standings: list[dict[str, Any]],
    remaining: list[dict[str, str]],
) -> tuple[int, int]:
    """Min/max points team can still achieve (3 per remaining match played)."""
    row = next(r for r in standings if r["team"] == team and r["group"] == group)
    rem = sum(
        1 for m in remaining
        if m["home_team"] == team or m["away_team"] == team
    )
    pts = row["points"]
    return pts, pts + 3 * rem


def _build_group_stats_from_matches(
    groups: dict[str, list[str]],
    matches: list[dict[str, str]],
) -> dict[str, dict[str, dict[str, Any]]]:
    group_stats: dict[str, dict[str, dict[str, Any]]] = {
        g: {t: init_stats(t) for t in teams} for g, teams in groups.items()
    }
    for m in matches:
        g = m["group"]
        home, away = m["home_team"], m["away_team"]
        hs, as_ = int(m["home_score"]), int(m["away_score"])
        if home in group_stats.get(g, {}) and away in group_stats.get(g, {}):
            apply_result(group_stats[g][home], hs, as_, away)
            apply_result(group_stats[g][away], as_, hs, home)
    return group_stats


def _remaining_fixture_pairs(
    group: str,
    remaining: list[dict[str, str]],
) -> list[tuple[str, str]]:
    return [
        (m["home_team"], m["away_team"])
        for m in remaining
        if m.get("group") == group
    ]


def enumerate_finish_rank_counts(
    teams: list[str],
    group_stats: dict[str, dict[str, Any]],
    remaining_pairs: list[tuple[str, str]],
    fair_play: dict[str, int],
) -> tuple[dict[str, dict[int, int]], int]:
    """Return per-team finish-rank counts across all remaining-result scenarios."""
    rank_counts: dict[str, dict[int, int]] = {t: {1: 0, 2: 0, 3: 0, 4: 0} for t in teams}
    if not remaining_pairs:
        ranked = rank_group(teams, group_stats, fair_play)
        for team, _, rank in ranked:
            rank_counts[team][rank] = 1
        return rank_counts, 1

    outcomes = [(1, 0), (1, 1), (0, 1)]
    total = 0
    for combo in product(outcomes, repeat=len(remaining_pairs)):
        stats = copy.deepcopy(group_stats)
        for (home, away), (hg, ag) in zip(remaining_pairs, combo):
            apply_result(stats[home], hg, ag, away)
            apply_result(stats[away], ag, hg, home)
        ranked = rank_group(teams, stats, fair_play)
        total += 1
        for team, _, rank in ranked:
            rank_counts[team][rank] += 1
    return rank_counts, total


def scenario_probabilities(
    team: str,
    rank_counts: dict[int, int],
    total: int,
) -> dict[str, float]:
    if total <= 0:
        return {
            "p_finish_1": 0.25, "p_finish_2": 0.25, "p_finish_3": 0.25, "p_finish_4": 0.25,
            "p_top2": 0.5, "p_advance": 0.5,
        }
    p1 = rank_counts.get(1, 0) / total
    p2 = rank_counts.get(2, 0) / total
    p3 = rank_counts.get(3, 0) / total
    p4 = rank_counts.get(4, 0) / total
    return {
        "p_finish_1": round(p1, 4),
        "p_finish_2": round(p2, 4),
        "p_finish_3": round(p3, 4),
        "p_finish_4": round(p4, 4),
        "p_top2": round(p1 + p2, 4),
        "p_advance": round(p1 + p2 + p3, 4),
    }


def build_group_stats_at_cutoff(
    cutoff: datetime,
) -> dict[str, dict[str, dict[str, Any]]]:
    groups = load_groups()
    matches, _ = load_completed_matches(cutoff)
    return _build_group_stats_from_matches(groups, matches)


def classify_path_state(
    team: str,
    group: str,
    rank: int,
    standings: list[dict[str, Any]],
    remaining: list[dict[str, str]],
    *,
    round_num: int = 0,
    cutoff: datetime | None = None,
    group_stats: dict[str, dict[str, Any]] | None = None,
    fair_play: dict[str, int] | None = None,
    teams_in_group: list[str] | None = None,
) -> dict[str, Any]:
    row = next(r for r in standings if r["team"] == team and r["group"] == group)
    pts, gd_val, gf = row["points"], row["gd"], row["gf"]
    played = row["played"]
    rem = [m for m in remaining if m["home_team"] == team or m["away_team"] == team]
    min_pts, max_pts = enumerate_points_bounds(team, group, standings, remaining)

    if played == 0 or round_num == 1:
        return {
            "current_rank": rank,
            "points": pts,
            "gd": gd_val,
            "gf": gf,
            "remaining_matches": len(rem),
            "can_finish_top1": True,
            "can_finish_top2": True,
            "can_finish_top3": True,
            "can_be_eliminated": True,
            "clinched_top2": False,
            "clinched_any_path": False,
            "eliminated": False,
            "third_place_viability": "bubble",
            "path_state": "opening_round",
            "path_confidence": 0.55,
            "draw_acceptance": 0.30,
            "rotation_risk": 0.10,
            "goal_diff_chase": 0.0,
            "qualification_secure_prob": 0.25,
            "p_finish_1": 0.25,
            "p_finish_2": 0.25,
            "p_finish_3": 0.25,
            "p_finish_4": 0.25,
            "p_top2": 0.5,
            "p_advance": 0.5,
            "state_reason_code": "R1_OPENING_BASELINE",
            "state_reason_codes": "R1_OPENING_BASELINE",
        }

    fp = fair_play if fair_play is not None else load_fair_play()
    teams = teams_in_group or [r["team"] for r in standings if r["group"] == group]
    rem_pairs = _remaining_fixture_pairs(group, remaining)
    if group_stats is None:
        if cutoff is not None:
            all_stats = build_group_stats_at_cutoff(cutoff)
            group_stats = all_stats.get(group, {})
        else:
            groups_all = load_groups()
            group_stats = {t: init_stats(t) for t in teams}
            for st in standings:
                if st["group"] != group:
                    continue
                t = st["team"]
                group_stats[t]["played"] = st["played"]
                group_stats[t]["wins"] = st.get("wins", st.get("won", 0))
                group_stats[t]["draws"] = st.get("draws", st.get("drawn", 0))
                group_stats[t]["losses"] = st.get("losses", st.get("lost", 0))
                group_stats[t]["gf"] = st["gf"]
                group_stats[t]["ga"] = st["ga"]
                group_stats[t]["points"] = st["points"]

    rank_counts, total = enumerate_finish_rank_counts(
        teams, {t: group_stats[t] for t in teams if t in group_stats}, rem_pairs, fp,
    )
    probs = scenario_probabilities(team, rank_counts[team], total)
    rc = rank_counts[team]

    can_finish_top1 = rc.get(1, 0) > 0
    can_finish_top2 = (rc.get(1, 0) + rc.get(2, 0)) > 0
    can_finish_top3 = (rc.get(1, 0) + rc.get(2, 0) + rc.get(3, 0)) > 0
    clinched_top2 = total > 0 and (rc.get(3, 0) + rc.get(4, 0)) == 0
    eliminated = total > 0 and (rc.get(1, 0) + rc.get(2, 0) + rc.get(3, 0)) == 0
    can_be_eliminated = rc.get(4, 0) > 0

    group_rows = [r for r in standings if r["group"] == group]
    second_pts = sorted({r["points"] for r in group_rows}, reverse=True)
    second_best = second_pts[1] if len(second_pts) > 1 else 0

    if eliminated:
        path_state = "eliminated"
        reason = "ELIMINATED_ALL_SCENARIOS"
    elif clinched_top2 and pts >= 6:
        path_state = "clinched_top2"
        reason = "CLINCHED_TOP2_ENUM"
    elif clinched_top2:
        path_state = "near_clinched"
        reason = "CLINCHED_TOP2_ENUM"
    elif pts >= 6:
        path_state = "near_clinched"
        reason = "SIX_POINTS_NOT_CLINCHED"
    elif pts >= 4 and not clinched_top2:
        path_state = "top_slot_chase" if rank <= 2 else "control_destiny"
        reason = "FOUR_POINTS_NOT_CLINCHED"
    elif pts >= 4:
        path_state = "top_slot_chase" if rank <= 2 else "control_destiny"
        reason = "TOP_SLOT_CHASE"
    elif pts == 3:
        if rank == 2:
            path_state = "must_not_lose"
            reason = "R2_THREE_POINTS_DRAW_TO_FOUR"
        elif rank == 3:
            path_state = "third_place_bubble"
            reason = "R3_BEST_THIRD_GD_CHASE"
        else:
            path_state = "control_destiny"
            reason = "CONTROL_DESTINY"
    elif pts <= 1:
        path_state = "must_win_big" if pts == 0 and gd_val <= -3 else "must_win"
        reason = "R2_ZERO_POINTS_SURVIVAL" if pts == 0 else "MUST_WIN_SURVIVAL"
    else:
        path_state = "open_group" if played <= 1 else "control_destiny"
        reason = "OPEN_GROUP"

    if played == 1 and pts == 1 and len([r for r in group_rows if r["points"] == 1]) >= 3:
        path_state = "open_group"
        reason = "OPEN_GROUP_TIED_ON_ONE"

    third_viability = "bubble"
    if rank == 3:
        if pts >= 3 and gd_val >= 0:
            third_viability = "strong_position"
        elif pts <= 1 or gd_val <= -3:
            third_viability = "weak_position"

    draw_acceptance = 0.3
    rotation_risk = 0.1
    goal_diff_chase = 0.0
    if path_state in ("clinched_top2", "near_clinched"):
        draw_acceptance = 0.75
        rotation_risk = 0.55
        if clinched_top2 and probs["p_top2"] >= 0.99:
            reason = "QUALIFICATION_SECURE_ROUTE_OPT_ALLOWED"
    elif path_state == "top_slot_chase":
        draw_acceptance = 0.55
    elif path_state == "must_not_lose":
        draw_acceptance = 0.45
    elif path_state == "third_place_bubble":
        draw_acceptance = 0.25
        goal_diff_chase = 0.5 if gd_val < 0 else 0.25
    elif path_state in ("must_win", "must_win_big"):
        draw_acceptance = 0.1
        goal_diff_chase = 0.7 if path_state == "must_win_big" else 0.35

    qual_prob = probs["p_advance"] if not eliminated else 0.05
    if clinched_top2:
        qual_prob = max(qual_prob, 0.95)

    return {
        "current_rank": rank,
        "points": pts,
        "gd": gd_val,
        "gf": gf,
        "remaining_matches": len(rem),
        "can_finish_top1": can_finish_top1,
        "can_finish_top2": can_finish_top2,
        "can_finish_top3": can_finish_top3,
        "can_be_eliminated": can_be_eliminated,
        "clinched_top2": clinched_top2,
        "clinched_any_path": clinched_top2 or (rank == 3 and pts >= 3 and probs["p_advance"] >= 0.9),
        "eliminated": eliminated,
        "third_place_viability": third_viability,
        "path_state": path_state,
        "path_confidence": 0.82 if played >= 2 else 0.68,
        "draw_acceptance": round(draw_acceptance, 3),
        "rotation_risk": round(rotation_risk, 3),
        "goal_diff_chase": round(goal_diff_chase, 3),
        "qualification_secure_prob": round(qual_prob, 3),
        "p_finish_1": probs["p_finish_1"],
        "p_finish_2": probs["p_finish_2"],
        "p_finish_3": probs["p_finish_3"],
        "p_finish_4": probs["p_finish_4"],
        "p_top2": probs["p_top2"],
        "p_advance": probs["p_advance"],
        "state_reason_code": reason,
        "state_reason_codes": reason,
    }


def estimate_qualification_prob(
    pts: int,
    rank: int,
    gd_val: int,
    rem: int,
    clinched: bool,
    eliminated: bool,
) -> float:
    if eliminated:
        return 0.05
    if clinched or pts >= 6:
        return 0.95
    if pts == 4 and rem <= 1:
        return 0.82
    if pts == 3 and rank <= 2:
        return 0.62
    if pts == 3 and rank == 3:
        return 0.48
    if pts == 1 and rem >= 2:
        return 0.28
    if pts == 0:
        return 0.12
    return 0.45


def team_strength(team: str) -> float:
    tiers = {r["team"]: float(r["tier_score"]) for r in read_csv(FAVORITE_TIERS)}
    if team in tiers:
        return tiers[team]
    rank = FIFA_RANK.get(team, 80)
    return max(0.15, min(1.0, 1.0 - (rank - 1) / 100.0))


def slot_opponent_strength(slot: str, standings: list[dict[str, Any]]) -> tuple[float, str, str]:
    """Return (strength, opponent_label, uncertainty)."""
    if slot == "3rd":
        return 0.55, "best_third_placeholder", "high"
    if slot.startswith("2") or slot.startswith("1"):
        g = slot[1]
        pos = 1 if slot[0] == "1" else 2
        grp = [r for r in standings if r["group"] == g]
        if not grp:
            return 0.5, slot, "medium"
        row = next((r for r in grp if r["rank"] == pos), grp[0])
        return team_strength(row["team"]), row["team"], "low"
    return 0.5, slot, "medium"


def route_score_for_position(
    position_slot: str,
    standings: list[dict[str, Any]],
) -> tuple[float, str, str, float]:
    opp_type, third_groups = R32_OPPONENT_SLOT.get(position_slot, ("unknown", []))
    if opp_type == "3rd":
        strength = 0.58
        label = f"3rd_from_{'_'.join(third_groups)}"
        uncertainty = 0.35
    else:
        strength, label, unc = slot_opponent_strength(opp_type, standings)
        uncertainty = 0.15 if unc == "low" else 0.25
    score = 0.55 * strength + 0.25 * strength * 0.85 + 0.10 * strength * 0.7
    score += 0.05 * uncertainty
    if opp_type == "3rd":
        score += 0.05 * 0.35
    return round(score, 4), label, opp_type, uncertainty
