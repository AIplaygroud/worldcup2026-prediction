#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load provider data from raw_external/{provider}/{subdir}/ cache files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from v37_common import V37_RAW_EXTERNAL


def cache_subdir(provider: str, subdir: str) -> Path:
    p = V37_RAW_EXTERNAL / provider / subdir
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_cache_file(provider: str, subdir: str, match_key: str) -> Optional[Path]:
    """Find cache file by internal_match_id (WC2026-F35) or provider id (35)."""
    base = cache_subdir(provider, subdir)
    candidates = [
        base / f"{match_key}.json",
        base / f"{match_key.upper()}.json",
    ]
    if match_key.isdigit():
        candidates.append(base / f"WC2026-{match_key.upper()}.json")
    for c in candidates:
        if c.exists():
            return c
    return None


def load_cache_list(provider: str, subdir: str, match_key: str) -> list[dict[str, Any]]:
    path = resolve_cache_file(provider, subdir, match_key)
    if not path:
        return []
    data = _read_json(path)
    if data is None:
        return []
    if isinstance(data, list):
        return [dict(x) for x in data]
    if isinstance(data, dict):
        for key in ("data", "response", "events", "lineups", "stats", "odds", "fixtures"):
            if key in data and isinstance(data[key], list):
                return [dict(x) for x in data[key]]
        if "provider_match_id" in data or "match_id" in data:
            return [dict(data)]
    return []


def list_cached_match_keys(provider: str, subdir: str = "fixtures") -> list[str]:
    base = cache_subdir(provider, subdir)
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.json"))
