#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run V3.6 dual-engine pipeline for R2 review matches and emit v36 JSON outputs."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PROCESSED = ROOT / "database" / "eventflow" / "processed"

R2_MATCHES = [
    ("WC2026-D32", "USA", "Australia", "dual_engine_output_D32_USA_AUS_balanced_v36.json"),
    ("WC2026-C29", "Brazil", "Haiti", "dual_engine_output_C29_BRA_HTI_balanced_v36.json"),
    ("WC2026-C30", "Scotland", "Morocco", "dual_engine_output_C30_SCO_MAR_balanced_v36.json"),
    ("WC2026-D31", "Turkey", "Paraguay", "dual_engine_output_D31_TUR_PAR_balanced_v36.json"),
]


def verify_json(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing {path.name}"]
    data = json.loads(path.read_text(encoding="utf-8"))
    pe = data.get("probability_engine", {})
    fusion = data.get("final_fusion", {}).get("fusion_input", {})
    prob_from = pe.get("probabilities_from")
    if prob_from != "v36_realized":
        errors.append(f"{path.name}: probabilities_from={prob_from}")
    if fusion.get("probability_source") != "v36_realized":
        errors.append(f"{path.name}: fusion probability_source != v36_realized")
    if not fusion.get("v36_realization_applied"):
        errors.append(f"{path.name}: v36_realization_applied not true")
    if not pe.get("scoreline_probability_grid"):
        errors.append(f"{path.name}: empty scoreline_probability_grid")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch run V3.6 R2 matches")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--match-id", default="", help="Run single match only")
    args = ap.parse_args()

    py = sys.executable
    pipeline = SCRIPTS / "run_dual_engine_pipeline.py"
    all_errors: list[str] = []

    for mid, home, away, out_name in R2_MATCHES:
        if args.match_id and mid != args.match_id:
            continue
        out = PROCESSED / out_name
        cmd = [
            py, str(pipeline),
            "--match-id", mid, "--home", home, "--away", away,
            "--mode", "auto",
            "--use-v36-realization", "true",
            "--export-json", str(out.relative_to(ROOT)).replace("\\", "/"),
        ]
        if args.skip_build:
            cmd.append("--skip-build")
        print(f"\n=== {mid} {home} vs {away} ===")
        subprocess.run(cmd, cwd=str(ROOT), check=True)
        all_errors.extend(verify_json(out))
        if out.exists():
            sys.path.insert(0, str(SCRIPTS))
            from scenario_realization_common import sync_v36_diagnostics_from_merge_json
            sync_v36_diagnostics_from_merge_json(out)

    val = subprocess.run(
        [py, str(SCRIPTS / "validate_v36_realization_calibration.py")],
        cwd=str(ROOT),
    )
    if val.returncode != 0:
        all_errors.append("unit validation failed")

    if all_errors:
        print("\nR2 batch verification FAILED:")
        for e in all_errors:
            print(f"  - {e}")
        raise SystemExit(1)
    print("\nR2 batch complete — all v36 JSON outputs verified.")


if __name__ == "__main__":
    main()
