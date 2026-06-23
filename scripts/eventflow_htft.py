#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""Match ID resolution, HT/FT scoring with favorite/home perspective, data quality."""

from __future__ import annotations

import math

from collections import defaultdict

from pathlib import Path

from typing import Any, Dict, List, Tuple



from eventflow_common import DB, EVENTFLOW_DB, HTFT_LABELS, fnum, read_csv, snum
from eventflow_source_common import prematch_eligibility
from eventflow_v32_gates import competition_context_for

from scenario_htft_semantics import (

    CHAOS_SCENARIO_IDS,

    SCENARIO_HTFT_SEMANTICS,

    UPSET_HTFT_IF_AWAY_FAV,

    UPSET_HTFT_IF_HOME_FAV,

    favorite_underdog,

    perspective_basis_text,

    semantic_to_htft_label,

)



MAPPING_PATH = DB / "competition" / "wc2026_match_id_mapping.csv"



EARLY_SCENARIO_IDS = {
    "S01_favorite_early_break_open", "S02_low_block_survival", "S03_wide_overload_crossfire",
    "S04_press_trap_turnover_goal", "S06_set_piece_breakthrough", "S10_tactical_stalemate_mutual_constraint",
    "S11_group_state_draw_control", "S12_rotation_tempo_drop", "S13_must_win_early_aggression",
    "S14_buildup_gk_error_chain", "S17_group_top_spot_controlled_win",
}

LATE_SCENARIO_IDS = {
    "S07_late_chase_open_game", "S08_strict_ref_card_penalty_chaos", "S09_fatigue_travel_second_half_drop",
    "S01_favorite_early_break_open", "S05_high_line_vs_runner",
    "S11_group_state_draw_control", "S15_weather_travel_pitch_adaptation", "S16_var_penalty_momentum_swing",
}


FAV_WIN_DRAW_DRAW_SUPPRESS = 0.70


def _poisson_pmf(lam: float, k: int) -> float:
    lam = max(0.05, lam)
    return math.exp(-lam) * lam**k / math.factorial(k)


def favorite_win_probability(lam_home: float, lam_away: float, favorite: str, home: str) -> float:
    fav_is_home = favorite == home
    p_win = 0.0
    for i in range(8):
        for j in range(8):
            p = _poisson_pmf(lam_home, i) * _poisson_pmf(lam_away, j)
            if fav_is_home and i > j:
                p_win += p
            elif not fav_is_home and j > i:
                p_win += p
    return p_win


def draw_draw_suppression_factor(match_id: str, fav_win_p: float) -> float:
    """When favorite win >70%, dampen 平/平 unless A-grade stalemate/low-block evidence."""
    if fav_win_p <= FAV_WIN_DRAW_DRAW_SUPPRESS:
        return 1.0
    has_s10_a = has_s02_a = False
    for row in read_csv(EVENTFLOW_DB / "eventflow_fused_evidence.csv"):
        if snum(row, "match_id") != match_id or snum(row, "evidence_grade") != "A":
            continue
        sig = snum(row, "signal_type")
        sid = snum(row, "scenario_id")
        if sid == "S10_tactical_stalemate_mutual_constraint" and sig in {"tactical_mutual_lock", "formation_actual"}:
            has_s10_a = True
        if sid == "S02_low_block_survival" and sig == "low_block_success":
            has_s02_a = True
    if has_s10_a:
        return 0.65
    if has_s02_a:
        return 0.38
    return 0.15


def draw_draw_a_evidence(match_id: str) -> bool:
    return draw_draw_suppression_factor(match_id, 1.0) >= 0.65





def load_match_mapping() -> List[Dict[str, str]]:

    return read_csv(MAPPING_PATH)





def resolve_match_id(match_id: str = "", home: str = "", away: str = "", fifa_id: str = "") -> Dict[str, str]:

    rows = load_match_mapping()

    if match_id:

        for r in rows:

            if snum(r, "internal_match_id") == match_id or snum(r, "fifa_match_id") == match_id:

                return r

    if fifa_id:

        for r in rows:

            if snum(r, "fifa_match_id") == fifa_id:

                return r

    if home and away:

        for r in rows:

            if snum(r, "home_team") == home and snum(r, "away_team") == away:

                return r

    return {

        "internal_match_id": match_id or "",

        "fifa_match_id": fifa_id or "",

        "home_team": home,

        "away_team": away,

        "kickoff_time": "",

    }





def resolve_source_notes_path(match_id: str, fallback: str = "database/eventflow/raw_sources/source_notes.csv") -> str:

    per_match = Path(f"database/eventflow/raw_sources/source_notes/{match_id}.csv")

    if per_match.exists():

        return str(per_match)

    return fallback





def _half_poisson_pmf(lam: float, max_g: int = 4) -> List[float]:

    import math

    lam = max(0.05, lam)

    vals = [math.exp(-lam) * lam**k / math.factorial(k) for k in range(max_g)]

    return vals + [max(0.0, 1.0 - sum(vals))]





def poisson_htft_prior(lam_home: float, lam_away: float, ht_share: float = 0.42) -> Dict[str, float]:

    lh, la = lam_home * ht_share, lam_away * ht_share

    ph, pa = _half_poisson_pmf(lh), _half_poisson_pmf(la)

    fh, fa = _half_poisson_pmf(lam_home * (1 - ht_share)), _half_poisson_pmf(lam_away * (1 - ht_share))



    def res(i: int, j: int) -> str:

        if i > j:

            return "胜"

        if i < j:

            return "负"

        return "平"



    out: Dict[str, float] = defaultdict(float)

    for hi, ph_i in enumerate(ph):

        for ai, pa_i in enumerate(pa):

            ht = res(hi, ai)

            p_ht = ph_i * pa_i

            for fi, pf_i in enumerate(fh):

                for fj, pf_j in enumerate(fa):

                    ft = res(hi + fi, ai + fj)

                    out[f"{ht}/{ft}"] += p_ht * pf_i * pf_j

    return dict(out)





def _scenario_weight(s: Dict[str, str]) -> float:

    return (
        fnum(s, "scenario_ranking_weight")
        or fnum(s, "normalized_weight")
        or fnum(s, "final_weight_deprecated")
        or fnum(s, "final_weight")
        or fnum(s, "weight")
    )





def _chaos_boost(all_scenarios: List[Dict[str, str]]) -> float:

    return sum(_scenario_weight(s) for s in all_scenarios if snum(s, "scenario_id") in CHAOS_SCENARIO_IDS)





def _is_blocked_upset(

    label: str, fav_is_home: bool, clear_imbalance: bool, chaos_boost: float, high_evidence: bool,

) -> bool:

    if not clear_imbalance:

        return False

    upset_set = UPSET_HTFT_IF_HOME_FAV if fav_is_home else UPSET_HTFT_IF_AWAY_FAV

    if label not in upset_set:

        return False

    if chaos_boost >= 0.12 or high_evidence:

        return False

    return True





def _scenario_semantics(s: Dict[str, str]) -> List[tuple[str, str, float]]:

    sid = snum(s, "scenario_id")

    raw = snum(s, "htft_bias_semantic")

    if raw:

        out = []

        for part in raw.split(";"):

            if "|" not in part:

                continue

            ht_r, ft_r = part.split("|", 1)

            out.append((ht_r.strip(), ft_r.strip(), 1.0))

        if out:

            return out

    return SCENARIO_HTFT_SEMANTICS.get(sid, [])





def compute_htft_top3(

    all_scenarios: List[Dict[str, str]],

    phase_sim: Dict[str, Any],

    lam_home: float,

    lam_away: float,

    home: str = "",

    away: str = "",

    high_confidence_evidence: bool = False,

    match_id: str = "",

    top_n: int = 3,

) -> List[Dict[str, Any]]:

    favorite, underdog, clear_imb = favorite_underdog(lam_home, lam_away, home, away)

    fav_is_home = favorite == home

    chaos_boost = _chaos_boost(all_scenarios)



    scores: Dict[str, float] = defaultdict(float)

    supporters: Dict[str, List[str]] = defaultdict(list)

    bases: Dict[str, str] = {}

    semantic_trace: Dict[str, List[str]] = defaultdict(list)



    prior = poisson_htft_prior(lam_home, lam_away)

    for label, p in prior.items():

        if not _is_blocked_upset(label, fav_is_home, clear_imb, chaos_boost, high_confidence_evidence):

            scores[label] += p * 0.20



    early_w = fnum(phase_sim.get("phase_0_30", {}), "scenario_weight", 0.33)

    late_w = fnum(phase_sim.get("phase_61_90", {}), "scenario_weight", 0.33)



    for s in all_scenarios:

        sid = snum(s, "scenario_id")

        w = _scenario_weight(s)

        name = snum(s, "scenario_name")

        phase_mult = 1.0

        if sid in EARLY_SCENARIO_IDS:

            phase_mult += early_w * 0.35

        if sid in LATE_SCENARIO_IDS:

            phase_mult += late_w * 0.35



        for ht_role, ft_role, sem_w in _scenario_semantics(s):

            label = semantic_to_htft_label(ht_role, ft_role, home, away, favorite)

            if label not in HTFT_LABELS:

                continue

            if _is_blocked_upset(label, fav_is_home, clear_imb, chaos_boost, high_confidence_evidence):

                if sid not in CHAOS_SCENARIO_IDS:

                    continue

            contrib = w * sem_w * phase_mult

            scores[label] += contrib

            if sid not in supporters[label]:

                supporters[label].append(sid)

            bases[label] = perspective_basis_text(ht_role, ft_role, favorite, home, away)

            semantic_trace[label].append(f"{name}({contrib:.3f})")

    fav_win_p = favorite_win_probability(lam_home, lam_away, favorite, home)
    if "平/平" in scores:
        scores["平/平"] *= draw_draw_suppression_factor(match_id, fav_win_p)



    ranked = sorted(scores.items(), key=lambda x: -x[1])

    filtered = [(lb, sc) for lb, sc in ranked if sc > 1e-9][: max(top_n, 10)]

    if len(filtered) < top_n:

        for lb in HTFT_LABELS:

            if lb not in scores and not _is_blocked_upset(lb, fav_is_home, clear_imb, chaos_boost, high_confidence_evidence):

                filtered.append((lb, 0.001))

            if len(filtered) >= top_n:

                break

    top = filtered[:top_n]

    total = sum(v for _, v in top) or 1.0

    top_labels = {lb for lb, _ in top}



    out: List[Dict[str, Any]] = []

    for label, raw in top:

        blocked_alts = [

            (lb, sc) for lb, sc in ranked

            if lb not in top_labels and _is_blocked_upset(lb, fav_is_home, clear_imb, chaos_boost, high_confidence_evidence)

        ]

        why_not = []

        if blocked_alts:

            why_not.append(f"强弱悬殊过滤：{','.join(lb for lb, _ in blocked_alts[:3])}需S08/S07或高置信证据")

        for alt_lb, _ in ranked:

            if alt_lb not in top_labels and alt_lb != label and len(why_not) < 3:

                why_not.append(f"{alt_lb}权重较低({scores.get(alt_lb, 0):.3f})")

        out.append({

            "label": label,

            "score": round(raw / total, 4),

            "perspective_basis": bases.get(label, f"强队={favorite}；弱队={underdog}；clear_imbalance={clear_imb}"),

            "supporting_scenarios": supporters.get(label, [])[:4],

            "why_not_others": "；".join(why_not[:3]) or "其余组合语义权重或Poisson先验更低",

            "explanation": f"支撑剧本：{'；'.join(semantic_trace.get(label, [])[:2])}",

        })

    return out





def _competition_strategy_block(match_id: str) -> Dict[str, str]:
    ctx = competition_context_for(match_id) if match_id else {}
    if not ctx:
        return {
            "early_phase": "tactical baseline",
            "middle_phase": "tactical baseline",
            "late_if_level": "standard late-game risk",
            "late_if_trailing": "trailing side may increase chase risk",
        }
    mutual = fnum(ctx, "mutual_draw_acceptance")
    max_cw = max(fnum(ctx, "home_controlled_win_incentive"), fnum(ctx, "away_controlled_win_incentive"))
    max_mw = max(fnum(ctx, "home_must_win_pressure"), fnum(ctx, "away_must_win_pressure"))
    home = snum(ctx, "home")
    is_host = home in {"USA", "Mexico", "Canada"}
    early = "favorite/host controlled initiative" if max_cw > 0.35 or is_host else "balanced opening"
    middle = "balanced risk; draw still acceptable" if mutual >= 0.5 else "competitive middle phase"
    late_level = "risk-downshift / draw-control increases" if mutual >= 0.5 else "standard tempo"
    late_trail = "only trailing side increases chase risk" if max_mw < 0.5 else "must-win side increases chase risk"
    return {
        "early_phase": early,
        "middle_phase": middle,
        "late_if_level": late_level,
        "late_if_trailing": late_trail,
    }





def enrich_phase_simulation(
    activated: List[Dict[str, Any]],
    all_scenarios: List[Dict[str, str]],
    match_id: str = "",
) -> Dict[str, Any]:

    early_pool = [s for s in all_scenarios if snum(s, "scenario_id") in EARLY_SCENARIO_IDS]

    late_pool = [s for s in all_scenarios if snum(s, "scenario_id") in LATE_SCENARIO_IDS]

    early = max(early_pool, key=_scenario_weight, default={})

    mid = activated[1] if len(activated) > 1 else (activated[0] if activated else {})

    late = max(late_pool, key=_scenario_weight, default={})



    def phase_block(label: str, dom: Dict[str, Any], pool: List[Dict[str, str]]) -> Dict[str, Any]:

        if isinstance(dom, dict) and dom.get("scenario_id"):

            sid = dom["scenario_id"]

            name = dom.get("name", "")

            w = fnum(dom, "weight")

        elif isinstance(dom, dict):

            sid = snum(dom, "scenario_id")

            name = snum(dom, "scenario_name")

            w = fnum(dom, "normalized_weight") or fnum(dom, "weight")

        else:

            sid, name, w = "", "", 0.0

        if not sid and pool:

            top = max(pool, key=_scenario_weight)

            sid, name = snum(top, "scenario_id"), snum(top, "scenario_name")

            w = _scenario_weight(top)

        return {

            "label": label,

            "dominant_scenario_id": sid,

            "dominant_scenario_name": name,

            "scenario_weight": round(w, 4),

            "supporting_scenario_ids": [

                snum(s, "scenario_id")

                for s in sorted(pool, key=lambda x: -_scenario_weight(x))[:3]

            ],

            "goal_tendency": "偏高" if w > 0.14 else "中性",

        }



    return {

        "phase_0_30": phase_block("开场0-30", early or {}, early_pool),

        "phase_31_60": phase_block("中段31-60", mid, all_scenarios),

        "phase_61_90": phase_block("末段61-90", late or {}, late_pool),

        "competition_strategy": _competition_strategy_block(match_id),

    }





def summarize_data_quality(match_id: str, home: str, away: str) -> Dict[str, Any]:

    checks: List[Tuple[str, str, str]] = [

        ("player", "database/player_style/processed/player_foot_position_profile.csv", "team"),

        ("player_shift", "database/player_style/processed/player_worldcup_position_shift.csv", "match_id"),

        ("team", "database/team_style/processed/team_tactical_profile.csv", "team"),

        ("matchup", "database/team_style/processed/tactical_matchup_matrix.csv", "match_id"),

        ("source", "database/eventflow/processed/source_signal_events.csv", "match_id"),

    ]

    real, estimated, missing = 0, 0, 0

    details: List[Dict[str, Any]] = []

    root = Path(__file__).resolve().parents[1]

    for kind, rel, key in checks:

        rows = read_csv(root / rel)

        if key == "team":

            matched = [r for r in rows if snum(r, key) in (home, away)]

        else:

            matched = [r for r in rows if not match_id or snum(r, key) == match_id]

        if not matched and key == "match_id":

            matched = [r for r in rows if snum(r, "home") == home and snum(r, "away") == away]

        for r in matched:

            est = str(r.get("is_estimated", "")).lower() in ("true", "1", "yes")

            if est:

                estimated += 1

            else:

                real += 1

            details.append({"layer": kind, "is_estimated": est, "confidence": fnum(r, "confidence", fnum(r, "data_confidence", 0.5))})

        if not matched:

            missing += 1

    total = max(1, real + estimated)
    coverage_score = max(0.0, min(1.0, 1.0 - missing / max(1, len(checks))))
    authenticity_score = max(0.0, min(1.0, real / total))

    claim_rows = [
        r for r in read_csv(root / "database/eventflow/processed/source_signal_claims.csv")
        if not match_id or snum(r, "match_id") == match_id
    ]
    conflict_count = sum(int(fnum(r, "conflict_count")) for r in claim_rows)
    consistency_score = max(0.0, min(1.0, 1.0 - conflict_count / max(1, len(claim_rows) + conflict_count)))

    freshness_values = []
    for d in details:
        # Most processed tables in this project are regenerated snapshots and may not
        # carry source timestamps. Keep freshness separate from authenticity instead
        # of calling real rows "complete".
        freshness_values.append(float(d.get("confidence", 0.5) or 0.5))
    freshness_score = max(0.0, min(1.0, sum(freshness_values) / len(freshness_values))) if freshness_values else 0.0
    overall = max(0.0, min(1.0, 0.35 * coverage_score + 0.30 * authenticity_score + 0.20 * consistency_score + 0.15 * freshness_score))

    return {

        "real_data_rows": real,

        "estimated_data_rows": estimated,

        "missing_layers": missing,

        "real_data_ratio": round(real / total, 3),

        "estimated_data_ratio": round(estimated / total, 3),

        "authenticity_score": round(authenticity_score, 3),

        "coverage_score": round(coverage_score, 3),

        "freshness_score": round(freshness_score, 3),

        "consistency_score": round(consistency_score, 3),

        "overall_data_reliability": round(overall, 3),

        "conflict_count": conflict_count,

        "data_quality_status": "完整" if overall >= 0.75 else ("一般" if overall >= 0.45 else "不足"),

        "note": "真实性、覆盖率、时效性和一致性已分列；已有真实数据不等于字段完整",

        "details": details[:12],

    }





def halftime_layer_status(
    data_quality: Dict[str, Any],
    dynamic_profile: Dict[str, Any] | None = None,
    eventflow_degraded: bool = False,
    htft_top3: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Audit gate for HT/FT outputs.

    V3.8 treats halftime and half/full-time as a separate low-confidence
    experimental layer. This helper never upgrades HT/FT to robust betting use
    without an explicit future calibration flag.
    """
    dynamic_profile = dynamic_profile or {}
    htft_top3 = htft_top3 or []
    coverage = fnum(data_quality, "coverage_score", fnum(data_quality, "real_data_ratio", 0.0))
    consistency = fnum(data_quality, "consistency_score", 1.0)
    reliability = fnum(dynamic_profile, "reliability_score", 0.0)
    enough_for_reference = bool(htft_top3) and not eventflow_degraded and coverage >= 0.35
    confidence = "low"
    if enough_for_reference and coverage >= 0.80 and consistency >= 0.80 and reliability >= 0.70:
        # Still a reference layer until independent time-out calibration is complete.
        confidence = "medium_reference_only"
    return {
        "halftime_confidence": confidence,
        "halftime_calibration_status": "not_independently_calibrated",
        "halftime_data_coverage": round(coverage, 3),
        "halftime_consistency": round(consistency, 3),
        "halftime_output_allowed": enough_for_reference,
        "halftime_betting_eligible": False,
        "label": "低置信度参考" if enough_for_reference else "不输出或仅内部审计",
        "sensitive_factors": ["早球", "点球", "红牌", "临场换人", "伤退", "天气/中断"],
        "reason": "半场样本短且两段泊松/EventFlow半场分布尚未完成独立时间外校准",
    }


def count_prematch_evidence(match_id: str) -> Dict[str, int]:

    root = Path(__file__).resolve().parents[1]

    events = [r for r in read_csv(root / "database/eventflow/processed/source_signal_events.csv") if snum(r, "match_id") == match_id]

    pre, post, excl = 0, 0, 0

    for e in events:

        elig = prematch_eligibility(e)

        partition = elig.get("evidence_partition", "excluded_non_prematch")

        if partition == "eligible_prematch":

            pre += 1

        elif partition == "prematch_summary_only":

            pre += 1

        else:

            post += 1

            excl += 1

    return {

        "pre_match_evidence_count": pre,

        "post_match_evidence_count": post,

        "excluded_post_match_evidence_count": excl,

    }


def eventflow_json_matches(ev_json: dict, mid: str, home: str, away: str) -> bool:
    """True when eventflow_output.json belongs to the requested match."""
    if snum(ev_json, "match_id") and snum(ev_json, "match_id") != mid:
        return False
    expected = f"{home} vs {away}".strip()
    em = snum(ev_json, "match")
    if em and expected and em != expected:
        return False
    return True


def htft_teams_bound(htft: list[dict], home: str, away: str) -> bool:
    """Ensure half_full_time_top3 perspective_basis only references this match's teams."""
    allowed = {home, away}
    for item in htft or []:
        basis = item.get("perspective_basis", "")
        for marker in ("强队=", "弱队="):
            if marker not in basis:
                continue
            token = basis.split(marker, 1)[1].split("；")[0].split("(")[0].strip()
            if token and token not in allowed:
                return False
    return True


def recompute_htft_top3(
    mid: str,
    home: str,
    away: str,
    lam_home: float,
    lam_away: float,
) -> tuple[list[dict], str]:
    from predict_eventflow import (
        build_activated_payload,
        pick_activated,
        scenario_rows,
    )

    all_scenarios, baseline_degraded, fallback_ratio = scenario_rows(mid, home, away)
    if baseline_degraded or fallback_ratio >= 0.50:
        return [], "empty_degraded"
    activated_raw = pick_activated(all_scenarios)
    if not activated_raw:
        return [], "empty_no_activation"
    activated = build_activated_payload(activated_raw, favorite_is_home=lam_home >= lam_away)
    phase_sim = enrich_phase_simulation(activated, all_scenarios, mid)
    evidence = count_prematch_evidence(mid)
    high_conf = evidence.get("pre_match_evidence_count", 0) >= 2
    htft = compute_htft_top3(
        all_scenarios,
        phase_sim,
        lam_home,
        lam_away,
        home=home,
        away=away,
        high_confidence_evidence=high_conf,
        match_id=mid,
        top_n=3,
    )
    return htft, "recomputed"


def resolve_eventflow_merge_attachments(
    ev_json: dict,
    mid: str,
    home: str,
    away: str,
    lam_home: float,
    lam_away: float,
) -> dict:
    """Bind EventFlow merge fields to current match; recompute HT/FT when JSON is stale."""
    ef_engine = ev_json.get("eventflow_engine", {}) or {}
    aligned = eventflow_json_matches(ev_json, mid, home, away)
    htft = ef_engine.get("half_full_time_top3", [])
    htft_source = "eventflow_json"

    if not aligned or not htft_teams_bound(htft, home, away):
        htft, htft_source = recompute_htft_top3(mid, home, away, lam_home, lam_away)

    activated = ef_engine.get("activated_scenarios", [])
    phase_sim = ef_engine.get("phase_simulation", {})
    comp_ctx = ef_engine.get("competition_context", {})
    all_weights = ef_engine.get("all_scenario_weights", [])

    if not aligned:
        from predict_eventflow import (
            build_activated_payload,
            competition_context_for,
            pick_activated,
            scenario_rows,
        )

        all_scenarios, baseline_degraded, fallback_ratio = scenario_rows(mid, home, away)
        if not baseline_degraded and fallback_ratio < 0.50:
            activated_raw = pick_activated(all_scenarios)
            activated = build_activated_payload(activated_raw, favorite_is_home=lam_home >= lam_away)
            phase_sim = enrich_phase_simulation(activated, all_scenarios, mid) if activated else {}
            all_weights = [
                {
                    "scenario_id": snum(s, "scenario_id"),
                    "name": snum(s, "scenario_name"),
                    "weight_composition": {
                        "raw_total_score": float(s.get("weight", 0) or 0),
                    },
                }
                for s in sorted(all_scenarios, key=lambda r: float(r.get("weight", 0) or 0), reverse=True)
            ]
        else:
            activated = []
            phase_sim = {}
            all_weights = []
        comp_ctx = competition_context_for(mid) if mid else {}

    return {
        "half_full_time_top3": htft,
        "half_full_time_source": htft_source,
        "activated_scenarios": activated,
        "phase_simulation": phase_sim,
        "competition_context": comp_ctx,
        "all_scenario_weights": all_weights,
        "eventflow_json_aligned": aligned,
    }


def validate_htft_output(payload: dict, forbidden_teams: list[str] | None = None) -> list[str]:
    """Return validation errors for half_full_time binding (empty = pass)."""
    home, away = "", ""
    match_line = snum(payload, "match")
    if " vs " in match_line:
        home, away = [x.strip() for x in match_line.split(" vs ", 1)]
    errors: list[str] = []
    forbidden = forbidden_teams or []
    for section in ("eventflow_engine", "final_fusion"):
        block = payload.get(section, {}) or {}
        htft = block.get("half_full_time_top3", [])
        if not htft_teams_bound(htft, home, away):
            errors.append(f"{section}.half_full_time_top3 references foreign teams")
        for item in htft:
            basis = item.get("perspective_basis", "")
            for team in forbidden:
                if team in basis:
                    errors.append(f"{section}.half_full_time_top3 contains forbidden team {team}")
    return errors

