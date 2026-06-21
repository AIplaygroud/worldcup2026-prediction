#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build V3.7 normalized tables from local Scheme-B data sources."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from eventflow_common import read_csv, write_csv
from group_state_common import build_standings, pre_kickoff_cutoff, remaining_group_matches
from annex_c_route_engine import annex_scenario_weights, best8_third_probabilities
from v37_common import (
    AVAILABILITY_SIGNALS,
    FEATURE_TABLES,
    JC_ODDS_SUMMARY,
    MATCH_XG,
    NORMALIZED_TABLES,
    V37_AUDIT,
    ensure_v37_dirs,
    fixture_row,
    kickoff_from_mapping,
    load_mapping,
    match_odds_by_teams,
    parse_big_chances,
    snum,
)

MATCH_FIELDS = [
    "match_id", "provider_match_id", "competition", "season", "stage", "group", "round",
    "home_team", "away_team", "kickoff_utc", "venue", "city", "country", "status",
    "home_score", "away_score", "home_ht_score", "away_ht_score",
]

STANDINGS_FIELDS = [
    "snapshot_id", "match_id", "group", "team", "points_before", "played_before",
    "wins_before", "draws_before", "losses_before", "gf_before", "ga_before", "gd_before",
    "rank_before", "remaining_matches", "remaining_opponents", "can_qualify_if_win",
    "can_qualify_if_draw", "elimination_risk_if_loss", "draw_utility", "win_necessity",
    "round_before", "path_state",
    "state_reason_code",
    "p_finish_1", "p_finish_2", "p_finish_3", "p_finish_4",
    "p_top2", "p_best8_third", "p_advance",
]

LINEUP_FIELDS = [
    "match_id", "team", "player_id", "player_name", "is_starter", "is_bench", "position",
    "role_group", "importance_tier", "formation_slot", "lineup_status", "source",
    "evidence_grade", "confirmed_at_utc",
]

AVAIL_FIELDS = [
    "match_id", "team", "player", "signal_type", "status", "role_group", "importance_tier",
    "evidence_grade", "confirmed", "source", "updated_at",
]

EVENT_FIELDS = [
    "match_id", "event_id", "minute", "stoppage_minute", "team", "event_type", "player",
    "assist_player", "score_home_after", "score_away_after", "card_type", "sub_in", "sub_out",
    "source", "confirmed",
]

STATS_FIELDS = [
    "match_id", "team", "data_timing", "shots", "shots_on_target", "xg", "big_chances",
    "corners", "passes", "pass_accuracy", "possession", "saves", "sot_faced",
    "goals_prevented", "ppda", "field_tilt", "source", "quality_flag",
]

TEAM_RECENT_FIELDS = [
    "match_id", "team", "matches_played", "xg_for_avg", "xg_against_avg", "shots_avg",
    "sot_avg", "big_chances_avg", "goals_for_avg", "goals_against_avg", "form_points",
    "data_timing", "source", "quality_flag",
]

ODDS_FIELDS = [
    "match_id", "market", "selection", "sp", "handicap", "total_line", "single_allowed",
    "pool_status", "provider", "fetched_at_utc", "is_opening", "is_closing",
]


def _xg_index() -> dict[tuple[str, str, str], dict[str, str]]:
    out: dict[tuple[str, str, str], dict[str, str]] = {}
    for r in read_csv(MATCH_XG):
        key = (r.get("match_date", ""), r.get("home_team", ""), r.get("away_team", ""))
        out[key] = r
    return out


def _find_xg(home: str, away: str, kickoff: datetime, xg_idx: dict) -> Optional[dict[str, str]]:
    date_s = kickoff.strftime("%Y-%m-%d")
    return xg_idx.get((date_s, home, away))


def _match_status(home: str, away: str, kickoff: datetime, xg_idx: dict) -> tuple[str, str, str, str, str, str]:
    row = _find_xg(home, away, kickoff, xg_idx)
    if not row:
        return "scheduled", "", "", "", "", ""
    return (
        "finished",
        snum(row, "home_score"),
        snum(row, "away_score"),
        "",
        "",
        snum(row, "quality_flag", "ok"),
    )


def build_matches(match_filter: str = "") -> list[dict[str, Any]]:
    xg_idx = _xg_index()
    rows: list[dict[str, Any]] = []
    for m in load_mapping(match_filter):
        fid = snum(m, "fifa_match_id")
        fix = fixture_row(fid)
        kickoff = kickoff_from_mapping(m)
        status, hs, aws, hht, aht, _ = _match_status(m["home_team"], m["away_team"], kickoff, xg_idx)
        rows.append({
            "match_id": m["internal_match_id"],
            "provider_match_id": fid,
            "competition": "WC2026",
            "season": "2026",
            "stage": "group",
            "group": m["group"],
            "round": m["round"],
            "home_team": m["home_team"],
            "away_team": m["away_team"],
            "kickoff_utc": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "venue": snum(fix, "venue"),
            "city": snum(fix, "city"),
            "country": snum(fix, "host_country"),
            "status": status,
            "home_score": hs,
            "away_score": aws,
            "home_ht_score": hht,
            "away_ht_score": aht,
        })
    return rows


def build_standings_snapshots(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for m in matches:
        kickoff = datetime.fromisoformat(m["kickoff_utc"].replace("Z", "+00:00"))
        cutoff = pre_kickoff_cutoff(kickoff)
        snap_id = f"V37_PRE_{m['match_id']}"
        standings, _, _ = build_standings(cutoff)
        remaining = remaining_group_matches(cutoff)
        all_details: dict[str, dict[str, Any]] = {
            standing["team"]: {
                "group": standing["group"],
                "points": standing["points"],
                "gd": standing["gd"],
                "p_finish_1": 1.0 if int(standing["rank"]) == 1 else 0.0,
                "p_finish_2": 1.0 if int(standing["rank"]) == 2 else 0.0,
                "p_finish_3": 1.0 if int(standing["rank"]) == 3 else 0.0,
                "p_finish_4": 1.0 if int(standing["rank"]) == 4 else 0.0,
            }
            for standing in standings
        }
        from v37_common import path_detail_for_team
        for standing in standings:
            if standing["team"] not in (m["home_team"], m["away_team"]):
                continue
            detail = path_detail_for_team(
                standing["team"], standing["group"], standings, cutoff, round_num=int(m["round"]),
            )
            all_details[standing["team"]] = {**detail, "group": standing["group"]}
        annex_scenarios = annex_scenario_weights(all_details)
        p_best8 = best8_third_probabilities(all_details, annex_scenarios)
        group = m["group"]
        rem_list = remaining.get(group, [])
        rem_opponents: list[str] = []
        for rm in rem_list:
            if rm["internal_match_id"] == m["match_id"]:
                continue
            if rm["home_team"] in (m["home_team"], m["away_team"]):
                rem_opponents.append(rm["away_team"])
            elif rm["away_team"] in (m["home_team"], m["away_team"]):
                rem_opponents.append(rm["home_team"])

        for team in (m["home_team"], m["away_team"]):
            st = next((r for r in standings if r["team"] == team and r["group"] == group), None)
            if not st:
                continue
            detail = all_details[team]
            win_nec = clip_win_necessity(detail)
            draw_util = float(detail.get("draw_acceptance", 0.3))
            p_advance = min(1.0, float(detail.get("p_top2", 0.0)) + p_best8.get(team, 0.0))
            rows.append({
                "snapshot_id": snap_id,
                "match_id": m["match_id"],
                "group": group,
                "team": team,
                "points_before": st["points"],
                "played_before": st["played"],
                "wins_before": st["wins"],
                "draws_before": st["draws"],
                "losses_before": st["losses"],
                "gf_before": st["gf"],
                "ga_before": st["ga"],
                "gd_before": st["gd"],
                "rank_before": st["rank"],
                "remaining_matches": detail.get("remaining_matches", 0),
                "remaining_opponents": ";".join(sorted(set(rem_opponents))),
                "can_qualify_if_win": str(detail.get("can_finish_top2", False)).lower(),
                "can_qualify_if_draw": str(detail.get("can_finish_top3", False)).lower(),
                "elimination_risk_if_loss": str(detail.get("can_be_eliminated", False)).lower(),
                "draw_utility": round(draw_util, 4),
                "win_necessity": round(win_nec, 4),
                "round_before": m["round"],
                "path_state": detail.get("path_state", ""),
                "state_reason_code": detail.get("state_reason_code", detail.get("state_reason_codes", "")),
                "p_finish_1": detail.get("p_finish_1", 0.0),
                "p_finish_2": detail.get("p_finish_2", 0.0),
                "p_finish_3": detail.get("p_finish_3", 0.0),
                "p_finish_4": detail.get("p_finish_4", 0.0),
                "p_top2": detail.get("p_top2", 0.0),
                "p_best8_third": p_best8.get(team, 0.0),
                "p_advance": round(p_advance, 4),
            })
    return rows


def clip_win_necessity(detail: dict[str, Any]) -> float:
    state = detail.get("path_state", "")
    base = 0.25
    if state in ("opening_round", "baseline_opening"):
        base = 0.28
    elif "must_win" in state:
        base = 0.75 if state == "must_win_big" else 0.68
    elif state in ("third_place_bubble", "control_destiny"):
        base = 0.55
    elif state == "must_not_lose":
        base = 0.42
    elif state in ("clinched_top2", "near_clinched"):
        base = 0.15
    elif state == "top_slot_chase":
        base = 0.50
    elif state == "open_group":
        base = 0.35
    gd_chase = float(detail.get("goal_diff_chase", 0.0))
    return min(1.0, base + gd_chase * 0.15)


def build_lineups_and_availability(match_filter: str = "") -> tuple[list[dict], list[dict]]:
    lineups: list[dict] = []
    avail: list[dict] = []
    for sig in read_csv(AVAILABILITY_SIGNALS):
        mid = snum(sig, "match_id")
        if match_filter and mid != match_filter:
            continue
        status = snum(sig, "status")
        confirmed = snum(sig, "confirmed").lower() == "true"
        lineup_status = "confirmed" if confirmed else "doubtful" if status == "doubtful" else "predicted"
        player = snum(sig, "player")
        lineups.append({
            "match_id": mid,
            "team": snum(sig, "team"),
            "player_id": "",
            "player_name": player,
            "is_starter": str(status in ("starts", "start")).lower(),
            "is_bench": str(status == "benched").lower(),
            "position": snum(sig, "role"),
            "role_group": snum(sig, "role_group"),
            "importance_tier": snum(sig, "importance_tier"),
            "formation_slot": "",
            "lineup_status": lineup_status,
            "source": "realtime_availability_signals",
            "evidence_grade": snum(sig, "evidence_grade", "C"),
            "confirmed_at_utc": snum(sig, "updated_at"),
        })
        avail.append({
            "match_id": mid,
            "team": snum(sig, "team"),
            "player": player,
            "signal_type": snum(sig, "signal_type"),
            "status": status,
            "role_group": snum(sig, "role_group"),
            "importance_tier": snum(sig, "importance_tier"),
            "evidence_grade": snum(sig, "evidence_grade"),
            "confirmed": str(confirmed).lower(),
            "source": "realtime_availability_signals",
            "updated_at": snum(sig, "updated_at"),
        })
    deduped_avail: list[dict] = []
    seen_avail: set[tuple[str, str, str, str]] = set()
    for row in avail:
        key = (
            row["match_id"], row["team"], row["player"], row["signal_type"],
        )
        if key in seen_avail:
            continue
        seen_avail.add(key)
        deduped_avail.append(row)
    return lineups, deduped_avail


def build_match_stats_pre(match_filter: str = "") -> tuple[list[dict], list[dict]]:
    """Rolling pre-match stats per team per upcoming match."""
    stats_rows: list[dict] = []
    team_recent_rows: list[dict] = []
    xg_all = read_csv(MATCH_XG)
    fixture_kickoffs = {
        (m["home_team"], m["away_team"]): kickoff_from_mapping(m)
        for m in load_mapping()
    }

    for m in load_mapping(match_filter):
        mid = m["internal_match_id"]
        kickoff = kickoff_from_mapping(m)
        cutoff = pre_kickoff_cutoff(kickoff)
        for team, side in ((m["home_team"], "home"), (m["away_team"], "away")):
            prior = [
                r for r in xg_all
                if fixture_kickoffs.get(
                    (r["home_team"], r["away_team"]),
                    datetime.combine(_kickoff_date(r), datetime.min.time(), tzinfo=timezone.utc),
                ) < cutoff
                and team in (r["home_team"], r["away_team"])
            ]
            agg = _aggregate_team_xg(team, prior)
            stats_rows.append({
                "match_id": mid,
                "team": team,
                "data_timing": "pre_match_rolling",
                "shots": round(agg["shots"], 2),
                "shots_on_target": round(agg["sot"], 2),
                "xg": round(agg["xg_for"], 3),
                "big_chances": round(agg["big_chances"], 2),
                "corners": "",
                "passes": "",
                "pass_accuracy": "",
                "possession": "",
                "saves": "",
                "sot_faced": round(agg["sot_against"], 2),
                "goals_prevented": "",
                "ppda": "",
                "field_tilt": "",
                "source": "wc2026_match_xg_rolling",
                "quality_flag": "proxy" if not prior else "ok",
            })
            team_recent_rows.append({
                "match_id": mid,
                "team": team,
                "matches_played": len(prior),
                "xg_for_avg": round(agg["xg_for"], 3),
                "xg_against_avg": round(agg["xg_against"], 3),
                "shots_avg": round(agg["shots"], 2),
                "sot_avg": round(agg["sot"], 2),
                "big_chances_avg": round(agg["big_chances"], 2),
                "goals_for_avg": round(agg["goals_for"], 2),
                "goals_against_avg": round(agg["goals_against"], 2),
                "form_points": round(agg["form_points"], 2),
                "data_timing": "pre_match_rolling",
                "source": "wc2026_match_xg_rolling",
                "quality_flag": "proxy" if not prior else "ok",
            })

        # post_match_final rows for finished matches (audit only)
        finished = _find_xg(m["home_team"], m["away_team"], kickoff, _xg_index())
        if finished:
            for team, opp, is_home in (
                (m["home_team"], m["away_team"], True),
                (m["away_team"], m["home_team"], False),
            ):
                bc_h, bc_a = parse_big_chances(snum(finished, "notes"))
                stats_rows.append({
                    "match_id": mid,
                    "team": team,
                    "data_timing": "post_match_final",
                    "shots": fnum(finished, "home_shots" if is_home else "away_shots"),
                    "shots_on_target": "",
                    "xg": fnum(finished, "home_xg" if is_home else "away_xg"),
                    "big_chances": bc_h if is_home else bc_a,
                    "corners": "",
                    "passes": "",
                    "pass_accuracy": "",
                    "possession": "",
                    "saves": "",
                    "sot_faced": "",
                    "goals_prevented": "",
                    "ppda": "",
                    "field_tilt": "",
                    "source": snum(finished, "source"),
                    "quality_flag": snum(finished, "quality_flag", "ok"),
                })

    return stats_rows, team_recent_rows


def fnum(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _kickoff_date(row: dict[str, str]):
    from datetime import date
    return date.fromisoformat(row["match_date"])


def _aggregate_team_xg(team: str, rows: list[dict[str, str]]) -> dict[str, float]:
    if not rows:
        return {
            "xg_for": 1.0, "xg_against": 1.0, "shots": 12.0, "sot": 4.0,
            "big_chances": 1.5, "goals_for": 1.0, "goals_against": 1.0,
            "form_points": 1.0, "sot_against": 4.0,
        }
    n = len(rows)
    totals = {
        "xg_for": 0.0, "xg_against": 0.0, "shots": 0.0, "sot": 0.0,
        "big_chances": 0.0, "goals_for": 0.0, "goals_against": 0.0,
        "form_points": 0.0, "sot_against": 0.0,
    }
    for r in rows:
        home = r["home_team"] == team
        xg_f = fnum(r, "home_xg" if home else "away_xg")
        xg_a = fnum(r, "away_xg" if home else "home_xg")
        shots = fnum(r, "home_shots" if home else "away_shots")
        sot_opp = fnum(r, "away_shots" if home else "home_shots") * 0.35
        bc_h, bc_a = parse_big_chances(snum(r, "notes"))
        bc = (bc_h if home else bc_a) or 0.0
        gf = fnum(r, "home_score" if home else "away_score")
        ga = fnum(r, "away_score" if home else "home_score")
        pts = 3 if gf > ga else 1 if gf == ga else 0
        totals["xg_for"] += xg_f
        totals["xg_against"] += xg_a
        totals["shots"] += shots
        totals["sot"] += shots * 0.35
        totals["big_chances"] += bc
        totals["goals_for"] += gf
        totals["goals_against"] += ga
        totals["form_points"] += pts
        totals["sot_against"] += sot_opp
    return {k: v / n for k, v in totals.items()}


def build_odds_snapshots(match_filter: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    existing = read_csv(NORMALIZED_TABLES["odds_snapshots"])
    if match_filter:
        existing = [r for r in existing if r.get("match_id") == match_filter]
    odds_all = read_csv(JC_ODDS_SUMMARY)
    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for m in load_mapping(match_filter):
        mid = m["internal_match_id"]
        odds = match_odds_by_teams(m["home_team"], m["away_team"], odds_all)
        if not odds:
            continue

        def pool_status(sp_val: str, single: str) -> str:
            if not sp_val or sp_val in ("", "未开售"):
                return "closed"
            return "open"

        def add_row(market: str, selection: str, sp: str, handicap: str = "", single: str = "") -> None:
            if not sp or sp in ("", "未开售"):
                return
            rows.append({
                "match_id": mid,
                "market": market,
                "selection": selection,
                "sp": sp,
                "handicap": handicap,
                "total_line": "",
                "single_allowed": str(single == "是").lower(),
                "pool_status": pool_status(sp, single),
                "provider": "local_jc_odds",
                "fetched_at_utc": fetched,
                "is_opening": "false",
                "is_closing": "false",
            })

        add_row("had", "home", snum(odds, "had_home"), single=snum(odds, "had_single"))
        add_row("had", "draw", snum(odds, "had_draw"), single=snum(odds, "had_single"))
        add_row("had", "away", snum(odds, "had_away"), single=snum(odds, "had_single"))
        line = snum(odds, "hhad_line")
        add_row("hhad", "home", snum(odds, "hhad_home"), handicap=line, single=snum(odds, "hhad_single"))
        add_row("hhad", "draw", snum(odds, "hhad_draw"), handicap=line, single=snum(odds, "hhad_single"))
        add_row("hhad", "away", snum(odds, "hhad_away"), handicap=line, single=snum(odds, "hhad_single"))

    seen = {
        (
            r.get("match_id", ""),
            r.get("market", ""),
            r.get("selection", ""),
            r.get("provider", ""),
            r.get("fetched_at_utc", ""),
            r.get("is_opening", ""),
            r.get("is_closing", ""),
        )
        for r in rows
    }
    current_local = {
        (r.get("match_id", ""), r.get("market", ""), r.get("selection", ""), r.get("provider", ""))
        for r in rows
        if r.get("provider") == "local_jc_odds"
    }
    for row in existing:
        local_identity = (
            row.get("match_id", ""), row.get("market", ""),
            row.get("selection", ""), row.get("provider", ""),
        )
        if row.get("provider") == "local_jc_odds" and local_identity in current_local:
            continue
        key = (
            row.get("match_id", ""),
            row.get("market", ""),
            row.get("selection", ""),
            row.get("provider", ""),
            row.get("fetched_at_utc", ""),
            row.get("is_opening", ""),
            row.get("is_closing", ""),
        )
        if key not in seen:
            rows.append(row)
            seen.add(key)
    return rows


def build_match_events(match_filter: str = "") -> list[dict[str, Any]]:
    """Minimal events from final scores only (no minute-level timeline in Scheme B)."""
    rows: list[dict[str, Any]] = []
    xg_idx = _xg_index()
    for m in load_mapping(match_filter):
        kickoff = kickoff_from_mapping(m)
        xg = _find_xg(m["home_team"], m["away_team"], kickoff, xg_idx)
        if not xg:
            continue
        mid = m["internal_match_id"]
        rows.append({
            "match_id": mid,
            "event_id": f"{mid}_ft",
            "minute": "90",
            "stoppage_minute": "",
            "team": "",
            "event_type": "fulltime",
            "player": "",
            "assist_player": "",
            "score_home_after": snum(xg, "home_score"),
            "score_away_after": snum(xg, "away_score"),
            "card_type": "",
            "sub_in": "",
            "sub_out": "",
            "source": "wc2026_match_xg",
            "confirmed": "true",
        })
    return rows


def write_missingness_report(
    matches: list[dict],
    stats: list[dict],
    odds: list[dict],
    standings: list[dict],
    team_recent: list[dict],
) -> None:
    odds_by_mid = {r["match_id"] for r in odds}
    stats_pre = {(r["match_id"], r["team"]) for r in stats if r["data_timing"] == "pre_match_rolling"}
    standings_by_mid: dict[str, set[str]] = {}
    for r in standings:
        standings_by_mid.setdefault(r["match_id"], set()).add(r["team"])

    def _xg_flags(mid: str, home: str, away: str) -> tuple[bool, bool]:
        rows = [r for r in team_recent if r.get("match_id") == mid and r.get("team") in (home, away)]
        if not rows:
            return False, True
        real = any(
            int(float(snum(r, "matches_played") or "0")) > 0
            and snum(r, "quality_flag") == "ok"
            for r in rows
        )
        proxy = any(
            int(float(snum(r, "matches_played") or "0")) == 0
            or snum(r, "quality_flag") == "proxy"
            for r in rows
        )
        return real, proxy and not real

    rows = []
    for m in matches:
        mid = m["match_id"]
        home, away = m["home_team"], m["away_team"]
        has_standing = home in standings_by_mid.get(mid, set()) and away in standings_by_mid.get(mid, set())
        has_stats = all((mid, t) in stats_pre for t in (home, away))
        has_xg_real, has_xg_proxy = _xg_flags(mid, home, away)
        if not team_recent:
            has_xg_real = has_stats
            has_xg_proxy = not has_stats
        rows.append({
            "match_id": mid,
            "has_standing": str(has_standing).lower(),
            "has_recent_xg_real": str(has_xg_real).lower(),
            "has_recent_xg_proxy": str(has_xg_proxy).lower(),
            "has_lineup": "false",
            "has_odds": str(mid in odds_by_mid).lower(),
            "notes": "",
        })
    write_csv(V37_AUDIT / "feature_missingness_report.csv", rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build V3.7 normalized tables from local sources")
    ap.add_argument("--match-id", default="", help="Single match e.g. WC2026-E34")
    ap.add_argument("--competition", default="WC2026")
    args = ap.parse_args()

    ensure_v37_dirs()
    mid_filter = args.match_id

    matches = build_matches(mid_filter)
    standings = build_standings_snapshots(matches)
    lineups, availability = build_lineups_and_availability(mid_filter)
    stats, team_recent = build_match_stats_pre(mid_filter)
    odds = build_odds_snapshots(mid_filter)
    events = build_match_events(mid_filter)

    write_csv(NORMALIZED_TABLES["matches"], matches, MATCH_FIELDS)
    write_csv(NORMALIZED_TABLES["standings_snapshot"], standings, STANDINGS_FIELDS)
    write_csv(NORMALIZED_TABLES["lineups"], lineups, LINEUP_FIELDS)
    write_csv(NORMALIZED_TABLES["player_availability"], availability, AVAIL_FIELDS)
    write_csv(NORMALIZED_TABLES["match_stats"], stats, STATS_FIELDS)
    write_csv(NORMALIZED_TABLES["team_recent_stats"], team_recent, TEAM_RECENT_FIELDS)
    write_csv(NORMALIZED_TABLES["odds_snapshots"], odds, ODDS_FIELDS)
    write_csv(NORMALIZED_TABLES["match_events"], events, EVENT_FIELDS)

    write_missingness_report(matches, stats, odds, standings, team_recent)

    summary = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "match_count": len(matches),
        "standings_rows": len(standings),
        "stats_rows": len(stats),
        "odds_rows": len(odds),
    }
    (V37_AUDIT / "normalized_build_log.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(f"V3.7 normalized tables: {len(matches)} matches, {len(standings)} standing rows, {len(odds)} odds rows")


if __name__ == "__main__":
    main()
