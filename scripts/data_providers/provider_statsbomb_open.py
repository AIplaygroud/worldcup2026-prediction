#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""StatsBomb Open Data — historical training/backtest only, not live prediction."""
from __future__ import annotations

from typing import Any

from data_providers.provider_base import BaseProvider
from data_providers.provider_cache_common import load_cache_list, list_cached_match_keys


class StatsBombOpenProvider(BaseProvider):
    provider_name = "statsbomb_open"

    def fetch_fixtures(self, season: str) -> list[dict[str, Any]]:
        keys = list_cached_match_keys(self.provider_name, "matches")
        out: list[dict[str, Any]] = []
        for k in keys:
            out.extend(load_cache_list(self.provider_name, "matches", k))
        return out

    def fetch_match_events(self, provider_match_id: str) -> list[dict[str, Any]]:
        return load_cache_list(self.provider_name, "events", provider_match_id)

    def fetch_lineups(self, provider_match_id: str) -> list[dict[str, Any]]:
        return load_cache_list(self.provider_name, "lineups", provider_match_id)

    def fetch_match_stats(self, provider_match_id: str) -> list[dict[str, Any]]:
        return []

    def fetch_odds(self, provider_match_id: str) -> list[dict[str, Any]]:
        return []
