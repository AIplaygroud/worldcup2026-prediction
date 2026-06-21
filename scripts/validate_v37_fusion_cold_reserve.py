#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate V3.7 cold reserve in fusion output."""
from __future__ import annotations

import argparse
import json
import sys

from eventflow_common import read_json
from scenario_realization_common import load_v37_features


def validate_cold_reserve(payload: dict) -> list[str]:
    errors: list[str] = []
    mid = payload.get("match_id", "")
    v37 = load_v37_features(mid)
    fusion = payload.get("final_fusion", {})
    reserves = fusion.get("risk_reserve_scorelines", [])
    if not v37.get("cold_guard_active"):
        if reserves:
            errors.append(f"{mid}: cold_guard inactive but risk_reserve present")
        return errors
    if not reserves:
        errors.append(f"{mid}: cold_guard_active but no risk_reserve_scorelines")
        return errors
    scores = [r.get("score") for r in reserves]
    if not any(s in ("0-0", "1-1") for s in scores):
        errors.append(f"{mid}: cold reserve missing 0-0 or 1-1, got {scores}")
    top3 = [r.get("score") for r in fusion.get("score_ranking", [])[:3]]
    for r in reserves:
        if r.get("score") in top3:
            errors.append(f"{mid}: reserve {r.get('score')} duplicates fusion top3")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--match-id", default="")
    args = ap.parse_args()
    payload = read_json(args.json, {})
    if args.match_id:
        payload["match_id"] = args.match_id
    errors = validate_cold_reserve(payload)
    print(json.dumps({"errors": errors, "ok": len(errors) == 0}, indent=2))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
