from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from eventflow_source_common import minute_to_bucket, read_csv, stable_id, write_csv

FIELDS = [
    "claim_id", "match_id", "canonical_signal", "signal_type", "team", "minute_bucket",
    "sources", "agreement_count", "conflict_count", "final_confidence",
    "evidence_grade", "single_source_penalty", "use_for_weighting", "use_for_prediction",
    "available_before_kickoff", "evidence_usage",
    "source_url", "source_type", "source_authority", "tactical_specificity", "evidence_snippet",
    "conflict_note",
]

HIGH_AUTHORITY_SOURCES = {
    "fifa_training_centre", "fifa_match_centre", "statsbomb_open_data",
    "espn_match_commentary", "the_guardian_match_report", "world_soccer_talk_previews",
}
SINGLE_SOURCE_PENALTY = 0.65
B_GRADE_AUTHORITY_FLOOR = 0.70
B_GRADE_TACTICAL_FLOOR = 0.20


def canonical(row: dict) -> str:
    return "|".join([
        row.get("match_id", ""),
        row.get("team", ""),
        row.get("signal_type", ""),
        minute_to_bucket(row.get("minute", "")),
    ])


def detect_conflicts(groups: dict[str, list]) -> dict[str, str]:
    conflict_pairs = [
        ("low_block_success", "low_block_failure"),
        ("pressing_success", "pressing_broken"),
        ("tactical_mutual_lock", "strong_side_attack"),
    ]
    notes: dict[str, str] = {}
    by_match_team: dict[str, set[str]] = defaultdict(set)
    for key, items in groups.items():
        first = items[0]
        mt = f"{first.get('match_id')}|{first.get('team')}"
        by_match_team[mt].add(first.get("signal_type", ""))
    for mt, types in by_match_team.items():
        for a, b in conflict_pairs:
            if a in types and b in types:
                notes[mt] = f"conflict:{a}_vs_{b}"
    return notes


def _event_meta(items: list[dict]) -> dict:
    first = items[0]
    return {
        "source_url": first.get("source_url", ""),
        "source_type": first.get("source_type") or first.get("source_id", ""),
        "source_authority": float(first.get("source_authority") or 0.0),
        "tactical_specificity": float(first.get("tactical_specificity") or 0.0),
        "evidence_snippet": first.get("evidence_snippet", ""),
        "published_at": first.get("published_at", ""),
        "available_before_kickoff": first.get("available_before_kickoff", ""),
        "evidence_usage": first.get("evidence_usage", ""),
    }


def grade_claim(
    agreement_count: int,
    final_confidence: float,
    sources: list[str],
    avg_authority: float,
    conflict_note: str,
    meta: dict,
) -> tuple[str, float, bool, bool]:
    usage = meta.get("evidence_usage", "")
    has_pub = bool(meta.get("published_at"))
    avail = str(meta.get("available_before_kickoff", "")).lower() == "true"
    is_prematch = (
        usage == "pre_match_prediction"
        and has_pub
        and avail
        and usage not in ("post_match_review", "backtest_only")
    )
    if usage in ("post_match_review", "backtest_only"):
        return "C", 0.0, False, False
    if not has_pub:
        return "C", 0.0, False, False

    if conflict_note and agreement_count < 2:
        return "C", 0.0, False, is_prematch

    if agreement_count >= 2 and final_confidence >= 0.60 and is_prematch:
        return "A", 1.0, True, True

    if agreement_count == 1 and is_prematch:
        src = sources[0] if sources else ""
        auth = meta.get("source_authority") or avg_authority
        tac = meta.get("tactical_specificity") or 0.0
        has_url = bool(meta.get("source_url"))
        has_snippet = bool(meta.get("evidence_snippet"))
        has_type = bool(meta.get("source_type"))
        b_ok = (
            has_url and has_pub and has_snippet and has_type
            and auth >= B_GRADE_AUTHORITY_FLOOR
            and tac >= B_GRADE_TACTICAL_FLOOR
            and final_confidence >= 0.50
            and (src in HIGH_AUTHORITY_SOURCES or auth >= B_GRADE_AUTHORITY_FLOOR)
        )
        if b_ok:
            return "B", SINGLE_SOURCE_PENALTY, True, True
        if not has_url or not has_pub:
            return "C", 0.0, False, False
        if final_confidence >= 0.45:
            return "C", 0.0, False, is_prematch

    if final_confidence >= 0.45 and is_prematch:
        return "C", 0.0, False, True
    return "C", 0.0, False, False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--infile", default="database/eventflow/processed/source_signal_events.csv")
    parser.add_argument("--out", default="database/eventflow/processed/source_signal_claims.csv")
    parser.add_argument("--quality", default="database/eventflow/processed/source_signal_quality.csv")
    args = parser.parse_args()

    rows = read_csv(Path(args.infile))
    quality = {r.get("source_id", ""): float(r.get("authority_score") or 0.5) for r in read_csv(Path(args.quality))}
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[canonical(r)].append(r)
    conflict_map = detect_conflicts(groups)

    claims = []
    for key, items in groups.items():
        first = items[0]
        meta = _event_meta(items)
        sources = sorted(set(i.get("source_id", "") for i in items if i.get("source_id")))
        agreement_count = len(sources)
        avg_raw = sum(float(i.get("raw_confidence") or 0.0) for i in items) / max(1, len(items))
        avg_auth = sum(quality.get(s, 0.5) for s in sources) / max(1, len(sources))
        agreement_boost = min(0.20, max(0, agreement_count - 1) * 0.08)
        final_confidence = round(min(1.0, avg_raw + agreement_boost), 4)
        mt = f"{first.get('match_id')}|{first.get('team')}"
        conflict_note = conflict_map.get(mt, "")
        grade, penalty, use_w, use_pred = grade_claim(
            agreement_count, final_confidence, sources, avg_auth, conflict_note, meta,
        )
        claims.append({
            "claim_id": stable_id(key),
            "match_id": first.get("match_id", ""),
            "canonical_signal": key,
            "signal_type": first.get("signal_type", ""),
            "team": first.get("team", ""),
            "minute_bucket": minute_to_bucket(first.get("minute", "")),
            "sources": "|".join(sources),
            "agreement_count": agreement_count,
            "conflict_count": 1 if conflict_note else 0,
            "final_confidence": final_confidence,
            "evidence_grade": grade,
            "single_source_penalty": penalty if grade == "B" else (0.0 if grade == "A" else ""),
            "use_for_weighting": str(use_w).lower(),
            "use_for_prediction": str(use_pred).lower(),
            "available_before_kickoff": meta.get("available_before_kickoff", ""),
            "evidence_usage": meta.get("evidence_usage", ""),
            "source_url": meta.get("source_url", ""),
            "source_type": meta.get("source_type", ""),
            "source_authority": meta.get("source_authority", ""),
            "tactical_specificity": meta.get("tactical_specificity", ""),
            "evidence_snippet": meta.get("evidence_snippet", ""),
            "conflict_note": conflict_note,
        })

    write_csv(Path(args.out), claims, FIELDS)
    grades = defaultdict(int)
    for c in claims:
        grades[c["evidence_grade"]] += 1
    print(f"Validated {len(claims)} claims -> {args.out}  A={grades['A']} B={grades['B']} C={grades['C']}")

if __name__ == "__main__":
    main()
