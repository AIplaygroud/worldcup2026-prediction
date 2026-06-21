#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.7-P2 apply large-score tail audit / re-ranking to dual-engine fusion output."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from eventflow_common import read_json, write_csv
from v37_common import FEATURE_TABLES, V37_AUDIT, V37_TAIL_THRESHOLDS, ensure_v37_dirs
from v37_large_score_tail import TAIL_FEATURE_FIELDS, apply_tail_to_payload


def _parse_bool(s: str) -> bool:
    return str(s).strip().lower() in ("true", "1", "yes")


def main() -> None:
    ap = argparse.ArgumentParser(description="V3.7-P2 large-score tail layer")
    ap.add_argument("--input", required=True, help="dual_engine_output JSON path")
    ap.add_argument("--output", default="", help="Output JSON (required for rerank_only)")
    ap.add_argument("--mode", default="audit_only", choices=("audit_only", "rerank_only"))
    ap.add_argument("--max-tail-boost", type=float, default=V37_TAIL_THRESHOLDS["max_tail_boost_default"])
    ap.add_argument("--min-data-quality", type=float, default=V37_TAIL_THRESHOLDS["min_data_quality"])
    ap.add_argument(
        "--disable-on-cold-guard",
        default="true",
        help="Suppress tail boost when cold_guard_active (default true)",
    )
    ap.add_argument(
        "--disable-on-must-win-no-convert",
        default="true",
        help="Suppress tail boost when favorite must_win_no_convert (default true)",
    )
    ap.add_argument("--write-features", action="store_true", help="Append row to large_score_tail_features.csv")
    args = ap.parse_args()

    ensure_v37_dirs()
    payload = read_json(args.input, {})
    if not payload:
        raise SystemExit(f"Empty or missing input: {args.input}")

    result = apply_tail_to_payload(
        payload,
        mode=args.mode,
        max_tail_boost=args.max_tail_boost,
        min_data_quality=args.min_data_quality,
        disable_on_cold_guard=_parse_bool(args.disable_on_cold_guard),
        disable_on_must_win_no_convert=_parse_bool(args.disable_on_must_win_no_convert),
    )

    match_id = result["audit"]["match_id"]
    audit_path = V37_AUDIT / f"large_score_tail_audit_{match_id}.json"
    audit_path.write_text(json.dumps(result["audit"], ensure_ascii=False, indent=2), encoding="utf-8")

    if args.write_features:
        feat_path = FEATURE_TABLES["large_score_tail"]
        existing = []
        if feat_path.exists():
            from eventflow_common import read_csv
            existing = [r for r in read_csv(feat_path) if r.get("match_id") != match_id]
        existing.append(result["feature_row"])
        write_csv(feat_path, existing, TAIL_FEATURE_FIELDS)

    if args.mode == "rerank_only":
        if not args.output:
            raise SystemExit("--output required when --mode rerank_only")
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_payload = result["payload"]
        out_payload["v37_p2_tail_applied_at"] = datetime.now(timezone.utc).isoformat()
        cal_path = V37_AUDIT / "v37_p4_tail_calibration_report.json"
        rerank_allowed = False
        if cal_path.exists():
            cal = json.loads(cal_path.read_text(encoding="utf-8"))
            rerank_allowed = bool(cal.get("rerank_only_allowed"))
        out_payload["tail_pilot"] = "_tail_pilot" in out_path.name
        out_payload["rerank_only_allowed_by_calibration"] = rerank_allowed
        out_payload["no_lambda_mutation"] = True
        out_payload["no_v2_probability_mutation"] = True
        out_payload["no_adjusted_probability_mutation"] = True
        out_payload["no_auto_betting"] = True
        out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"P2 rerank -> {out_path}")

    level = result["audit"]["v37_large_score_tail"]["tail_boost_level"]
    print(f"P2 tail audit -> {audit_path}")
    print(f"  match_id={match_id} mode={args.mode} level={level}")
    print(f"  no_lambda_mutation={result['audit']['no_lambda_mutation']}")
    print(f"  boosted={result['audit']['v37_large_score_tail']['boosted_scores']}")


if __name__ == "__main__":
    main()
