#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression check for EventFlow V3.2 S11–S16 calibrated weights."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "database/eventflow/processed/dual_engine_output_C29_balanced_v32.json",
    ROOT / "database/eventflow/processed/dual_engine_output_C30_balanced_v32.json",
    ROOT / "database/eventflow/processed/dual_engine_output_D31_balanced_v32.json",
    ROOT / "database/eventflow/processed/dual_engine_output_D32_USA_AUS_balanced_v32_calibrated.json",
]
NEW_SIDS = ("S11", "S12", "S13", "S14", "S15", "S16")
ANOMALIES: list[str] = []


def check_file(path: Path) -> None:
    if not path.exists():
        print("MISSING:", path)
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    engine = data.get("eventflow_engine") or data.get("eventflow", {}).get("eventflow_engine", {})
    weights = engine.get("all_scenario_weights", [])
    activated = {a.get("scenario_id", "") for a in engine.get("activated_scenarios", [])}

    print("\n===", path.name, "===")
    print("match:", data.get("match_id"), data.get("match", ""))
    print("activated:", sorted(activated))

    for w in weights:
        sid = w.get("scenario_id", "")
        if not sid.startswith(NEW_SIDS):
            continue
        comp = w.get("weight_composition", {})
        tac = comp.get("raw_tactical_delta", 0) or 0
        src = comp.get("raw_source_delta", 0) or 0
        prob = comp.get("raw_probability_context_delta", 0) or 0
        norm = comp.get("normalized_weight", 0) or 0
        gates = comp.get("gates", {})
        print(
            f"  {sid}",
            f"base={comp.get('raw_base_weight')}",
            f"tac={tac}",
            f"src={src}",
            f"prob={prob}",
            f"total={comp.get('raw_total_score')}",
            f"norm={norm:.4f}",
            f"activated={sid in activated}",
            f"gates={gates}",
        )
        if sid == "S13_must_win_early_aggression" and tac == 0 and src == 0 and prob > 0.08:
            ANOMALIES.append(f"{path.name}: S13 prob-only activation prob={prob}")
        if sid == "S14_buildup_gk_error_chain" and tac > 0.3:
            if not gates.get("specific_buildup_evidence") and not gates.get("evidence_refs"):
                ANOMALIES.append(f"{path.name}: S14 high without buildup evidence tac={tac}")
        if sid in (
            "S12_rotation_tempo_drop",
            "S15_weather_travel_pitch_adaptation",
            "S16_var_penalty_momentum_swing",
        ) and sid in activated and tac < 0.02 and src < 0.01:
            ANOMALIES.append(f"{path.name}: {sid} activated on prior only")


def main() -> int:
    seen = set()
    for f in FILES:
        if f in seen or not f.exists():
            continue
        seen.add(f)
        check_file(f)

    if ANOMALIES:
        print("\n=== ANOMALIES ===")
        for a in ANOMALIES:
            print("!", a)
        return 1
    print("\nOK: no anomalies detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
