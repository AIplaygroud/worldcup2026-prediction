#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate attribution analysis for tail layer blocks."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from eventflow_common import read_csv, write_csv
from v37_common import BACKTEST_TABLES, DIAGNOSTICS_TABLES, ensure_v37_dirs
from v37_tail_diagnostics_common import GATE_ATTRIBUTION_FIELDS, gate_from_block_reason, gate_interpretation


def analyze(backtest_path: Path, audit_dir: Path) -> tuple[list[dict[str, str]], dict]:
    gate_stats: dict[str, dict] = defaultdict(lambda: {
        "blocked_count": 0, "blocked_large_score_count": 0, "blocked_non_large_score_count": 0,
        "total_goals": [], "examples": [],
    })

    for bt in read_csv(backtest_path):
        mid = bt["match_id"]
        is_large = bt.get("is_large_score") == "true"
        audit_path = audit_dir / f"{mid}.json"
        if not audit_path.exists():
            continue
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        blockers = audit.get("block_reasons", [])
        if isinstance(blockers, str):
            blockers = [b for b in blockers.split(";") if b]
        tail = audit.get("v37_large_score_tail", {})
        if tail.get("tail_boost_level", "none") != "none":
            continue
        for reason in blockers:
            gate = gate_from_block_reason(reason)
            g = gate_stats[gate]
            g["blocked_count"] += 1
            if is_large:
                g["blocked_large_score_count"] += 1
            else:
                g["blocked_non_large_score_count"] += 1
            try:
                h, a = map(int, bt.get("actual_scoreline", "0-0").split("-"))
                g["total_goals"].append(h + a)
            except ValueError:
                pass
            if len(g["examples"]) < 3:
                g["examples"].append(mid)

    rows: list[dict[str, str]] = []
    for gate, g in sorted(gate_stats.items()):
        n = g["blocked_count"]
        avg_goals = sum(g["total_goals"]) / max(len(g["total_goals"]), 1)
        false_rate = round(g["blocked_large_score_count"] / n, 4) if n else 0.0
        true_rate = round(g["blocked_non_large_score_count"] / n, 4) if n else 0.0
        rows.append({
            "gate_name": gate,
            "blocked_count": str(n),
            "blocked_large_score_count": str(g["blocked_large_score_count"]),
            "blocked_non_large_score_count": str(g["blocked_non_large_score_count"]),
            "false_block_rate": str(false_rate),
            "true_block_rate": str(true_rate),
            "avg_actual_total_goals": str(round(avg_goals, 2)),
            "interpretation": gate_interpretation(false_rate, true_rate),
            "examples": ";".join(g["examples"]),
        })

    summary = {
        "gate_count": len(rows),
        "top_blocking_gates": [r["gate_name"] for r in sorted(rows, key=lambda x: -int(x["blocked_count"]))[:5]],
        "total_blocked_cases": sum(int(r["blocked_count"]) for r in rows),
    }
    return rows, summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Tail gate attribution")
    ap.add_argument("--backtest", default=str(BACKTEST_TABLES["results"]))
    ap.add_argument("--case-audit-dir", default=str(BACKTEST_TABLES["case_audit_dir"]))
    ap.add_argument("--output", default=str(DIAGNOSTICS_TABLES["gate_attribution"]))
    ap.add_argument("--summary", default=str(DIAGNOSTICS_TABLES["signal_summary"]))
    args = ap.parse_args()
    ensure_v37_dirs()
    rows, summary = analyze(Path(args.backtest), Path(args.case_audit_dir))
    write_csv(Path(args.output), rows, GATE_ATTRIBUTION_FIELDS)
    summary_path = Path(args.summary)
    existing = {}
    if summary_path.exists():
        existing = json.loads(summary_path.read_text(encoding="utf-8"))
    existing["gate_attribution"] = summary
    summary_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} gate rows -> {args.output}")


if __name__ == "__main__":
    main()
