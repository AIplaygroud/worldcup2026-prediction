#!/usr/bin/env python3
"""Audit score-only or metric-incomplete rows in wc2026_match_xg.csv."""
from __future__ import annotations

import argparse
from pathlib import Path

from group_state_common import FIXTURES, MAPPING, MATCH_XG, ROOT, read_csv, write_csv

OUT_DIR = ROOT / "outputs" / "phase07_xg_metric_backfill"

AUDIT_FIELDS = [
    "match_id", "fifa_match_id", "group", "round", "match_date",
    "home_team", "away_team", "home_score", "away_score",
    "missing_home_xg", "missing_away_xg", "missing_home_shots", "missing_away_shots",
    "quality_flag", "profile_update_allowed", "matrix_update_allowed", "recommended_action",
]


def _missing(val: str) -> bool:
    return not str(val or "").strip()


def _match_id_for_row(row: dict, mapping_rows: list[dict]) -> str:
    for m in mapping_rows:
        if (
            m.get("group") == row.get("group")
            and m.get("home_team") == row.get("home_team")
            and m.get("away_team") == row.get("away_team")
        ):
            return m.get("internal_match_id", "")
    return ""


def _round_for_fifa(fid: str, fixtures: list[dict]) -> str:
    for f in fixtures:
        if f.get("fifa_match_id") == fid:
            return f.get("round", "")
    return ""


def audit() -> list[dict]:
    rows = read_csv(MATCH_XG)
    mapping = read_csv(MAPPING)
    fixtures = read_csv(FIXTURES)
    fid_map = {m["fifa_match_id"]: m for m in mapping}

    out: list[dict] = []
    for r in rows:
        qf = r.get("quality_flag", "")
        miss_hxg = _missing(r.get("home_xg", ""))
        miss_axg = _missing(r.get("away_xg", ""))
        miss_hs = _missing(r.get("home_shots", ""))
        miss_as = _missing(r.get("away_shots", ""))
        if qf != "score_only_backfill" and not (miss_hxg or miss_axg or miss_hs or miss_as):
            continue
        mid = _match_id_for_row(r, mapping)
        fid = fid_map.get(mid, {}).get("fifa_match_id", "") if mid else ""
        if not fid:
            for m in mapping:
                if m.get("home_team") == r.get("home_team") and m.get("away_team") == r.get("away_team"):
                    fid = m.get("fifa_match_id", "")
                    mid = m.get("internal_match_id", mid)
                    break
        score_only = qf == "score_only_backfill" or miss_hxg or miss_axg
        out.append({
            "match_id": mid,
            "fifa_match_id": fid,
            "group": r.get("group", ""),
            "round": _round_for_fifa(str(fid), fixtures),
            "match_date": r.get("match_date", ""),
            "home_team": r.get("home_team", ""),
            "away_team": r.get("away_team", ""),
            "home_score": r.get("home_score", ""),
            "away_score": r.get("away_score", ""),
            "missing_home_xg": str(miss_hxg).lower(),
            "missing_away_xg": str(miss_axg).lower(),
            "missing_home_shots": str(miss_hs).lower(),
            "missing_away_shots": str(miss_as).lower(),
            "quality_flag": qf,
            "profile_update_allowed": "false" if score_only else "true",
            "matrix_update_allowed": "false" if score_only else "true",
            "recommended_action": "apply_xg_metric_backfill" if score_only else "review_partial_metrics",
        })
    return out


def write_report(rows: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase 07A Score-Only Audit",
        "",
        f"- score_only_or_incomplete_rows: **{len(rows)}**",
        "",
        "## Rows",
        "",
    ]
    for r in rows:
        lines.append(
            f"- `{r['match_id']}` {r['home_team']} vs {r['away_team']} "
            f"({r['quality_flag']}) — {r['recommended_action']}"
        )
    lines.extend([
        "",
        "## Boundaries",
        "",
        "- score_only rows: standings/path OK; profile/matrix update blocked",
    ])
    (OUT_DIR / "phase07A_score_only_audit_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    rows = audit()
    write_csv(args.out_dir / "score_only_rows_audit.csv", AUDIT_FIELDS, rows)
    write_report(rows)
    print(f"audited {len(rows)} score-only/incomplete rows")


if __name__ == "__main__":
    main()
