#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local Scheme-B provider — reads existing v37 normalized tables."""
from __future__ import annotations

from typing import Any

from eventflow_common import read_csv, snum
from v37_common import NORMALIZED_TABLES

from data_providers.provider_base import BaseProvider


class LocalProvider(BaseProvider):
    provider_name = "local"

    def __init__(self) -> None:
        self._matches = read_csv(NORMALIZED_TABLES["matches"]) if NORMALIZED_TABLES["matches"].exists() else []
        self._events = read_csv(NORMALIZED_TABLES["match_events"]) if NORMALIZED_TABLES["match_events"].exists() else []
        self._lineups = read_csv(NORMALIZED_TABLES["lineups"]) if NORMALIZED_TABLES["lineups"].exists() else []
        self._stats = read_csv(NORMALIZED_TABLES["match_stats"]) if NORMALIZED_TABLES["match_stats"].exists() else []
        self._odds = read_csv(NORMALIZED_TABLES["odds_snapshots"]) if NORMALIZED_TABLES["odds_snapshots"].exists() else []

    def _internal_from_provider_id(self, provider_match_id: str) -> str:
        for m in self._matches:
            if snum(m, "provider_match_id") == provider_match_id:
                return snum(m, "match_id")
        return ""

    def fetch_fixtures(self, season: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in self._matches:
            if season and snum(m, "season") != season:
                continue
            out.append({
                "provider": self.provider_name,
                "provider_match_id": snum(m, "provider_match_id"),
                "internal_match_id": snum(m, "match_id"),
                "home_team": m["home_team"],
                "away_team": m["away_team"],
                "kickoff_utc": m["kickoff_utc"],
                "status": m.get("status", ""),
            })
        return out

    def fetch_match_events(self, provider_match_id: str) -> list[dict[str, Any]]:
        mid = self._internal_from_provider_id(provider_match_id)
        if not mid:
            return []
        return [dict(r) for r in self._events if r.get("match_id") == mid]

    def fetch_lineups(self, provider_match_id: str) -> list[dict[str, Any]]:
        mid = self._internal_from_provider_id(provider_match_id)
        if not mid:
            return []
        return [dict(r) for r in self._lineups if r.get("match_id") == mid]

    def fetch_match_stats(self, provider_match_id: str) -> list[dict[str, Any]]:
        mid = self._internal_from_provider_id(provider_match_id)
        if not mid:
            return []
        return [dict(r) for r in self._stats if r.get("match_id") == mid]

    def fetch_odds(self, provider_match_id: str) -> list[dict[str, Any]]:
        mid = self._internal_from_provider_id(provider_match_id)
        if not mid:
            return []
        return [dict(r) for r in self._odds if r.get("match_id") == mid]
