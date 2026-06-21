#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Candidate pool coverage audit for historical large scores."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from eventflow_common import read_csv, write_csv
from v37_common import BACKTEST_TABLES, DIAGNOSTICS_TABLES, ensure_v37_dirs
from v37_tail_diagnostics_common import COVERAGE_FIELDS, covered_by_tail_pool, recommended_bucket


def analyze(backtest_path: Path) -> list[dict[str, str]]:
    counts: Counter[str] = Counter()
    for bt in read_csv(backtest_path):
        if bt.get("is_large_score") != "true":
            continue
        counts[bt.get("actual_scoreline", "")] += 1

    rows: list[dict[str, str]] = []
    for scoreline, count in sorted(counts.items()):
        covered = covered_by_tail_pool(scoreline)
        bucket = recommended_bucket(scoreline)
        notes = ""
        if not covered and bucket == "extreme_tail_warning":
            notes = "extreme tail — audit warning only, not boostable to Top5"
        elif not covered:
            notes = "not in legacy pool — consider bucket extension"
        rows.append({
            "actual_scoreline": scoreline,
            "count": str(count),
            "covered_by_current_tail_pool": str(covered).lower(),
            "recommended_bucket": bucket,
            "notes": notes,
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Tail candidate coverage audit")
    ap.add_argument("--backtest", default=str(BACKTEST_TABLES["results"]))
    ap.add_argument("--output", default=str(DIAGNOSTICS_TABLES["candidate_coverage"]))
    args = ap.parse_args()
    ensure_v37_dirs()
    rows = analyze(Path(args.backtest))
    write_csv(Path(args.output), rows, COVERAGE_FIELDS)
    large_total = sum(int(r["count"]) for r in rows)
    covered = sum(int(r["count"]) for r in rows if r["covered_by_current_tail_pool"] == "true")
    rate = round(covered / max(large_total, 1), 4)
    print(f"Wrote {len(rows)} coverage rows; pool coverage rate={rate} -> {args.output}")


if __name__ == "__main__":
    main()
