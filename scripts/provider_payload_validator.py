#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provider cached payload validation rules for V3.7-P3.2."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from eventflow_common import snum
from v37_common import PROVIDER_CONFIDENCE_ENRICH_MIN


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def validate_fixture(row: Mapping[str, Any], match_id: str = "") -> list[str]:
    errs: list[str] = []
    if not snum(row, "provider_match_id") and not snum(row, "match_id"):
        errs.append(f"{match_id}: fixture missing provider_match_id")
    if not snum(row, "home_team") and not snum(row, "home"):
        errs.append(f"{match_id}: fixture missing home")
    if not snum(row, "away_team") and not snum(row, "away"):
        errs.append(f"{match_id}: fixture missing away")
    if not snum(row, "kickoff_utc") and not snum(row, "kickoff"):
        errs.append(f"{match_id}: fixture missing kickoff")
    return errs


def validate_event(row: Mapping[str, Any], match_id: str, kickoff: str = "") -> list[str]:
    errs: list[str] = []
    et = snum(row, "event_type").lower()
    if not et:
        errs.append(f"{match_id}: event missing event_type")
        return errs
    if et != "fulltime" and snum(row, "minute") == "":
        errs.append(f"{match_id}: event missing minute")
    if et in ("goal", "own_goal", "penalty_goal"):
        if not snum(row, "team"):
            errs.append(f"{match_id}: goal event missing team")
    ts = snum(row, "fetched_at_utc") or snum(row, "timestamp")
    k = _parse_dt(kickoff)
    t = _parse_dt(ts)
    if t and k and t > k:
        errs.append(f"{match_id}: event timestamp post-kickoff")
    return errs


def validate_lineup(row: Mapping[str, Any], match_id: str, kickoff: str = "") -> list[str]:
    errs: list[str] = []
    if not snum(row, "team"):
        errs.append(f"{match_id}: lineup missing team")
    if not snum(row, "player_name") and not snum(row, "player"):
        errs.append(f"{match_id}: lineup missing player_name")
    if not snum(row, "lineup_status"):
        errs.append(f"{match_id}: lineup missing lineup_status")
    cat = snum(row, "confirmed_at_utc")
    k = _parse_dt(kickoff)
    c = _parse_dt(cat)
    if c and k and c > k:
        errs.append(f"{match_id}: lineup confirmed post-kickoff")
    return errs


def validate_match_stats(row: Mapping[str, Any], match_id: str) -> list[str]:
    errs: list[str] = []
    if not snum(row, "team"):
        errs.append(f"{match_id}: stats missing team")
    has_metric = any(
        snum(row, k) for k in ("shots", "xg", "shots_on_target", "big_chances", "sot")
    )
    if not has_metric:
        errs.append(f"{match_id}: stats missing shots/xg/sot/big_chances")
    return errs


def validate_odds(row: Mapping[str, Any], match_id: str, kickoff: str = "") -> list[str]:
    errs: list[str] = []
    for f in ("market", "selection", "sp"):
        if not snum(row, f):
            errs.append(f"{match_id}: odds missing {f}")
    if not snum(row, "fetched_at_utc") and not snum(row, "fetched_at"):
        errs.append(f"{match_id}: odds missing fetched_at")
    ts = snum(row, "fetched_at_utc") or snum(row, "fetched_at")
    k = _parse_dt(kickoff)
    t = _parse_dt(ts)
    if t and k and t > k:
        errs.append(f"{match_id}: odds fetched post-kickoff")
    return errs


def confidence_allows_enrich(confidence: float, alias_verified: bool = True) -> tuple[bool, str]:
    if confidence < PROVIDER_CONFIDENCE_ENRICH_MIN:
        return False, "match_confidence_below_threshold"
    if confidence < 0.80 and not alias_verified:
        return False, "alias_not_verified"
    return True, ""
