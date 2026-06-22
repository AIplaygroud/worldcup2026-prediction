#!/usr/bin/env python3
"""Deterministic, audit-friendly EventFlow fusion weighting.

The policy is intentionally rule based. It is not fitted on the latest match
results, so a small batch of outcomes cannot move the coefficients.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping


LEGACY_MODES = {"safe", "balanced", "hit_hunting"}
AUTO_MODE = "auto"
MODE_CHOICES = (AUTO_MODE, *sorted(LEGACY_MODES))


def clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _num(row: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _scenario_weight(row: Mapping[str, Any]) -> float:
    comp = row.get("weight_composition")
    if isinstance(comp, Mapping):
        return _num(comp, "normalized_weight", _num(row, "normalized_weight", _num(row, "weight")))
    return (
        _num(row, "scenario_ranking_weight")
        or _num(row, "normalized_weight")
        or _num(row, "final_weight_deprecated")
        or _num(row, "final_weight")
        or _num(row, "weight")
    )


def _scenario_confidence(row: Mapping[str, Any]) -> float:
    comp = row.get("weight_composition")
    if isinstance(comp, Mapping):
        return _num(row, "data_confidence", 0.55)
    return _num(row, "data_confidence", _num(row, "confidence", 0.55))


def _scenario_concentration(rows: Iterable[Mapping[str, Any]]) -> float:
    weights = sorted((_scenario_weight(r) for r in rows), reverse=True)
    weights = [w for w in weights if w > 0]
    if len(weights) < 2:
        return 0.0
    total = sum(weights)
    probs = [w / total for w in weights]
    entropy = -sum(p * math.log(p) for p in probs)
    entropy_concentration = 1.0 - entropy / math.log(len(probs))
    top3_mass = sum(probs[:3])
    uniform_top3 = min(1.0, 3.0 / len(probs))
    top3_concentration = clip(
        (top3_mass - uniform_top3) / max(1e-9, 1.0 - uniform_top3)
    )
    return clip(0.55 * entropy_concentration + 0.45 * top3_concentration)


def _scenario_specificity(rows: List[Mapping[str, Any]], fallback_ratio: float) -> float:
    if not rows:
        return 0.0
    confidence = sum(_scenario_confidence(r) for r in rows) / len(rows)
    substantive = 0
    for row in rows:
        comp = row.get("weight_composition")
        source = comp if isinstance(comp, Mapping) else row
        non_prior = (
            abs(_num(source, "raw_tactical_delta", _num(source, "tactical_delta")))
            + abs(_num(source, "raw_player_delta", _num(source, "player_delta")))
            + abs(_num(source, "raw_source_delta", _num(source, "source_delta")))
            + abs(_num(source, "raw_probability_context_delta", _num(source, "probability_context_delta")))
        )
        substantive += int(non_prior >= 0.03)
    substantive_ratio = substantive / len(rows)
    return clip(
        0.45 * confidence
        + 0.35 * substantive_ratio
        + 0.20 * (1.0 - clip(fallback_ratio))
    )


def compute_dynamic_fusion_profile(
    *,
    data_quality: Mapping[str, Any],
    source_fusion: Mapping[str, Any],
    scenarios: Iterable[Mapping[str, Any]],
    fallback_ratio: float = 0.0,
    eventflow_degraded: bool = False,
    probability_degraded: bool = False,
    requested_mode: str = AUTO_MODE,
) -> Dict[str, Any]:
    """Return automatic Probability/EventFlow weights and an audit trace."""
    rows = list(scenarios)
    real_rows = _num(data_quality, "real_data_rows")
    estimated_rows = _num(data_quality, "estimated_data_rows")
    missing_layers = _num(data_quality, "missing_layers")
    real_ratio = _num(data_quality, "real_data_ratio")

    row_coverage = clip(real_rows / 12.0)
    layer_coverage = clip(1.0 - missing_layers / 5.0)
    estimate_penalty = clip(estimated_rows / max(1.0, real_rows + estimated_rows))
    data_coverage = clip(
        0.40 * row_coverage
        + 0.35 * layer_coverage
        + 0.25 * real_ratio
        - 0.25 * estimate_penalty
    )

    prematch = _num(source_fusion, "pre_match_evidence_count")
    grade_a = _num(source_fusion, "grade_A_count")
    grade_b = _num(source_fusion, "grade_B_count")
    fused = _num(source_fusion, "fused_evidence_rows")
    conflicts = _num(source_fusion, "conflict_count")
    ab_count = grade_a + grade_b
    evidence_strength = clip(
        0.40 * clip(ab_count / 3.0)
        + 0.25 * clip(prematch / 6.0)
        + 0.20 * clip(fused / 3.0)
        + 0.15 * clip(grade_a / 2.0)
    )
    conflict_ratio = clip(conflicts / max(1.0, prematch + conflicts))

    concentration = _scenario_concentration(rows)
    specificity = _scenario_specificity(rows, fallback_ratio)
    reliability = clip(
        0.30 * data_coverage
        + 0.30 * evidence_strength
        + 0.25 * specificity
        + 0.15 * concentration
        - 0.20 * conflict_ratio
    )

    event_weight = clip(0.06 + 0.30 * reliability, 0.06, 0.35)
    caps: List[str] = []
    if ab_count <= 0:
        event_weight = min(event_weight, 0.20)
        caps.append("no_grade_ab_cap_0.20")
    if fused <= 0:
        event_weight = min(event_weight, 0.18)
        caps.append("no_fused_evidence_cap_0.18")
    if conflict_ratio >= 0.35:
        event_weight = min(event_weight, 0.16)
        caps.append("evidence_conflict_cap_0.16")
    if fallback_ratio >= 0.20:
        event_weight = min(event_weight, 0.14)
        caps.append("fallback_cap_0.14")
    if probability_degraded and evidence_strength < 0.45:
        event_weight = min(event_weight, 0.18)
        caps.append("both_engines_weak_cap_0.18")
    if eventflow_degraded:
        event_weight = 0.0
        caps.append("eventflow_degraded_probability_only")

    event_weight = round(event_weight, 4)
    probability_weight = round(1.0 - event_weight, 4)
    tail_strength = round(clip(0.50 + 0.40 * reliability, 0.50, 0.90), 4)
    active_scenario_limit = 3 if reliability < 0.42 else 4 if reliability < 0.68 else 5

    return {
        "policy": "auto_dynamic_v1",
        "requested_mode": requested_mode,
        "legacy_mode_ignored": requested_mode in LEGACY_MODES,
        "effective_mode": "auto_dynamic",
        "probability_weight": probability_weight,
        "eventflow_weight": event_weight,
        "tail_strength": tail_strength,
        "active_scenario_limit": active_scenario_limit,
        "reliability_score": round(reliability, 4),
        "components": {
            "data_coverage": round(data_coverage, 4),
            "evidence_strength": round(evidence_strength, 4),
            "scenario_specificity": round(specificity, 4),
            "scenario_concentration": round(concentration, 4),
            "conflict_ratio": round(conflict_ratio, 4),
            "fallback_ratio": round(clip(fallback_ratio), 4),
        },
        "evidence_counts": {
            "prematch": int(prematch),
            "grade_a": int(grade_a),
            "grade_b": int(grade_b),
            "fused": int(fused),
            "conflicts": int(conflicts),
        },
        "caps_applied": caps,
        "coefficient_policy": (
            "fixed_rule_not_fitted_on_latest_results; "
            "change only after time-split backtest"
        ),
    }

