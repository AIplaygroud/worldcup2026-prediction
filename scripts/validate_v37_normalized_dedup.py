#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate normalized tables have no duplicate merge keys."""
from __future__ import annotations

import argparse
import json
import sys

from eventflow_common import read_csv
from v37_common import NORMALIZED_TABLES
from v37_enrichment_common import MERGE_KEYS, find_duplicates


def validate_all() -> list[str]:
    errors: list[str] = []
    for table, keys in MERGE_KEYS.items():
        path = NORMALIZED_TABLES.get(table)
        if not path or not path.exists():
            continue
        rows = read_csv(path)
        dups = find_duplicates(table, rows)
        if dups:
            errors.append(f"{table}: {len(dups)} duplicate keys (e.g. {dups[0][0]})")

    if NORMALIZED_TABLES["match_events"].exists():
        events = read_csv(NORMALIZED_TABLES["match_events"])
        ft: dict[str, int] = {}
        for e in events:
            if e.get("event_type", "").lower() == "fulltime":
                mid = e["match_id"]
                ft[mid] = ft.get(mid, 0) + 1
        for mid, n in ft.items():
            if n > 1:
                errors.append(f"match_events: fulltime duplicate for {mid} ({n})")

    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate v37 normalized dedup")
    args = ap.parse_args()
    errors = validate_all()
    print(json.dumps({"ok": len(errors) == 0, "errors": errors}, indent=2))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
