"""Extract structured signals from source notes or locally supplied excerpts.

Input: database/eventflow/raw_sources/source_notes/<match_id>.csv (preferred)
       or database/eventflow/raw_sources/source_notes.csv (fallback)

Columns include temporal isolation:
  kickoff_time, published_at, available_before_kickoff, evidence_usage
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from eventflow_htft import resolve_match_id, resolve_source_notes_path
from eventflow_source_common import (
    SourceSignal,
    compute_raw_confidence,
    detect_signal_type,
    read_csv,
    tactical_specificity_score,
    timestamp_precision_score,
    write_csv,
)

FIELDS = [
    "match_id", "source_id", "source_type", "source_url", "source_title", "published_at",
    "kickoff_time", "available_before_kickoff", "evidence_usage",
    "minute", "team", "player", "signal_type", "summary", "evidence_snippet", "scenario_tags",
    "source_authority", "timestamp_precision", "tactical_specificity", "data_consistency", "raw_confidence",
]

SCENARIO_TAG_MAP = {
    "pressing_success": "high_press_trap|opponent_build_up_risk",
    "pressing_broken": "press_broken|space_in_midfield",
    "low_block_success": "low_block_survival|under_goals",
    "low_block_failure": "block_pulled_apart|over_goals",
    "transition_threat": "counter_attack|high_line_risk|tail_score",
    "set_piece_edge": "set_piece_breakthrough",
    "goalkeeper_error": "opponent_error|game_state_shift",
    "card_or_referee_chaos": "strict_ref_chaos|score_variance",
    "injury_or_forced_substitution": "forced_sub|stability_loss",
    "late_game_opening": "late_chase_open_game|tail_score",
    "position_shift": "position_shift|role_mismatch",
    "strong_side_attack": "wide_overload|flank_mismatch",
    "tactical_mutual_lock": "tactical_lock|under_goals",
}


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip()[:19], fmt)
        except ValueError:
            continue
    return None


def infer_evidence_usage(row: dict, kickoff: str) -> str:
    explicit = (row.get("evidence_usage") or "").strip()
    if explicit:
        return explicit
    if row.get("minute"):
        return "post_match_review"
    pub = _parse_dt(row.get("published_at", ""))
    ko = _parse_dt(kickoff)
    if pub and ko and pub >= ko:
        return "post_match_review"
    return "pre_match_prediction"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match-id", default="")
    parser.add_argument("--infile", default="")
    parser.add_argument("--out", default="database/eventflow/processed/source_signal_events.csv")
    parser.add_argument("--append", action="store_true", help="Append/replace rows for match_id only")
    args = parser.parse_args()

    infile = args.infile
    if not infile and args.match_id:
        infile = resolve_source_notes_path(args.match_id)
    if not infile:
        infile = "database/eventflow/raw_sources/source_notes.csv"

    rows = read_csv(Path(infile))
    if args.match_id:
        rows = [r for r in rows if r.get("match_id") == args.match_id]

    signals = []
    for r in rows:
        text = (r.get("text") or r.get("summary") or "").strip()
        if not text:
            continue
        mid = r.get("match_id", "")
        resolved = resolve_match_id(mid)
        kickoff = r.get("kickoff_time") or resolved.get("kickoff_time", "")
        usage = infer_evidence_usage(r, kickoff)
        pub = _parse_dt(r.get("published_at", ""))
        ko = _parse_dt(kickoff)
        avail = r.get("available_before_kickoff")
        if avail is None or avail == "":
            if not pub:
                avail = "false"
            elif usage == "pre_match_prediction" and (not ko or pub < ko):
                avail = "true"
            else:
                avail = "false"
        elif not pub and str(avail).lower() == "true":
            avail = "false"
        signal_type = r.get("signal_type") or detect_signal_type(text)
        tscore = tactical_specificity_score(text)
        if r.get("tactical_specificity"):
            try:
                tscore = float(r["tactical_specificity"])
            except (TypeError, ValueError):
                pass
        mscore = timestamp_precision_score(r.get("minute", ""))
        authority = float(r.get("source_authority") or 0.5)
        consistency = float(r.get("data_consistency") or 0.5)
        confidence = compute_raw_confidence(authority, mscore, tscore, consistency)
        sig = SourceSignal(
            match_id=mid,
            source_id=r.get("source_id", ""),
            source_url=r.get("source_url", ""),
            source_title=r.get("source_title", ""),
            published_at=r.get("published_at", ""),
            minute=r.get("minute", ""),
            team=r.get("team", ""),
            player=r.get("player", ""),
            signal_type=signal_type,
            summary=text[:500],
            evidence_snippet=(r.get("evidence_snippet") or "")[:220],
            scenario_tags=SCENARIO_TAG_MAP.get(signal_type, "general_observation"),
            source_authority=authority,
            timestamp_precision=mscore,
            tactical_specificity=tscore,
            data_consistency=consistency,
            raw_confidence=confidence,
        )
        d = sig.__dict__
        d["source_type"] = r.get("source_type") or r.get("source_id", "")
        d["kickoff_time"] = kickoff
        d["available_before_kickoff"] = str(avail).lower()
        d["evidence_usage"] = usage
        signals.append(d)

    out_path = Path(args.out)
    existing = read_csv(out_path) if args.append and out_path.exists() else []
    if args.match_id and existing:
        existing = [e for e in existing if e.get("match_id") != args.match_id]
    write_csv(out_path, existing + signals, FIELDS)
    pre = sum(1 for s in signals if s.get("evidence_usage") == "pre_match_prediction")
    post = len(signals) - pre
    print(f"Extracted {len(signals)} signals (pre={pre} post={post}) -> {args.out}")

if __name__ == "__main__":
    main()
