#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backtest EventFlow score/result/total-goals/HTFT outputs.

Input:
- database/eventflow/raw/actual_results.csv with columns:
  match_id,home,away,actual_ht_score,actual_score
- database/eventflow/processed/dual_engine_predictions.csv

Output:
- database/eventflow/processed/eventflow_backtest.csv
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from eventflow_common import EVENTFLOW_DB, read_csv, write_csv, snum, htft_label, score_to_result

RAW = Path(__file__).resolve().parents[1] / "database" / "eventflow" / "raw"


def total_bucket(score: str) -> str:
    try:
        h, a = [int(x) for x in score.split("-")]
    except Exception:
        return ""
    total = h + a
    if total <= 1:
        return "0-1球"
    if total == 2:
        return "2球"
    if total == 3:
        return "3球"
    if total == 4:
        return "4球"
    return "5+球"


def main() -> None:
    actual = {snum(r,"match_id"): r for r in read_csv(RAW / "actual_results.csv")}
    preds = read_csv(EVENTFLOW_DB / "dual_engine_predictions.csv")
    by_match: Dict[str, List[Dict[str,str]]] = {}
    for p in preds:
        by_match.setdefault(snum(p,"match_id"), []).append(p)
    out: List[Dict[str, Any]] = []
    for mid, ps in by_match.items():
        a = actual.get(mid)
        if not a:
            continue
        ps_sorted = sorted(ps, key=lambda r: int(float(snum(r,"rank") or 999)))
        top_scores = [snum(p,"score") for p in ps_sorted[:3]]
        actual_score = snum(a,"actual_score")
        actual_ht = snum(a,"actual_ht_score")
        actual_htft = htft_label(actual_ht, actual_score) if actual_ht else ""
        pred_htfts = [snum(p,"htft") for p in ps_sorted[:3]]
        out.append({
            "match_id": mid,
            "home": snum(a,"home"),
            "away": snum(a,"away"),
            "predicted_score_1": top_scores[0] if len(top_scores)>0 else "",
            "predicted_score_2": top_scores[1] if len(top_scores)>1 else "",
            "predicted_score_3": top_scores[2] if len(top_scores)>2 else "",
            "actual_score": actual_score,
            "score_hit_top1": 1 if top_scores and top_scores[0] == actual_score else 0,
            "score_hit_top3": 1 if actual_score in top_scores else 0,
            "result_hit": 1 if top_scores and score_to_result(top_scores[0]) == score_to_result(actual_score) else 0,
            "total_goals_hit": 1 if top_scores and total_bucket(top_scores[0]) == total_bucket(actual_score) else 0,
            "htft_hit": 1 if actual_htft and actual_htft in pred_htfts else 0,
            "brier_delta_vs_v2": "",
            "notes": "",
        })
    write_csv(EVENTFLOW_DB / "eventflow_backtest.csv", out)
    print(f"wrote {len(out)} backtest rows")


if __name__ == "__main__":
    main()
