#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate V3.7-P2 large-score tail rules for regression matches."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eventflow_common import read_json
from v37_large_score_tail import apply_tail_to_payload

REGRESSION = {
    "WC2026-E34": {
        "expect_no_boost": True,
        "expect_blockers": {"cold_guard_active", "must_win_no_convert_favorite"},
    },
    "WC2026-F35": {
        "expect_no_lambda_mutation": True,
    },
    "WC2026-F36": {
        "expect_no_lambda_mutation": True,
        "audit_only_if_degraded": True,
    },
}

DEFAULT_FIXTURES = {
    "WC2026-E34": "dual_engine_output_E34_v37_test.json",
    "WC2026-F35": "dual_engine_output_F35_v37_test.json",
    "WC2026-F36": "dual_engine_output_F36_v37_test.json",
}


def validate_match(
    match_id: str,
    payload: dict,
    *,
    mode: str = "audit_only",
) -> list[str]:
    errors: list[str] = []
    spec = REGRESSION.get(match_id, {})
    audit_result = apply_tail_to_payload(payload, mode=mode)
    audit = audit_result["audit"]
    tail = audit["v37_large_score_tail"]

    if not audit.get("no_lambda_mutation"):
        errors.append(f"{match_id}: lambda mutation detected")

    prob = payload.get("probability_engine", {})
    out_prob = audit_result["payload"].get("probability_engine", {})
    for key in ("lambda_home", "lambda_away", "adjusted_probability", "adjusted_lambda"):
        if key in prob and prob.get(key) != out_prob.get(key):
            errors.append(f"{match_id}: probability_engine.{key} mutated")

    if spec.get("expect_no_boost"):
        if tail.get("boosted_scores"):
            errors.append(f"{match_id}: unexpected tail boost {tail['boosted_scores']}")
        if tail.get("tail_boost_level") not in ("none", ""):
            blockers = set(audit.get("evaluation", {}).get("block_reasons", []))
            if not blockers:
                errors.append(f"{match_id}: expected no boost but level={tail.get('tail_boost_level')}")

    if spec.get("audit_only_if_degraded") and payload.get("eventflow_data_degraded"):
        rerank = apply_tail_to_payload(payload, mode="rerank_only")
        if rerank["audit"]["v37_large_score_tail"]["boosted_scores"]:
            errors.append(f"{match_id}: degraded EventFlow should not default rerank boost")

    if mode == "rerank_only" and spec.get("expect_no_boost"):
        if tail.get("boosted_scores"):
            errors.append(f"{match_id}: rerank boosted despite guards")

    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate V3.7-P2 tail layer")
    ap.add_argument("--match-id", default="", help="e.g. WC2026-E34")
    ap.add_argument("--json", default="", help="Override dual_engine JSON path")
    ap.add_argument("--mode", default="audit_only", choices=("audit_only", "rerank_only"))
    ap.add_argument("--all-regression", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    proc = root / "database" / "eventflow" / "processed"

    targets: list[tuple[str, Path]] = []
    if args.all_regression:
        for mid, fname in DEFAULT_FIXTURES.items():
            targets.append((mid, proc / fname))
    elif args.match_id:
        fname = DEFAULT_FIXTURES.get(args.match_id, "")
        path = Path(args.json) if args.json else (proc / fname if fname else Path(""))
        if not path or not path.exists():
            raise SystemExit(f"Fixture not found for {args.match_id}")
        targets.append((args.match_id, path))
    else:
        raise SystemExit("Provide --match-id or --all-regression")

    all_errors: list[str] = []
    for mid, path in targets:
        payload = read_json(path, {})
        payload["match_id"] = mid
        all_errors.extend(validate_match(mid, payload, mode=args.mode))

    report = {"ok": len(all_errors) == 0, "errors": all_errors, "checked": [t[0] for t in targets]}
    print(json.dumps(report, indent=2))
    if all_errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
