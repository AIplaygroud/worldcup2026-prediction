# -*- coding: utf-8 -*-
"""抓取/合并裁判指派 → match_officials.csv（MVP：保留种子数据，仅合并 raw 增量）。"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DB = os.path.join(HERE, "..", "database", "referee")
PROC = os.path.join(REF_DB, "processed")
RAW = os.path.join(REF_DB, "raw")
OUT = os.path.join(PROC, "match_officials.csv")

TEAM_ALIASES = {
    "United States": "USA",
    "Côte d'Ivoire": "Ivory Coast",
    "Türkiye": "Turkey",
    "Cote d'Ivoire": "Ivory Coast",
}

SOURCE_PRIORITY = {
    "FIFA": 100,
    "Reuters": 90,
    "AP": 88,
    "RefereeingWorld": 80,
    "Media": 70,
    "Social": 20,
}


def normalize_team(name: str) -> str:
    return TEAM_ALIASES.get(name.strip(), name.strip())


def _load_csv(path):
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write_csv(path, rows, fieldnames):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def merge_records(records):
    merged = {}
    conflicts = []
    for r in records:
        home = normalize_team(r.get("home", ""))
        away = normalize_team(r.get("away", ""))
        key = (home, away, r.get("date", ""))
        src = r.get("source", "Media")
        pri = SOURCE_PRIORITY.get(src, 50)
        conf = float(r.get("confidence") or 0.7)
        r = {**r, "home": home, "away": away}
        if key not in merged or pri > merged[key]["_pri"] or (
            pri == merged[key]["_pri"] and conf > merged[key]["_conf"]
        ):
            if key in merged and merged[key].get("referee") != r.get("referee"):
                conflicts.append({"key": key, "old": merged[key].get("referee"), "new": r.get("referee")})
            merged[key] = {**r, "_pri": pri, "_conf": conf}
    out = []
    for r in merged.values():
        r.pop("_pri", None)
        r.pop("_conf", None)
        out.append(r)
    return out, conflicts


def fetch_from_refereeing_world():
    # TODO: parse public HTML when automated fetch is wired
    return []


def main():
    existing = _load_csv(OUT)
    extra = []
    raw_json = os.path.join(RAW, "fifa_match_officials_raw.json")
    if os.path.isfile(raw_json):
        with open(raw_json, encoding="utf-8") as f:
            extra.extend(json.load(f))
    extra += fetch_from_refereeing_world()
    merged, conflicts = merge_records(existing + extra)
    if not merged:
        print("No records to write.")
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in merged:
        r.setdefault("fetched_at", now)
    fieldnames = list(merged[0].keys())
    _write_csv(OUT, merged, fieldnames)
    if conflicts:
        cpath = os.path.join(RAW, "conflicts.json")
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(conflicts, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(merged)} rows -> match_officials.csv")


if __name__ == "__main__":
    main()
