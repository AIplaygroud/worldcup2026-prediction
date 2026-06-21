#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build provider match map — local + external cache fixtures."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from eventflow_common import normalize_team, read_csv, snum, write_csv
from group_state_common import FIXTURES, MAPPING
from v37_common import NORMALIZED_TABLES, V37_AUDIT, V37_TAIL_THRESHOLDS, ensure_v37_dirs

from data_providers.provider_cache_common import list_cached_match_keys, load_cache_list

PROVIDER_MAP_FIELDS = [
    "internal_match_id",
    "fifa_match_id",
    "provider",
    "provider_match_id",
    "provider_home",
    "provider_away",
    "internal_home",
    "internal_away",
    "kickoff_utc",
    "match_confidence",
    "status",
    "reason",
]


def _kickoff_from_fixture(fifa_id: str) -> str:
    for r in read_csv(FIXTURES):
        if snum(r, "fifa_match_id") == fifa_id:
            kt = snum(r, "kickoff_time")
            if kt:
                return kt.replace(" ", "T") + ":00Z"
    return ""


def build_local_map() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows: list[dict[str, str]] = []
    audit_low: list[dict[str, str]] = []
    matches = read_csv(NORMALIZED_TABLES["matches"]) if NORMALIZED_TABLES["matches"].exists() else []

    for m in read_csv(MAPPING):
        mid = snum(m, "internal_match_id")
        fifa = snum(m, "fifa_match_id")
        home = normalize_team(m["home_team"])
        away = normalize_team(m["away_team"])
        kickoff = _kickoff_from_fixture(fifa)
        norm = next((x for x in matches if x["match_id"] == mid), None)
        if norm:
            kickoff = snum(norm, "kickoff_utc") or kickoff
            provider_id = snum(norm, "provider_match_id") or fifa
            status = snum(norm, "status", "scheduled")
        else:
            provider_id = fifa
            status = "scheduled"

        confidence = 1.0 if norm else 0.85
        row = {
            "internal_match_id": mid,
            "fifa_match_id": fifa,
            "provider": "local",
            "provider_match_id": provider_id,
            "provider_home": home,
            "provider_away": away,
            "internal_home": home,
            "internal_away": away,
            "kickoff_utc": kickoff,
            "match_confidence": f"{confidence:.4f}",
            "status": status,
            "reason": "local_normalized",
        }
        if confidence >= V37_TAIL_THRESHOLDS["provider_match_confidence_min"]:
            rows.append(row)
        else:
            audit_low.append({**row, "reason": "match_confidence_below_threshold"})
    return rows, audit_low


def build_external_cache_map(provider: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Map cached fixture files to internal matches by team + kickoff."""
    rows: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    matches = {r["match_id"]: r for r in read_csv(NORMALIZED_TABLES["matches"])}
    keys = list_cached_match_keys(provider, "fixtures")
    if not keys:
        keys = list_cached_match_keys(provider, "events")

    for key in keys:
        fixtures = load_cache_list(provider, "fixtures", key)
        if not fixtures:
            fixtures = [{"provider_match_id": key, "internal_match_id": key}]
        for fx in fixtures:
            mid = snum(fx, "internal_match_id") or key
            if mid not in matches:
                rejected.append({"match_key": key, "reason": "no_internal_match"})
                continue
            m = matches[mid]
            ph = normalize_team(snum(fx, "home_team") or snum(fx, "home") or m["home_team"])
            pa = normalize_team(snum(fx, "away_team") or snum(fx, "away") or m["away_team"])
            ih = normalize_team(m["home_team"])
            ia = normalize_team(m["away_team"])
            confidence = 1.0 if ph == ih and pa == ia else 0.75
            reason = "team_kickoff_exact" if confidence >= 1.0 else "team_alias_candidate"
            row = {
                "internal_match_id": mid,
                "fifa_match_id": snum(m, "provider_match_id"),
                "provider": provider,
                "provider_match_id": key,
                "provider_home": ph,
                "provider_away": pa,
                "internal_home": ih,
                "internal_away": ia,
                "kickoff_utc": snum(m, "kickoff_utc"),
                "match_confidence": f"{confidence:.4f}",
                "status": snum(m, "status", "scheduled"),
                "reason": reason,
            }
            if confidence >= V37_TAIL_THRESHOLDS["provider_match_confidence_min"]:
                rows.append(row)
            else:
                rejected.append({**row, "reason": "match_confidence_below_threshold"})
    return rows, rejected


def build_provider_map(providers: list[str]) -> dict[str, int]:
    ensure_v37_dirs()
    all_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []

    for name in providers:
        if name == "local":
            rows, low = build_local_map()
            all_rows.extend(rows)
            audit_rows.extend(low)
        elif name in ("thestatsapi", "sportmonks", "apifootball"):
            rows, rej = build_external_cache_map(name)
            all_rows.extend(rows)
            audit_rows.extend(rej)

    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for r in all_rows:
        key = (r["internal_match_id"], r["provider"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    write_csv(NORMALIZED_TABLES["provider_match_map"], deduped, PROVIDER_MAP_FIELDS)
    if audit_rows:
        write_csv(V37_AUDIT / "provider_coverage_report.csv", audit_rows, list(audit_rows[0].keys()))

    (V37_AUDIT / "provider_match_map_log.json").write_text(
        json.dumps({
            "built_at": datetime.now(timezone.utc).isoformat(),
            "rows": len(deduped),
            "audit_skipped": len(audit_rows),
            "providers": providers,
        }, indent=2),
        encoding="utf-8",
    )
    return {"rows": len(deduped), "audit_skipped": len(audit_rows)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Build V3.7 provider match map")
    ap.add_argument("--provider", default="local", help="Comma-separated providers")
    args = ap.parse_args()
    providers = [p.strip() for p in args.provider.split(",") if p.strip()]
    stats = build_provider_map(providers)
    print(f"Provider match map: {stats['rows']} rows -> {NORMALIZED_TABLES['provider_match_map']}")


if __name__ == "__main__":
    main()
