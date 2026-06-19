#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Common helpers for WorldCup2026 EventFlow V3.0.

This module intentionally uses only the Python standard library so it can be
copied into the existing prediction-skill repository without dependency churn.
"""
from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database"
EVENTFLOW_DB = DB / "eventflow" / "processed"
PLAYER_DB = DB / "player_style" / "processed"
TEAM_DB = DB / "team_style" / "processed"
SOURCE_DB = DB / "source_registry" / "processed"

TEAM_ALIASES = {
    "USA": "United States",
    "USMNT": "United States",
    "Türkiye": "Turkey",
    "Turkey": "Turkey",
    "Korea Republic": "South Korea",
    "Korea Rep": "South Korea",
    "Czech Republic": "Czechia",
    "Cote d'Ivoire": "Ivory Coast",
    "Côte d’Ivoire": "Ivory Coast",
    "DR Congo": "DR Congo",
    "Congo DR": "DR Congo",
    "Saudi": "Saudi Arabia",
    "Cabo Verde": "Cape Verde",
}

HTFT_LABELS = ["胜/胜", "胜/平", "胜/负", "平/胜", "平/平", "平/负", "负/胜", "负/平", "负/负"]


def normalize_team(name: str) -> str:
    name = (name or "").strip()
    return TEAM_ALIASES.get(name, name)


def ensure_parent(path: os.PathLike[str] | str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def read_csv(path: os.PathLike[str] | str) -> List[Dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: os.PathLike[str] | str, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    p = Path(path)
    ensure_parent(p)
    if fieldnames is None:
        keys: List[str] = []
        for row in rows:
            for k in row.keys():
                if k not in keys:
                    keys.append(k)
        fieldnames = keys
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: _format_value(row.get(k, "")) for k in fieldnames})


def read_json(path: os.PathLike[str] | str, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: os.PathLike[str] | str, obj: Any) -> None:
    p = Path(path)
    ensure_parent(p)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _format_value(v: Any) -> Any:
    if isinstance(v, float):
        return f"{v:.6f}".rstrip("0").rstrip(".")
    return v


def fnum(row: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        v = row.get(key, default)
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def snum(row: Mapping[str, Any], key: str, default: str = "") -> str:
    v = row.get(key, default)
    if v is None:
        return default
    return str(v).strip()


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if abs(b) > 1e-12 else default


def zscore(value: float, mean: float, std: float) -> float:
    if std <= 1e-12:
        return 0.0
    return (value - mean) / std


def add_zscores(rows: List[MutableMapping[str, Any]], cols: Sequence[str], suffix: str = "_z") -> List[MutableMapping[str, Any]]:
    for col in cols:
        vals = [fnum(r, col) for r in rows if snum(r, col) != ""]
        if not vals:
            for r in rows:
                r[col + suffix] = 0.0
            continue
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1)
        std = math.sqrt(var)
        for r in rows:
            r[col + suffix] = zscore(fnum(r, col), mean, std)
    return rows


def shrink_to_mean(value: float, sample_n: float, global_mean: float, k: float = 10.0) -> float:
    return (sample_n * value + k * global_mean) / (sample_n + k) if sample_n + k > 0 else global_mean


def time_decay_weight(days_ago: int, half_life_days: float = 365.0) -> float:
    days_ago = max(0, int(days_ago))
    return 0.5 ** (days_ago / half_life_days)


def parse_date(s: str, default: date | None = None) -> date | None:
    s = (s or "").strip()
    if not s:
        return default
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return default


def days_between(d: str, ref: date | None = None) -> int:
    ref = ref or date.today()
    got = parse_date(d)
    if got is None:
        return 365
    return max(0, (ref - got).days)


def groupby(rows: Iterable[Mapping[str, Any]], key: str) -> Dict[str, List[Mapping[str, Any]]]:
    d: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        d[snum(r, key)].append(r)
    return dict(d)


def weighted_mean(rows: Iterable[Mapping[str, Any]], value_key: str, weight_key: str = "weight", default: float = 0.0) -> float:
    num = 0.0
    den = 0.0
    for r in rows:
        w = fnum(r, weight_key, 1.0)
        v = fnum(r, value_key, default)
        num += w * v
        den += w
    return safe_div(num, den, default)


def score_to_result(score: str) -> str:
    """Return Chinese W/D/L label from home perspective."""
    try:
        h, a = score.split("-")
        h_i, a_i = int(h), int(a)
    except Exception:
        return "平"
    if h_i > a_i:
        return "胜"
    if h_i < a_i:
        return "负"
    return "平"


def htft_label(ht_score: str, ft_score: str) -> str:
    return f"{score_to_result(ht_score)}/{score_to_result(ft_score)}"


def poisson_pmf(lam: float, max_goals: int = 7) -> List[float]:
    lam = max(0.01, lam)
    vals = []
    for k in range(max_goals):
        vals.append(math.exp(-lam) * lam**k / math.factorial(k))
    vals.append(max(0.0, 1.0 - sum(vals)))
    return vals


def top_score_distribution(lam_home: float, lam_away: float, max_goals: int = 7) -> List[Dict[str, Any]]:
    ph = poisson_pmf(lam_home, max_goals)
    pa = poisson_pmf(lam_away, max_goals)
    out = []
    for i, p_i in enumerate(ph):
        for j, p_j in enumerate(pa):
            out.append({"score": f"{i}-{j}", "probability": p_i * p_j})
    return sorted(out, key=lambda x: x["probability"], reverse=True)


def normalize_weights(items: List[MutableMapping[str, Any]], key: str = "weight") -> List[MutableMapping[str, Any]]:
    s = sum(max(0.0, fnum(x, key)) for x in items)
    if s <= 1e-12:
        n = len(items) or 1
        for x in items:
            x[key] = 1.0 / n
        return items
    for x in items:
        x[key] = max(0.0, fnum(x, key)) / s
    return items
