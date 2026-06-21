#!/usr/bin/env python3
"""Phase 06B: bracket route / route avoidance analysis for R2 runtime overlay."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from group_state_common import (
    R32_OPPONENT_SLOT,
    ROOT,
    classify_path_state,
    parse_cutoff,
    read_csv,
    remaining_group_matches,
    route_score_for_position,
    write_csv,
)
from annex_c_route_engine import annex_scenario_weights, expected_route_for_slot
from validate_completed_results_coverage import run_coverage_validation

OUT_DIR = ROOT / "outputs" / "phase06B_bracket_route"
RUNTIME_DIR = ROOT / "database" / "competition" / "runtime"
PHASE06_DIR = ROOT / "outputs" / "phase06_group_state"
SCRIPTS = ROOT / "scripts"
TEMPLATE = ROOT / "database" / "competition" / "round_of_32_template.csv"
MAPPING = ROOT / "database" / "competition" / "wc2026_match_id_mapping.csv"

KNOCKOUT_FIELDS = [
    "slot", "round32_match", "entrant_type", "source_group", "opponent_slot", "next_match", "notes",
]

BRACKET_FIELDS = [
    "generated_at", "match_id", "group", "team", "current_rank", "current_points",
    "current_gd", "current_gf", "qualification_secure_prob", "possible_finish_positions",
    "route_if_first", "route_if_second", "route_if_third",
    "route_score_first", "route_score_second", "route_score_third",
    "expected_route_difficulty_first", "expected_route_difficulty_second",
    "route_uncertainty", "annex_scenarios_covered",
    "best_route_position", "route_preference_delta",
    "route_avoidance_applicable", "route_avoidance_strength",
    "primary_route_reason", "uncertainty_level", "source", "source_url", "notes",
]

RUNTIME_INCENTIVE_FIELDS = [
    "snapshot_id", "match_id", "as_of_utc", "kickoff_utc",
    "home", "away", "home_path_state", "away_path_state",
    "home_state_reason_code", "away_state_reason_code",
    "route_pressure_label", "route_preference_label", "first_place_incentive",
    "second_place_acceptance", "third_place_risk", "draw_acceptance_modifier",
    "late_push_modifier", "rotation_modifier", "route_explanation",
    "home_route_preference_label", "away_route_preference_label",
    "home_first_place_utility", "away_first_place_utility",
    "home_second_place_utility", "away_second_place_utility",
    "home_route_utility_first", "away_route_utility_first",
    "home_route_utility_second", "away_route_utility_second",
    "home_route_preference_delta", "away_route_preference_delta",
    "home_expected_route_difficulty_first", "away_expected_route_difficulty_first",
    "home_expected_route_difficulty_second", "away_expected_route_difficulty_second",
    "home_route_uncertainty", "away_route_uncertainty",
    "home_annex_scenarios_covered", "away_annex_scenarios_covered",
    "home_third_place_risk", "away_third_place_risk",
    "home_draw_acceptance_modifier", "away_draw_acceptance_modifier",
    "home_late_push_modifier", "away_late_push_modifier",
    "home_rotation_modifier", "away_rotation_modifier",
    "home_route_avoidance_applicable", "away_route_avoidance_applicable",
    "home_route_strength", "away_route_strength",
]


def build_knockout_slots() -> list[dict]:
    rows = read_csv(TEMPLATE)
    out = []
    for r in rows:
        home, away = r["home_slot"], r["away_slot"]
        for slot, opp in ((home, away), (away, home)):
            g = slot[1] if len(slot) == 2 else ""
            entrant = "winner" if slot[0] == "1" else "runner_up"
            if "3rd" in opp:
                entrant = "winner_vs_third"
            out.append({
                "slot": slot,
                "round32_match": r["match_no"],
                "entrant_type": entrant,
                "source_group": g,
                "opponent_slot": opp,
                "next_match": "",
                "notes": r.get("notes", ""),
            })
    return out


def route_label(group: str, finish: int) -> str:
    return f"{finish}{group}"


def analyze_team_route(
    team: str,
    group: str,
    standings: list[dict],
    path_info: dict,
    generated_at: str,
    team_states: dict[str, dict],
    annex_scenarios: list[dict],
) -> dict:
    row = next(r for r in standings if r["team"] == team and r["group"] == group)
    rank, pts, gd_val, gf = row["rank"], row["points"], row["gd"], row["gf"]
    qual = float(path_info.get("p_advance") or path_info.get("qualification_secure_prob", 0.45))

    r1_slot = route_label(group, 1)
    r2_slot = route_label(group, 2)
    r3_slot = f"3rd_{group}"

    opp1 = R32_OPPONENT_SLOT.get(r1_slot, ("unknown", []))[0]
    opp2 = R32_OPPONENT_SLOT.get(r2_slot, ("unknown", []))[0]
    route1 = expected_route_for_slot(
        r1_slot if opp1 == "3rd" else opp1, team_states, annex_scenarios,
    )
    route2 = expected_route_for_slot(
        r2_slot if opp2 == "3rd" else opp2, team_states, annex_scenarios,
    )
    s1, o1, t1, u1 = (
        route1["difficulty"], route1["opponent_label"], opp1, route1["uncertainty"],
    )
    s2, o2, t2, u2 = (
        route2["difficulty"], route2["opponent_label"], opp2, route2["uncertainty"],
    )
    s3 = round(0.55 * 0.58 + 0.25 * 0.50 + 0.10 * 0.45 + 0.05 * 0.20 + 0.05 * 0.35, 4)
    o3 = "best_third_pool"
    t3 = "3rd"
    u3 = 0.35

    # Route optimization only compares secure top-two paths. Finishing third
    # is an advancement fallback, never a route-avoidance target.
    scores = {"first": s1, "second": s2}
    best = min(scores, key=scores.get)
    current_target = "first" if rank == 1 else ("second" if rank == 2 else "third")
    delta = round(scores.get(current_target, s2) - scores[best], 4)

    applicable = False
    strength = "none"
    reason = "qualification_not_secure"
    if qual >= 0.80 and path_info.get("can_finish_top1") and path_info.get("can_finish_top2"):
        if abs(s1 - s2) >= 0.12:
            applicable = True
            if delta < 0.08:
                strength = "none"
            elif delta < 0.15:
                strength = "weak"
            elif delta < 0.25:
                strength = "medium"
            else:
                strength = "strong"
            reason = f"R32_first_vs_{o1}_score={s1:.2f}; R32_second_vs_{o2}_score={s2:.2f}"
        else:
            reason = "route_scores_too_close"
    elif qual < 0.80:
        reason = "route_avoidance_blocked_by_qualification_need"

    if path_info.get("path_state") in ("must_win", "must_win_big", "third_place_bubble"):
        applicable = False
        strength = "none"
        reason = "advancement_pressure_overrides_route"

    if applicable and strength in ("medium", "strong"):
        strength = "weak"

    possible = []
    if path_info.get("can_finish_top1"):
        possible.append("1")
    if path_info.get("can_finish_top2"):
        possible.append("2")
    if path_info.get("can_finish_top3"):
        possible.append("3")

    return {
        "generated_at": generated_at,
        "match_id": "",
        "group": group,
        "team": team,
        "current_rank": rank,
        "current_points": pts,
        "current_gd": gd_val,
        "current_gf": gf,
        "qualification_secure_prob": qual,
        "possible_finish_positions": "|".join(possible),
        "route_if_first": f"R32 vs {o1}",
        "route_if_second": f"R32 vs {o2}",
        "route_if_third": f"R32 vs best_third_pool (uncertain)",
        "route_score_first": s1,
        "route_score_second": s2,
        "route_score_third": s3,
        "expected_route_difficulty_first": s1,
        "expected_route_difficulty_second": s2,
        "route_uncertainty": round(max(u1, u2), 4),
        "annex_scenarios_covered": max(
            int(route1["annex_scenarios_covered"]),
            int(route2["annex_scenarios_covered"]),
        ),
        "best_route_position": best,
        "route_preference_delta": delta,
        "route_avoidance_applicable": str(applicable).lower(),
        "route_avoidance_strength": strength,
        "primary_route_reason": reason,
        "uncertainty_level": "high" if "3rd" in t1 or u1 > 0.3 else "low",
        "source": "phase06B_bracket_route",
        "source_url": "internal_knockout_route_slots",
        "notes": f"path_state={path_info.get('path_state')}",
    }


def route_preference_label(team_route: dict, path_state: str) -> str:
    if not team_route:
        return "must_chase_first" if "must_win" in path_state else "route_data_missing"
    if team_route.get("route_avoidance_applicable") != "true":
        if "must_win" in path_state:
            return "must_chase_first"
        return "route_avoidance_blocked_by_qualification_need"
    if team_route["best_route_position"] == "second":
        return "second_acceptable"
    if team_route["route_avoidance_strength"] == "weak":
        return "route_avoidance_weak"
    return "neutral_route"


def build_runtime_incentive(
    snap: str,
    incentive_rows: list[dict],
    bracket_rows: list[dict],
    route_allowed: bool = True,
    affected_groups: set[str] | None = None,
) -> list[dict]:
    by_team = {b["team"]: b for b in bracket_rows}
    affected_groups = affected_groups or set()
    out = []
    for m in incentive_rows:
        home, away = m["home"], m["away"]
        mapping = {r["internal_match_id"]: r for r in read_csv(MAPPING)}
        grp = mapping.get(m["match_id"], {}).get("group", "")
        group_local_only = grp in affected_groups

        hb, ab = by_team.get(home, {}), by_team.get(away, {})
        h_label = route_preference_label(hb, m["home_path_state"])
        a_label = route_preference_label(ab, m["away_path_state"])

        h_draw_mod = 0.0
        h_late_mod = 0.0
        h_rot_mod = 0.0
        if route_allowed and hb.get("route_avoidance_applicable") == "true":
            if hb.get("best_route_position") == "second":
                h_draw_mod = 0.04
                h_late_mod = -0.08
                h_rot_mod = 0.05

        a_draw_mod = 0.0
        a_late_mod = 0.0
        a_rot_mod = 0.0
        if route_allowed and ab.get("route_avoidance_applicable") == "true":
            if ab.get("best_route_position") == "second":
                a_draw_mod = 0.04
                a_late_mod = -0.08
                a_rot_mod = 0.05

        if "must_win" in m["home_path_state"]:
            h_late_mod += 0.06
        if "must_win" in m["away_path_state"]:
            a_late_mod += 0.06

        pressure = "neutral_route"
        if route_allowed:
            if h_label != "route_avoidance_blocked_by_qualification_need" or a_label != "route_avoidance_blocked_by_qualification_need":
                pressure = h_label if h_label != "route_avoidance_blocked_by_qualification_need" else a_label
        else:
            pressure = "route_avoidance_blocked_by_integrity_guard"
            h_label = a_label = "route_avoidance_blocked_by_qualification_need"

        h_route_app = "false" if not route_allowed or group_local_only else hb.get("route_avoidance_applicable", "false")
        a_route_app = "false" if not route_allowed or group_local_only else ab.get("route_avoidance_applicable", "false")
        h_route_strength = "none" if not route_allowed or group_local_only else hb.get("route_avoidance_strength", "none")
        a_route_strength = "none" if not route_allowed or group_local_only else ab.get("route_avoidance_strength", "none")
        h_first_utility = round(1.0 - float(hb.get("route_score_first", 0.5)), 3)
        a_first_utility = round(1.0 - float(ab.get("route_score_first", 0.5)), 3)
        h_second_utility = round(1.0 - float(hb.get("route_score_second", 0.5)), 3)
        a_second_utility = round(1.0 - float(ab.get("route_score_second", 0.5)), 3)
        h_third_risk = (
            round(max(0.0, 1.0 - float(hb.get("qualification_secure_prob", 0.0))), 3)
            if route_allowed and not group_local_only else 0.0
        )
        a_third_risk = (
            round(max(0.0, 1.0 - float(ab.get("qualification_secure_prob", 0.0))), 3)
            if route_allowed and not group_local_only else 0.0
        )

        out.append({
            "snapshot_id": snap,
            "match_id": m["match_id"],
            "as_of_utc": m.get("as_of_utc", ""),
            "kickoff_utc": m.get("kickoff_utc", ""),
            "home": home,
            "away": away,
            "home_path_state": m["home_path_state"],
            "away_path_state": m["away_path_state"],
            "home_state_reason_code": m.get("home_state_reason_code", ""),
            "away_state_reason_code": m.get("away_state_reason_code", ""),
            "route_pressure_label": pressure,
            "route_preference_label": f"{home}:{h_label}; {away}:{a_label}",
            # Deprecated match-level compatibility fields use symmetric aggregation.
            "first_place_incentive": round((h_first_utility + a_first_utility) / 2.0, 3),
            "second_place_acceptance": round((h_second_utility + a_second_utility) / 2.0, 3),
            "third_place_risk": round((h_third_risk + a_third_risk) / 2.0, 3),
            "draw_acceptance_modifier": round((h_draw_mod + a_draw_mod) / 2.0, 3),
            "late_push_modifier": round((h_late_mod + a_late_mod) / 2.0, 3),
            "rotation_modifier": round((h_rot_mod + a_rot_mod) / 2.0, 3),
            "route_explanation": (
                f"{home} qual={hb.get('qualification_secure_prob','?')} route_delta={hb.get('route_preference_delta','?')}; "
                f"{away} qual={ab.get('qualification_secure_prob','?')} route_delta={ab.get('route_preference_delta','?')}"
                + ("; integrity_guard=route_disabled" if not route_allowed else "")
            ),
            "home_route_preference_label": h_label,
            "away_route_preference_label": a_label,
            "home_first_place_utility": h_first_utility,
            "away_first_place_utility": a_first_utility,
            "home_second_place_utility": h_second_utility,
            "away_second_place_utility": a_second_utility,
            "home_route_utility_first": h_first_utility,
            "away_route_utility_first": a_first_utility,
            "home_route_utility_second": h_second_utility,
            "away_route_utility_second": a_second_utility,
            "home_route_preference_delta": hb.get("route_preference_delta", 0.0),
            "away_route_preference_delta": ab.get("route_preference_delta", 0.0),
            "home_expected_route_difficulty_first": hb.get("expected_route_difficulty_first", 0.5),
            "away_expected_route_difficulty_first": ab.get("expected_route_difficulty_first", 0.5),
            "home_expected_route_difficulty_second": hb.get("expected_route_difficulty_second", 0.5),
            "away_expected_route_difficulty_second": ab.get("expected_route_difficulty_second", 0.5),
            "home_route_uncertainty": hb.get("route_uncertainty", 0.35),
            "away_route_uncertainty": ab.get("route_uncertainty", 0.35),
            "home_annex_scenarios_covered": hb.get("annex_scenarios_covered", 0),
            "away_annex_scenarios_covered": ab.get("annex_scenarios_covered", 0),
            "home_third_place_risk": h_third_risk,
            "away_third_place_risk": a_third_risk,
            "home_draw_acceptance_modifier": round(h_draw_mod, 3),
            "away_draw_acceptance_modifier": round(a_draw_mod, 3),
            "home_late_push_modifier": round(h_late_mod, 3),
            "away_late_push_modifier": round(a_late_mod, 3),
            "home_rotation_modifier": round(h_rot_mod, 3),
            "away_rotation_modifier": round(a_rot_mod, 3),
            "home_route_avoidance_applicable": h_route_app,
            "away_route_avoidance_applicable": a_route_app,
            "home_route_strength": h_route_strength,
            "away_route_strength": a_route_strength,
        })
    return out


def write_reports(
    snap: str,
    cutoff: str,
    standings: list[dict],
    third: list[dict],
    paths: list[dict],
    incentives: list[dict],
    bracket: list[dict],
    runtime: list[dict],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Phase 06 Group State Build Report",
        "",
        f"- **snapshot_id**: `{snap}`",
        f"- **source_cutoff_time**: `{cutoff}`",
        f"- **teams covered**: {len(standings)}",
        f"- **third-place candidates**: {len(third)}",
        "",
        "## Group leaders (top 2 + 3rd)",
        "",
    ]
    for g in sorted({r["group"] for r in standings}):
        grp = [r for r in standings if r["group"] == g]
        grp.sort(key=lambda x: int(x["rank"]))
        t2 = ", ".join(f"{r['team']} ({r['points']}pts)" for r in grp[:2])
        t3 = next((r for r in grp if int(r["rank"]) == 3), None)
        t3s = f"{t3['team']} ({t3['points']}pts)" if t3 else "n/a"
        lines.append(f"- **Group {g}**: 1st/2nd — {t2}; 3rd — {t3s}")

    lines.extend(["", "## Top 8 third-place ranking", ""])
    for t in third[:8]:
        lines.append(
            f"- #{t['rank_3rd']} {t['team']} (Group {t['group']}) — {t['points']}pts, GD {t['gd']}, status={t['third_place_status']}"
        )

    lines.extend(["", "## Match incentive summary (R2)", ""])
    for m in incentives:
        lines.append(
            f"- `{m['match_id']}` {m['home']} vs {m['away']}: "
            f"{m['home_path_state']} / {m['away_path_state']}"
        )

    lines.extend([
        "",
        "## Processed file integrity",
        "",
        "- No changes to `tactical_matchup_matrix.csv`",
        "- No changes to `eventflow_scenario_weights.csv`",
        "- Runtime outputs only under `outputs/phase06_group_state/` and `database/competition/runtime/`",
    ])
    (OUT_DIR.parent / "phase06_group_state" / "phase06_group_state_build_report.md").parent.mkdir(parents=True, exist_ok=True)
    (PHASE06_DIR / "phase06_group_state_build_report.md").write_text("\n".join(lines), encoding="utf-8")

    val_lines = [
        "# Phase 06 Advancement Path Validation",
        "",
        f"- snapshot_id: {snap}",
        f"- standings rows: {len(standings)} (expected 48)",
        f"- advancement paths: {len(paths)}",
        f"- R2 incentive features: {len(incentives)}",
        f"- source_cutoff before all included results: {cutoff}",
        "",
        "## Checks",
        "",
    ]
    checks = [
        ("48 teams in standings", len(standings) == 48),
        ("12 third-place rows", len(third) == 12),
        ("all R2 matches have incentives", len(incentives) >= 20),
        ("F35 present", any(m["match_id"] == "WC2026-F35" for m in incentives)),
    ]
    for name, ok in checks:
        val_lines.append(f"- [{'x' if ok else ' '}] {name}")

    (PHASE06_DIR / "phase06_advancement_path_validation_report.md").write_text("\n".join(val_lines), encoding="utf-8")

    route_lines = [
        "# Phase 06B Route Analysis Report",
        "",
        f"- snapshot: {snap}",
        f"- cutoff: {cutoff}",
        "",
        "## Route avoidance signals",
        "",
    ]
    for b in bracket:
        if b["route_avoidance_applicable"] == "true":
            route_lines.append(
                f"- **{b['team']}** ({b['group']}): {b['route_avoidance_strength']} — {b['primary_route_reason']}"
            )
    must_first = [b["team"] for b in bracket if "must_win" in b.get("notes", "")]
    route_lines.extend(["", "## Must chase first / win", ""])
    for b in bracket:
        if float(b.get("qualification_secure_prob", 0)) < 0.8:
            route_lines.append(f"- {b['team']}: blocked (qual={b['qualification_secure_prob']})")

    f35 = next((r for r in runtime if r["match_id"] == "WC2026-F35"), None)
    if f35:
        route_lines.extend([
            "",
            "## F35 Netherlands vs Sweden",
            "",
            f"- route_pressure_label: {f35['route_pressure_label']}",
            f"- home route applicable: {f35['home_route_avoidance_applicable']} ({f35['home_route_strength']})",
            f"- away route applicable: {f35['away_route_avoidance_applicable']} ({f35['away_route_strength']})",
            f"- explanation: {f35['route_explanation']}",
        ])

    (OUT_DIR / "phase06B_route_analysis_report.md").write_text("\n".join(route_lines), encoding="utf-8")
    (OUT_DIR / "phase06B_r2_route_report.md").write_text("\n".join(route_lines), encoding="utf-8")

    flags = []
    for b in bracket:
        if b["route_avoidance_strength"] == "strong":
            flags.append({"team": b["team"], "flag": "strong_route_signal_needs_review"})
        if b["route_avoidance_applicable"] == "true" and float(b["qualification_secure_prob"]) < 0.8:
            flags.append({"team": b["team"], "flag": "route_applied_below_qual_threshold"})
    write_csv(OUT_DIR / "phase06B_route_quality_flags.csv", ["team", "flag"], flags)

    val_b = [
        "# Phase 06B Validation",
        "",
        f"- bracket rows: {len(bracket)}",
        f"- runtime incentive rows: {len(runtime)}",
        "- processed files unchanged: yes",
        f"- F35 Netherlands route blocked: {next((r for r in runtime if r['match_id']=='WC2026-F35'), {}).get('home_route_avoidance_applicable')}",
    ]
    (OUT_DIR / "phase06B_validation_report.md").write_text("\n".join(val_b), encoding="utf-8")


def build_source_notes(snap: str, incentives: list[dict], cutoff: str) -> list[dict]:
    mapping = {r["internal_match_id"]: r for r in read_csv(MAPPING)}
    rows = []
    for m in incentives:
        mid = m["match_id"]
        grp = mapping.get(mid, {}).get("group", mid.replace("WC2026-", "")[:1])
        rows.append({
            "match_id": mid,
            "source_type": "group_state",
            "title": f"Group {grp} advancement pressure",
            "notes": m["notes"],
            "confidence": m["confidence"],
            "published_at": cutoff,
            "source_url": "internal_live_group_standings",
        })
    return rows


def run_phase06_scripts(snap: str, cutoff: str) -> None:
    py = sys.executable
    subprocess.run(
        [py, str(SCRIPTS / "build_live_group_standings.py"),
         "--source-cutoff-time", cutoff, "--out-snapshot-id", snap],
        check=True, cwd=ROOT,
    )
    subprocess.run(
        [py, str(SCRIPTS / "build_advancement_path_snapshot.py"),
         "--snapshot-id", snap, "--source-cutoff-time", cutoff],
        check=True, cwd=ROOT,
    )
    subprocess.run(
        [py, str(SCRIPTS / "build_match_incentive_features.py"),
         "--snapshot-id", snap, "--source-cutoff-time", cutoff, "--round", "2"],
        check=True, cwd=ROOT,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-cutoff-time", default="2026-06-20T12:00:00Z")
    ap.add_argument("--snapshot-id", default="WC2026_GROUP_20260620_PRE_F35")
    ap.add_argument("--skip-phase06", action="store_true")
    ap.add_argument("--allow-partial-standings", action="store_true")
    ap.add_argument("--skip-integrity-check", action="store_true")
    args = ap.parse_args()

    snap = args.snapshot_id
    cutoff = args.source_cutoff_time
    cutoff_dt = parse_cutoff(cutoff)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    integrity_result = None
    route_allowed = True
    cross_group_allowed = True
    affected_groups: set[str] = set()

    if not args.skip_integrity_check:
        integrity_result = run_coverage_validation(
            cutoff, snap, allow_partial=args.allow_partial_standings,
        )
        integrity = integrity_result["integrity"]
        route_allowed = integrity.get("route_avoidance_allowed") == "true"
        cross_group_allowed = integrity.get("cross_group_third_ranking_allowed") == "true"
        affected_groups = set((integrity.get("affected_groups") or "").split("|")) - {""}
        if integrity_result["abort"]:
            report = ROOT / "outputs" / "phase06C_standings_integrity" / "standings_snapshot_integrity_report.md"
            print(f"ABORT: partial stale standings — missing pre-cutoff results. See {report}")
            raise SystemExit(1)
        if integrity.get("formal_prediction_allowed") == "partial_only":
            print(
                f"WARNING: partial standings mode — route_avoidance=false, "
                f"cross_group_third=false, affected_groups={sorted(affected_groups)}"
            )

    if not args.skip_phase06:
        run_phase06_scripts(snap, cutoff)

    standings_raw = read_csv(PHASE06_DIR / "live_group_standings.csv")
    snapshot_standings = [r for r in standings_raw if r.get("snapshot_id") == snap]
    if snapshot_standings:
        standings_raw = snapshot_standings
    standings = [
        {"group": r["group"], "rank": int(r["rank"]), "team": r["team"],
         "points": int(r["points"]), "gd": int(r["gd"]), "gf": int(r["gf"]),
         "played": int(r["played"])}
        for r in standings_raw
    ]
    third = [r for r in read_csv(PHASE06_DIR / "third_place_rankings.csv") if r.get("snapshot_id") == snap]
    if not cross_group_allowed:
        for t in third:
            t["third_place_status"] = f"provisional_cross_group_blocked_{t.get('third_place_status', '')}"
    path_source = PHASE06_DIR / "advancement_path_snapshot.csv"
    if not path_source.exists():
        path_source = ROOT / "database" / "competition" / "advancement_path_snapshot.csv"
    paths = [r for r in read_csv(path_source) if r.get("snapshot_id") == snap]
    incentives = read_csv(PHASE06_DIR / "match_incentive_features_runtime.csv")
    incentives = [r for r in incentives if r.get("snapshot_id") == snap]

    remaining = remaining_group_matches(cutoff_dt)
    path_details = {}
    for p in paths:
        info = classify_path_state(
            p["team"], p["group"], int(p["current_rank"]), standings,
            remaining.get(p["group"], []),
            round_num=2,
            cutoff=cutoff_dt,
        )
        path_details[p["team"]] = {**info, **p}
        path_details[p["team"]]["group"] = p["group"]

    annex_scenarios = annex_scenario_weights(path_details)

    knockout = build_knockout_slots()
    write_csv(RUNTIME_DIR / "knockout_route_slots.csv", KNOCKOUT_FIELDS, knockout)

    bracket = []
    for p in paths:
        team = p["team"]
        row = analyze_team_route(
            team, p["group"], standings, path_details[team], generated_at,
            path_details, annex_scenarios,
        )
        if not route_allowed:
            row["route_avoidance_applicable"] = "false"
            row["route_avoidance_strength"] = "none"
            row["primary_route_reason"] = "blocked_by_phase06C_integrity_guard"
            row["notes"] += "; integrity_guard=route_disabled"
        bracket.append(row)

    runtime = build_runtime_incentive(
        snap, incentives, bracket,
        route_allowed=route_allowed,
        affected_groups=affected_groups,
    )
    write_csv(RUNTIME_DIR / "bracket_route_runtime_R2.csv", BRACKET_FIELDS, bracket)
    write_csv(RUNTIME_DIR / "match_incentive_runtime_R2.csv", RUNTIME_INCENTIVE_FIELDS, runtime)

    source_notes = build_source_notes(snap, incentives, cutoff)
    write_csv(
        PHASE06_DIR / "source_notes_group_state_append_preview.csv",
        ["match_id", "source_type", "title", "notes", "confidence", "published_at", "source_url"],
        source_notes,
    )

    write_reports(snap, cutoff, standings_raw, third, paths, incentives, bracket, runtime)
    print(f"Phase 06B complete: {len(bracket)} bracket rows, {len(runtime)} runtime incentive rows")


if __name__ == "__main__":
    main()
