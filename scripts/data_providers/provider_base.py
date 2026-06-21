#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Base provider interface for V3.7 external data adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    provider_name: str = "base"

    @abstractmethod
    def fetch_fixtures(self, season: str) -> list[dict[str, Any]]:
        """Return normalized fixture dicts (provider schema, not model input)."""

    @abstractmethod
    def fetch_match_events(self, provider_match_id: str) -> list[dict[str, Any]]:
        """Return normalized event dicts for a provider match id."""

    @abstractmethod
    def fetch_lineups(self, provider_match_id: str) -> list[dict[str, Any]]:
        """Return normalized lineup dicts."""

    @abstractmethod
    def fetch_match_stats(self, provider_match_id: str) -> list[dict[str, Any]]:
        """Return per-team match stats."""

    @abstractmethod
    def fetch_odds(self, provider_match_id: str) -> list[dict[str, Any]]:
        """Return odds snapshot dicts."""

    def cache_dir_name(self) -> str:
        return self.provider_name
