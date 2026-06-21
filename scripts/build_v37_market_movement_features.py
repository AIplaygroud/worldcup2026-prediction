#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build market movement features — audit only, no betting recommendations."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from eventflow_common import read_csv, snum, write_csv
from v37_common import FEATURE_TABLES, NORMALIZED_TABLES, V37_AUDIT, ensure_v37_dirs, fnum

MOVEMENT_FIELDS = [
    "match_id",
    "market",
    "selection",
    "opening_sp",
    "latest_sp",
    "sp_delta",
    "implied_prob_delta",
    "move_direction",
    "provider_count",
    "movement_quality",
    "market_warning",
]


def _implied(sp: float) -> float:
    return 1.0 / sp if sp > 0 else 0.0


def _warning(delta: float, direction: str, providers: int) -> str:
    if providers == 0:
        return "market_missing"
    if delta <= -0.12:
        return "favorite_overheated"
    if delta >= 0.15:
        return "underdog_plus_supported"
    if abs(delta) >= 0.10:
        return "odds_conflict_with_model"
    if direction == "drifted":
        return "deep_handicap_pressure"
    return ""


def build_market_movement(match_filter: str = "") -> int:
    ensure_v37_dirs()
    odds = read_csv(NORMALIZED_TABLES["odds_snapshots"])
    out: list[dict[str, str]] = []

    by_key: dict[tuple[str, str, str], list[dict]] = {}
    for r in odds:
        key = (r["match_id"], r["market"], r["selection"])
        by_key.setdefault(key, []).append(r)

    for (mid, market, selection), rows in by_key.items():
        if match_filter and mid != match_filter:
            continue
        opening = next((r for r in rows if snum(r, "is_opening") == "true"), rows[0] if rows else None)
        if not opening:
            continue
        providers = len({snum(r, "provider") for r in rows})
        closing = next((r for r in rows if snum(r, "is_closing") == "true"), rows[-1])
        open_sp = fnum(opening, "sp")
        latest_sp = fnum(closing, "sp") if closing else open_sp
        delta = (latest_sp - open_sp) / open_sp if open_sp else 0.0
        imp_delta = _implied(latest_sp) - _implied(open_sp)
        direction = "shortened" if delta < -0.02 else "drifted" if delta > 0.02 else "stable"
        quality = "high" if providers >= 2 else "medium" if providers == 1 else "low"
        warning = _warning(delta, direction, providers)

        out.append({
            "match_id": mid,
            "market": market,
            "selection": selection,
            "opening_sp": f"{open_sp:.4f}",
            "latest_sp": f"{latest_sp:.4f}",
            "sp_delta": f"{delta:.4f}",
            "implied_prob_delta": f"{imp_delta:.4f}",
            "move_direction": direction,
            "provider_count": str(providers),
            "movement_quality": quality,
            "market_warning": warning,
        })

    write_csv(FEATURE_TABLES["market_movement"], out, MOVEMENT_FIELDS)
    (V37_AUDIT / "market_movement_build_log.json").write_text(
        json.dumps({"built_at": datetime.now(timezone.utc).isoformat(), "rows": len(out)}, indent=2),
        encoding="utf-8",
    )
    return len(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build market movement features")
    ap.add_argument("--match-id", default="")
    args = ap.parse_args()
    n = build_market_movement(args.match_id)
    print(f"Market movement: {n} rows -> {FEATURE_TABLES['market_movement']}")


if __name__ == "__main__":
    main()
