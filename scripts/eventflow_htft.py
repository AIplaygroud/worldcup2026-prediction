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
    "S14_buildup_gk_error_chain",
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





def enrich_phase_simulation(activated: List[Dict[str, Any]], all_scenarios: List[Dict[str, str]]) -> Dict[str, Any]:

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

    return {

        "real_data_rows": real,

        "estimated_data_rows": estimated,

        "missing_layers": missing,

        "real_data_ratio": round(real / total, 3),

        "estimated_data_ratio": round(estimated / total, 3),

        "note": "估算数据已降权参与；不可与真实数据同权",

        "details": details[:12],

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


