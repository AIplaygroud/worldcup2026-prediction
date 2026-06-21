#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate provider cached payloads before enrichment — P3.2."""
from __future__ import annotations

import argparse
import json
import sys

from eventflow_common import read_csv, snum
from v37_common import NORMALIZED_TABLES, V37_AUDIT, ensure_v37_dirs
from data_providers.provider_cache_common import load_cache_list
from provider_payload_validator import (
    confidence_allows_enrich,
    validate_event,
    validate_fixture,
    validate_lineup,
    validate_match_stats,
    validate_odds,
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


def validate_provider(provider_name: str, match_filter: str = "") -> dict:
    cls = PROVIDER_CLASSES.get(provider_name)
    if not cls:
        return {"provider": provider_name, "errors": ["provider_not_registered"], "ok": False}

    pmap = read_csv(NORMALIZED_TABLES["provider_match_map"]) if NORMALIZED_TABLES["provider_match_map"].exists() else []
    pmap = [p for p in pmap if p.get("provider") == provider_name]
    if match_filter:
        pmap = [p for p in pmap if p["internal_match_id"] == match_filter]

    provider = cls()
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0

    for pm in pmap:
        mid = pm["internal_match_id"]
        pid = pm.get("provider_match_id") or mid
        conf = float(pm.get("match_confidence", 0) or 0)
        kickoff = snum(pm, "kickoff_utc")
        alias_ok = snum(pm, "reason") != "team_alias_candidate" or conf >= 0.75
        ok_conf, reason = confidence_allows_enrich(conf, alias_ok)
        if not ok_conf:
            warnings.append(f"{mid}: {reason} ({conf})")
            if conf < 0.60:
                continue

        checked += 1
        fixtures = load_cache_list(provider_name, "fixtures", pid) or load_cache_list(provider_name, "fixtures", mid)
        if not fixtures:
            fixtures = [{"provider_match_id": pid, "internal_match_id": mid, "kickoff_utc": kickoff}]
        for fx in fixtures[:1]:
            errors.extend(validate_fixture(fx, mid))

        for i, ev in enumerate(provider.fetch_match_events(pid) or provider.fetch_match_events(mid)):
            errors.extend(validate_event(ev, mid, kickoff))
        for i, lu in enumerate(provider.fetch_lineups(pid) or provider.fetch_lineups(mid)):
            errs = validate_lineup(lu, mid, kickoff)
            errors.extend(errs)
            if any("post-kickoff" in e for e in errs):
                warnings.append(f"{mid}: post-kickoff lineup")
        for st in provider.fetch_match_stats(pid) or provider.fetch_match_stats(mid):
            errors.extend(validate_match_stats(st, mid))
        for od in provider.fetch_odds(pid) or provider.fetch_odds(mid):
            errors.extend(validate_odds(od, mid, kickoff))

    return {
        "provider": provider_name,
        "checked": checked,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "ok": len(errors) == 0,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate provider payloads")
    ap.add_argument("--provider", default="local")
    ap.add_argument("--match-id", default="")
    args = ap.parse_args()
    ensure_v37_dirs()
    providers = [p.strip() for p in args.provider.split(",") if p.strip()]
    results = [validate_provider(p, args.match_id) for p in providers]
    report = {
        "results": results,
        "ok": all(r["ok"] for r in results),
        "error_count": sum(r.get("error_count", 0) for r in results),
    }
    out = V37_AUDIT / "provider_payload_validation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
