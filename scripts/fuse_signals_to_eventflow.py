from __future__ import annotations

import argparse
from pathlib import Path
from eventflow_source_common import read_csv, write_csv

FIELDS = [
    "match_id", "home_team", "away_team", "signal_type", "team", "minute_bucket",
    "scenario_id", "weight_delta", "confidence", "evidence_grade", "single_source_penalty",
    "evidence_summary", "sources", "use_for_weighting",
    "available_before_kickoff", "evidence_usage",
]

MAPPING_PATH = Path("database/eventflow/processed/scenario_signal_mapping.csv")
SUMMARY_FIELDS = [
    "match_id", "signal_type", "team", "evidence_grade", "confidence",
    "evidence_summary", "sources", "note",
]


def load_mapping() -> dict[str, dict[str, str]]:
    return {r.get("signal_type", ""): r for r in read_csv(MAPPING_PATH) if r.get("signal_type")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claims", default="database/eventflow/processed/source_signal_claims.csv")
    parser.add_argument("--match-id", default="")
    parser.add_argument("--home", default="")
    parser.add_argument("--away", default="")
    parser.add_argument("--out", default="database/eventflow/processed/eventflow_fused_evidence.csv")
    parser.add_argument("--summary-out", default="database/eventflow/processed/eventflow_evidence_summary.csv")
    args = parser.parse_args()

    mapping = load_mapping()
    rows = read_csv(Path(args.claims))
    fused = []
    summary_only = []
    for r in rows:
        if args.match_id and r.get("match_id") != args.match_id:
            continue
        if r.get("use_for_prediction") != "true":
            continue
        usage = r.get("evidence_usage", "")
        avail = str(r.get("available_before_kickoff", "")).lower() == "true"
        if usage in ("post_match_review", "backtest_only"):
            continue
        if usage and usage != "pre_match_prediction" and not avail:
            continue
        sig = r.get("signal_type", "")
        grade = r.get("evidence_grade", "C")
        m = mapping.get(sig, {})
        scenario_id = m.get("scenario_id", "S10_tactical_stalemate_mutual_constraint")
        direction = m.get("weight_direction", "+1")
        sign = -1.0 if str(direction).startswith("-") else 1.0
        base_delta = float(m.get("base_delta") or 0.02)
        conf = float(r.get("final_confidence") or 0.0)
        penalty = float(r.get("single_source_penalty") or 1.0) if grade == "B" else 1.0
        use_weight = r.get("use_for_weighting", "false") == "true" and grade in ("A", "B")
        delta = round(sign * base_delta * conf * penalty, 4) if use_weight else 0.0
        row = {
            "match_id": r.get("match_id", ""),
            "home_team": args.home,
            "away_team": args.away,
            "signal_type": sig,
            "team": r.get("team", ""),
            "minute_bucket": r.get("minute_bucket", ""),
            "scenario_id": scenario_id,
            "weight_delta": delta,
            "confidence": conf,
            "evidence_grade": grade,
            "single_source_penalty": r.get("single_source_penalty", ""),
            "evidence_summary": r.get("canonical_signal", ""),
            "sources": r.get("sources", ""),
            "use_for_weighting": str(use_weight).lower(),
            "available_before_kickoff": r.get("available_before_kickoff", ""),
            "evidence_usage": r.get("evidence_usage", "pre_match_prediction"),
        }
        if use_weight:
            fused.append(row)
        elif grade == "C":
            summary_only.append({
                "match_id": r.get("match_id", ""),
                "signal_type": sig,
                "team": r.get("team", ""),
                "evidence_grade": "C",
                "confidence": conf,
                "evidence_summary": r.get("canonical_signal", ""),
                "sources": r.get("sources", ""),
                "note": "仅进入 evidence_summary，不参与 scenario 加权",
            })

    write_csv(Path(args.out), fused, FIELDS)
    write_csv(Path(args.summary_out), summary_only, SUMMARY_FIELDS)
    print(f"Fused {len(fused)} weighted evidence (A/B) -> {args.out}")
    print(f"C-grade summary-only {len(summary_only)} -> {args.summary_out}")

if __name__ == "__main__":
    main()
