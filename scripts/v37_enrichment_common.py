#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.7-P3.1 normalized table merge keys, dedupe, and enrichment audit helpers."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone, timezone
from typing import Any, Callable, Mapping, Optional

from eventflow_common import normalize_team, snum

MERGE_KEYS: dict[str, list[str]] = {
    "matches": ["match_id"],
    "standings_snapshot": ["match_id", "team"],
    "match_stats": ["match_id", "team", "data_timing"],
    "team_recent_stats": ["match_id", "team"],
    "match_events": ["match_id", "event_id"],
    "lineups": ["match_id", "team", "player_name", "lineup_status"],
    "player_availability": ["match_id", "team", "player", "signal_type"],
    "odds_snapshots": ["match_id", "market", "selection", "provider", "fetched_at_utc"],
}

AUDIT_FIELDS = [
    "audit_id",
    "run_id",
    "provider",
    "table",
    "match_id",
    "key",
    "field",
    "local_value",
    "external_value",
    "chosen_value",
    "action",
    "confidence",
    "reason",
    "created_at",
]

ALLOWED_AUDIT_ACTIONS = frozenset({
    "keep_local",
    "fill_missing",
    "replace_proxy",
    "conflict_keep_local",
    "conflict_external_override",
    "skip_duplicate",
    "duplicate_removed",
    "invalid_post_kickoff",
    "invalid_missing_key",
    "invalid_provider_payload",
    "skip_low_confidence",
    "skip_missing_provider_match",
    "invalid_provider_match",
    "dry_run_only",
})

PROVIDER_ENRICH_MIN_CONFIDENCE = 0.6


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]


def normalize_player_name(name: str) -> str:
    s = re.sub(r"\s+", " ", (name or "").strip().lower())
    return s


def make_event_id(row: Mapping[str, Any], match_id: str = "") -> str:
    eid = snum(row, "event_id")
    if eid:
        return eid
    mid = snum(row, "match_id") or match_id
    minute = snum(row, "minute", "0")
    team = normalize_team(snum(row, "team"))
    etype = snum(row, "event_type", "event").lower()
    player = normalize_player_name(snum(row, "player"))
    return f"{mid}_{minute}_{team}_{etype}_{player}".lower()


def row_merge_key(table: str, row: Mapping[str, str], *, normalize_lineup_name: bool = True) -> tuple:
    keys = MERGE_KEYS[table]
    parts: list[str] = []
    for k in keys:
        v = snum(row, k)
        if table == "lineups" and k == "player_name" and normalize_lineup_name:
            v = normalize_player_name(v)
        parts.append(v)
    return tuple(parts)


def is_match_stats_proxy(row: Mapping[str, str]) -> bool:
    return snum(row, "quality_flag") == "proxy" or snum(row, "source") == "proxy_prior"


def is_team_recent_proxy(row: Mapping[str, str]) -> bool:
    return snum(row, "quality_flag") == "proxy"


def is_lineup_proxy(row: Mapping[str, str]) -> bool:
    return snum(row, "lineup_status") in ("projected", "proxy", "") or snum(row, "evidence_grade") == "proxy"


def is_odds_local_jc(row: Mapping[str, str]) -> bool:
    prov = snum(row, "provider").lower()
    return prov in ("local_jc_odds", "jc-odds", "local", "jc_odds")


def is_external_real_row(table: str, row: Mapping[str, str]) -> bool:
    if table == "match_stats":
        return not is_match_stats_proxy(row)
    if table == "team_recent_stats":
        return not is_team_recent_proxy(row)
    if table == "lineups":
        return snum(row, "lineup_status") == "confirmed"
    if table == "odds_snapshots":
        return bool(snum(row, "sp")) and not is_odds_local_jc(row)
    if table == "match_events":
        return bool(snum(row, "event_type")) and snum(row, "source") not in ("proxy", "final_score_derived")
    return bool(row)


def prepare_event_row(row: dict[str, str], match_id: str) -> dict[str, str]:
    out = dict(row)
    out["match_id"] = snum(out, "match_id") or match_id
    out["event_id"] = make_event_id(out, match_id)
    return out


def prepare_lineup_row(row: dict[str, str], match_id: str) -> dict[str, str]:
    out = dict(row)
    out["match_id"] = snum(out, "match_id") or match_id
    out["player_name"] = snum(out, "player_name")  # keep display; key uses normalized
    return out


def dedupe_table_rows(
    table: str,
    rows: list[dict[str, str]],
    audit: list[dict[str, str]],
    *,
    run_id: str,
    provider: str = "local",
    match_id: str = "",
) -> list[dict[str, str]]:
    """Remove duplicate rows by merge key; audit duplicate_removed."""
    seen: dict[tuple, dict[str, str]] = {}
    out: list[dict[str, str]] = []
    fulltime_count: dict[str, int] = {}

    for row in rows:
        if table == "match_events":
            row = prepare_event_row(row, snum(row, "match_id") or match_id)
            if snum(row, "event_type").lower() == "fulltime":
                mid = snum(row, "match_id")
                fulltime_count[mid] = fulltime_count.get(mid, 0) + 1
                if fulltime_count[mid] > 1:
                    audit.append(_audit_entry(
                        run_id, provider, table, snum(row, "match_id"),
                        key=str(row_merge_key(table, row)),
                        field="event_type",
                        local_value="fulltime",
                        external_value="fulltime",
                        chosen_value="skip",
                        action="duplicate_removed",
                        confidence="1.0",
                        reason="fulltime_event_duplicate",
                    ))
                    continue

        key = row_merge_key(table, row)
        if key in seen:
            audit.append(_audit_entry(
                run_id, provider, table, snum(row, "match_id") or match_id,
                key=str(key),
                field="row",
                local_value=json.dumps(seen[key], ensure_ascii=False)[:120],
                external_value=json.dumps(row, ensure_ascii=False)[:120],
                chosen_value="first",
                action="duplicate_removed",
                confidence="1.0",
                reason="merge_key_duplicate",
            ))
            continue
        seen[key] = row
        out.append(row)
    return out


def _audit_entry(
    run_id: str,
    provider: str,
    table: str,
    match_id: str,
    *,
    key: str,
    field: str,
    local_value: str,
    external_value: str,
    chosen_value: str,
    action: str,
    confidence: str,
    reason: str,
) -> dict[str, str]:
    return {
        "audit_id": uuid.uuid4().hex[:12],
        "run_id": run_id,
        "provider": provider,
        "table": table,
        "match_id": match_id,
        "key": key,
        "field": field,
        "local_value": local_value[:500],
        "external_value": external_value[:500],
        "chosen_value": chosen_value[:500],
        "action": action,
        "confidence": confidence,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def merge_external_rows(
    table: str,
    local_rows: list[dict[str, str]],
    external_rows: list[dict[str, Any]],
    match_id: str,
    provider: str,
    run_id: str,
    audit: list[dict[str, str]],
    *,
    kickoff_utc: str = "",
    match_confidence: float = 1.0,
) -> list[dict[str, str]]:
    """Merge external provider rows for one match into local table rows."""
    if match_confidence < PROVIDER_ENRICH_MIN_CONFIDENCE:
        audit.append(_audit_entry(
            run_id, provider, table, match_id,
            key=match_id, field="match_confidence",
            local_value="", external_value=str(match_confidence),
            chosen_value="skip", action="invalid_provider_match",
            confidence=str(match_confidence), reason="match_confidence_below_threshold",
        ))
        return local_rows

    others = [r for r in local_rows if snum(r, "match_id") != match_id]
    local_match = [r for r in local_rows if snum(r, "match_id") == match_id]

    if not external_rows:
        if not local_match:
            audit.append(_audit_entry(
                run_id, provider, table, match_id,
                key=match_id, field="*",
                local_value="", external_value="", chosen_value="",
                action="skip_missing_provider_match", confidence="0",
                reason="no_external_rows",
            ))
        return local_rows

    ext_prepared: list[dict[str, str]] = []
    for er in external_rows:
        row = {k: str(er.get(k, "")) for k in er}
        if table == "match_events":
            row = prepare_event_row(row, match_id)
        elif table == "lineups":
            row = prepare_lineup_row(row, match_id)
            if _lineup_post_kickoff(row, kickoff_utc):
                audit.append(_audit_entry(
                    run_id, provider, table, match_id,
                    key=snum(row, "player_name"), field="confirmed_at_utc",
                    local_value="", external_value=snum(row, "confirmed_at_utc"),
                    chosen_value="reject", action="invalid_post_kickoff",
                    confidence="1.0", reason="lineup_after_kickoff",
                ))
                continue
        elif table == "odds_snapshots":
            row["match_id"] = match_id
            if is_odds_local_jc(row):
                continue  # external odds path only for movement; jc kept separate
        else:
            row["match_id"] = snum(row, "match_id") or match_id
        ext_prepared.append(row)

    local_by_key = {row_merge_key(table, r): r for r in local_match}
    merged_match = list(local_match)

    for er in ext_prepared:
        key = row_merge_key(table, er)
        if key in local_by_key:
            local_row = local_by_key[key]
            if table == "match_stats":
                if is_match_stats_proxy(local_row) and is_external_real_row(table, er):
                    _replace_row(merged_match, local_row, er, audit, run_id, provider, table, match_id, key, "replace_proxy")
                    local_by_key[key] = er
                else:
                    audit.append(_audit_entry(
                        run_id, provider, table, match_id, key=str(key), field="row",
                        local_value="real", external_value=json.dumps(er, ensure_ascii=False)[:120],
                        chosen_value="local", action="conflict_keep_local", confidence="1.0",
                        reason="local_real_data_priority",
                    ))
            elif table == "lineups":
                local_confirmed = snum(local_row, "lineup_status") == "confirmed"
                ext_confirmed = snum(er, "lineup_status") == "confirmed"
                if is_lineup_proxy(local_row) and ext_confirmed:
                    _replace_row(merged_match, local_row, er, audit, run_id, provider, table, match_id, key, "replace_proxy")
                    local_by_key[key] = er
                elif local_confirmed:
                    audit.append(_audit_entry(
                        run_id, provider, table, match_id, key=str(key), field="lineup_status",
                        local_value=snum(local_row, "lineup_status"),
                        external_value=snum(er, "lineup_status"),
                        chosen_value="local", action="keep_local", confidence="1.0",
                        reason="confirmed_lineup_priority",
                    ))
                else:
                    audit.append(_audit_entry(
                        run_id, provider, table, match_id, key=str(key), field="row",
                        local_value="present", external_value=json.dumps(er, ensure_ascii=False)[:120],
                        chosen_value="local", action="skip_duplicate", confidence="1.0",
                        reason="duplicate_merge_key",
                    ))
            elif table == "odds_snapshots":
                if is_odds_local_jc(local_row):
                    audit.append(_audit_entry(
                        run_id, provider, table, match_id, key=str(key), field="provider",
                        local_value=snum(local_row, "provider"), external_value=snum(er, "provider"),
                        chosen_value="local", action="keep_local", confidence="1.0",
                        reason="jc_odds_priority",
                    ))
                else:
                    audit.append(_audit_entry(
                        run_id, provider, table, match_id, key=str(key), field="row",
                        local_value="present", external_value=json.dumps(er, ensure_ascii=False)[:120],
                        chosen_value="local", action="skip_duplicate", confidence="1.0",
                        reason="odds_key_exists",
                    ))
            else:
                audit.append(_audit_entry(
                    run_id, provider, table, match_id, key=str(key), field="row",
                    local_value=json.dumps(local_row, ensure_ascii=False)[:120],
                    external_value=json.dumps(er, ensure_ascii=False)[:120],
                    chosen_value="local", action="skip_duplicate", confidence="1.0",
                    reason="merge_key_exists",
                ))
            continue

        if not local_match and not merged_match:
            action = "fill_missing"
        elif table == "match_stats" and all(is_match_stats_proxy(r) for r in merged_match):
            action = "replace_proxy" if merged_match else "fill_missing"
        else:
            action = "fill_missing"

        audit.append(_audit_entry(
            run_id, provider, table, match_id, key=str(key), field="row",
            local_value="", external_value=json.dumps(er, ensure_ascii=False)[:120],
            chosen_value=json.dumps(er, ensure_ascii=False)[:120],
            action=action, confidence="0.9", reason=f"external_{provider}",
        ))
        merged_match.append(er)
        local_by_key[key] = er

    combined = others + merged_match
    return dedupe_table_rows(table, combined, audit, run_id=run_id, provider=provider, match_id=match_id)


def _replace_row(
    merged: list[dict[str, str]],
    old: dict[str, str],
    new: dict[str, str],
    audit: list[dict[str, str]],
    run_id: str,
    provider: str,
    table: str,
    match_id: str,
    key: tuple,
    action: str,
) -> None:
    audit.append(_audit_entry(
        run_id, provider, table, match_id, key=str(key), field="row",
        local_value=json.dumps(old, ensure_ascii=False)[:120],
        external_value=json.dumps(new, ensure_ascii=False)[:120],
        chosen_value=json.dumps(new, ensure_ascii=False)[:120],
        action=action, confidence="0.85", reason=f"proxy_replaced_by_{provider}",
    ))
    for i, r in enumerate(merged):
        if r is old or row_merge_key(table, r) == key:
            merged[i] = new
            return
    merged.append(new)


def _lineup_post_kickoff(row: Mapping[str, str], kickoff_utc: str) -> bool:
    confirmed = snum(row, "confirmed_at_utc")
    if not confirmed or not kickoff_utc:
        return False
    try:
        c = datetime.fromisoformat(confirmed.replace("Z", "+00:00"))
        k = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
        if c.tzinfo is None:
            c = c.replace(tzinfo=timezone.utc)
        if k.tzinfo is None:
            k = k.replace(tzinfo=timezone.utc)
        return c > k
    except ValueError:
        return False


def find_duplicates(table: str, rows: list[dict[str, str]]) -> list[tuple[tuple, int]]:
    counts: dict[tuple, int] = {}
    for r in rows:
        k = row_merge_key(table, r)
        counts[k] = counts.get(k, 0) + 1
    return [(k, n) for k, n in counts.items() if n > 1]


def build_enrichment_summary(
    audit_rows: list[dict[str, str]],
    *,
    run_id: str,
    provider: str,
    dry_run: bool,
) -> dict:
    """Aggregate enrichment audit into per-table action counts."""
    tables: dict[str, dict[str, int]] = {}
    error_count = 0
    warning_count = 0

    for row in audit_rows:
        if row.get("provider") not in (provider, "pre_dedupe", "post_dedupe") and provider != "multi":
            continue
        tbl = row.get("table", "unknown")
        action = row.get("action", "")
        tables.setdefault(tbl, {})
        tables[tbl][action] = tables[tbl].get(action, 0) + 1
        if action.startswith("invalid"):
            error_count += 1
        if action in ("conflict_keep_local", "invalid_post_kickoff"):
            warning_count += 1

    return {
        "run_id": run_id,
        "provider": provider,
        "dry_run": dry_run,
        "tables": tables,
        "error_count": error_count,
        "warning_count": warning_count,
        "safe_to_apply": error_count == 0 and not dry_run,
    }
