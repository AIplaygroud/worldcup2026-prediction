#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SportMonks provider — cached JSON under raw_external/sportmonks/."""
from __future__ import annotations

from typing import Any

from data_providers.provider_base import BaseProvider
from data_providers.provider_cache_common import load_cache_list


class SportMonksProvider(BaseProvider):
    provider_name = "sportmonks"

    def fetch_fixtures(self, season: str) -> list[dict[str, Any]]:
        return load_cache_list(self.provider_name, "fixtures", season)

    def fetch_match_events(self, provider_match_id: str) -> list[dict[str, Any]]:
        return load_cache_list(self.provider_name, "events", provider_match_id)

    def fetch_lineups(self, provider_match_id: str) -> list[dict[str, Any]]:
        return load_cache_list(self.provider_name, "lineups", provider_match_id)

    def fetch_match_stats(self, provider_match_id: str) -> list[dict[str, Any]]:
        return load_cache_list(self.provider_name, "match_stats", provider_match_id)

    def fetch_odds(self, provider_match_id: str) -> list[dict[str, Any]]:
        return load_cache_list(self.provider_name, "odds", provider_match_id)
