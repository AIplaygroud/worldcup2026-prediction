#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enrich v37 normalized tables — P3.2 with dry-run support."""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone

from eventflow_common import read_csv, snum, write_csv
from v37_common import NORMALIZED_TABLES, V37_AUDIT, ensure_v37_dirs
from v37_enrichment_common import (
    AUDIT_FIELDS,
    MERGE_KEYS,
    build_enrichment_summary,
    dedupe_table_rows,
    merge_external_rows,
    new_run_id,
)

from data_providers.provider_apifootball import ApiFootballProvider
from data_providers.provider_local import LocalProvider
from data_providers.provider_sportmonks import SportMonksProvider
from data_providers.provider_statsbomb_open import StatsBombOpenProvider
from data_providers.provider_thestatsapi import TheStatsApiProvider

PROVIDER_CLASSES = {
    "local": LocalProvider,
    "thestatsapi": TheStatsApiProvider,
    "sportmonks": SportMonksProvider,
    "apifootball": ApiFootballProvider,
    "statsbomb_open": StatsBombOpenProvider,
}

TABLE_FIELDS = {
    "match_events": [
        "match_id", "event_id", "minute", "stoppage_minute", "team", "event_type", "player",
        "assist_player", "score_home_after", "score_away_after", "card_type", "sub_in", "sub_out",
        "source", "confirmed",
    ],
    "lineups": [
        "match_id", "team", "player_id", "player_name", "is_starter", "is_bench", "position",
        "role_group", "importance_tier", "formation_slot", "lineup_status", "source",
        "evidence_grade", "confirmed_at_utc",
    ],
    "match_stats": [
        "match_id", "team", "data_timing", "shots", "shots_on_target", "xg", "big_chances",
        "corners", "passes", "pass_accuracy", "possession", "saves", "sot_faced",
        "goals_prevented", "ppda", "field_tilt", "source", "quality_flag",
    ],
    "odds_snapshots": [
        "match_id", "market", "selection", "sp", "handicap", "total_line", "single_allowed",
        "pool_status", "provider", "fetched_at_utc", "is_opening", "is_closing",
    ],
}

FIELD_MAP = {
    "events": "match_events",
    "lineups": "lineups",
    "match_stats": "match_stats",
    "odds": "odds_snapshots",
}

FETCH_MAP = {
    "events": "fetch_match_events",
    "lineups": "fetch_lineups",
    "match_stats": "fetch_match_stats",
    "odds": "fetch_odds",
}


def _load_tables(field_names: list[str]) -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = {}
    for field in field_names:
        tk = FIELD_MAP.get(field)
        if not tk:
            continue
        path = NORMALIZED_TABLES[tk]
        tables[tk] = read_csv(path) if path.exists() else []
    return tables


def enrich(
    providers: list[str],
    fields: list[str],
    mode: str = "fill_missing_or_replace_proxy",
    run_id: str = "",
    dry_run: bool = False,
    match_filter: str = "",
) -> dict:
    ensure_v37_dirs()
    run_id = run_id or new_run_id()
    pmap = read_csv(NORMALIZED_TABLES["provider_match_map"]) if NORMALIZED_TABLES["provider_match_map"].exists() else []
    if not pmap:
        raise SystemExit("provider_match_map empty; run build_v37_provider_match_map.py first")

    audit_rows: list[dict[str, str]] = []
    tables = _load_tables(fields)

    for tk in list(tables.keys()):
        tables[tk] = dedupe_table_rows(tk, tables[tk], audit_rows, run_id=run_id, provider="pre_dedupe")

    provider_instances: dict[str, object] = {}

    for pm in pmap:
        prov_name = pm.get("provider", "")
        if prov_name not in providers:
            continue
        mid = pm["internal_match_id"]
        if match_filter and mid != match_filter:
            continue
        pid = pm.get("provider_match_id") or mid
        confidence = float(pm.get("match_confidence", 0) or 0)
        kickoff = snum(pm, "kickoff_utc")

        if prov_name not in provider_instances:
            cls = PROVIDER_CLASSES.get(prov_name)
            if not cls:
                continue
            provider_instances[prov_name] = cls()
        provider = provider_instances[prov_name]

        for field in fields:
            table_key = FIELD_MAP.get(field)
            if not table_key:
                continue
            method = getattr(provider, FETCH_MAP[field])
            ext = method(pid)
            if not ext and mid != pid:
                ext = method(mid)
            tables[table_key] = merge_external_rows(
                table_key,
                tables[table_key],
                ext,
                mid,
                prov_name,
                run_id,
                audit_rows,
                kickoff_utc=kickoff,
                match_confidence=confidence,
            )

    for tk in tables:
        tables[tk] = dedupe_table_rows(tk, tables[tk], audit_rows, run_id=run_id, provider="post_dedupe")

    summaries = []
    for prov in providers:
        prov_audit = [a for a in audit_rows if a.get("provider") == prov]
        summaries.append(build_enrichment_summary(prov_audit, run_id=run_id, provider=prov, dry_run=dry_run))

    if not dry_run:
        for tk, rows in tables.items():
            write_csv(NORMALIZED_TABLES[tk], rows, TABLE_FIELDS[tk])
        write_csv(V37_AUDIT / "provider_enrichment_audit.csv", audit_rows, AUDIT_FIELDS)
    else:
        dry_audit = V37_AUDIT / f"provider_enrichment_audit_dryrun_{run_id}.csv"
        write_csv(dry_audit, audit_rows, AUDIT_FIELDS)

    for sm in summaries:
        out = V37_AUDIT / f"provider_enrichment_summary_{sm['run_id']}.json"
        out.write_text(json.dumps(sm, ensure_ascii=False, indent=2), encoding="utf-8")

    log = {
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "providers": providers,
        "fields": fields,
        "mode": mode,
        "dry_run": dry_run,
        "audit_rows": len(audit_rows),
        "summaries": summaries,
    }
    (V37_AUDIT / "provider_enrichment_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    return log


def main() -> None:
    ap = argparse.ArgumentParser(description="Enrich V3.7 normalized tables from providers")
    ap.add_argument("--provider", default="local", help="Comma-separated providers")
    ap.add_argument("--fields", default="events,lineups,match_stats,odds")
    ap.add_argument("--mode", default="fill_missing_or_replace_proxy")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--dry-run", action="store_true", help="Simulate merge; write summary only")
    ap.add_argument("--match-id", default="", help="Limit to one internal match id")
    args = ap.parse_args()
    providers = [p.strip() for p in args.provider.split(",") if p.strip()]
    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    log = enrich(providers, fields, args.mode, args.run_id, args.dry_run, args.match_id)
    print(json.dumps(log, indent=2))


if __name__ == "__main__":
    main()
