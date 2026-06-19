# -*- coding: utf-8 -*-
"""从 referee_style_history.csv 构建裁判风格指数 referee_style_index.csv。"""
from __future__ import annotations

import csv
import math
import os
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DB = os.path.join(HERE, "..", "database", "referee", "processed")
OFFICIALS = os.path.join(REF_DB, "match_officials.csv")

COMPETITION_WEIGHT = {
    "wc2026_current": 1.60,
    "world_cup_qualifier": 1.20,
    "continental_tournament": 1.15,
    "uefa_champions_league": 1.10,
    "domestic_top5": 1.00,
    "libertadores": 0.95,
    "mls": 0.80,
    "non_big5_top": 0.75,
    "friendly": 0.45,
}

SHRINK_K = 12


def _load(name):
    path = os.path.join(REF_DB, name)
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write(name, rows, fieldnames):
    path = os.path.join(REF_DB, name)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def shrink_to_mean(value, sample_n, global_mean, k=SHRINK_K):
    if value is None:
        return global_mean
    return (sample_n * value + k * global_mean) / (sample_n + k)


def zscore(value, mean, std):
    if value is None or std <= 1e-9:
        return 0.0
    return (value - mean) / std


def all_referees():
    refs = set()
    for r in _load("match_officials.csv"):
        if r.get("referee"):
            refs.add(r["referee"])
    return sorted(refs)


def build():
    history = _load("referee_style_history.csv")
    today = date.today().isoformat()

    rows_w = []
    for r in history:
        try:
            m = float(r["matches"])
        except (ValueError, KeyError):
            continue
        if m <= 0:
            continue
        yc = float(r.get("yellow_cards") or 0)
        sy = float(r.get("second_yellows") or 0)
        rc = float(r.get("red_cards") or 0)
        pk = float(r.get("penalties") or 0)
        comp_w = COMPETITION_WEIGHT.get(r.get("competition_level", ""), 0.85)
        w = comp_w * m
        rows_w.append(dict(
            referee=r["referee"],
            weight=w,
            yc90=yc / m,
            rc90=rc / m,
            pk90=pk / m,
            card_pts90=(yc + 2 * sy + 3 * rc) / m,
            matches=m,
        ))

    by_ref = defaultdict(list)
    for row in rows_w:
        by_ref[row["referee"]].append(row)

    def weighted_mean(rs, key):
        num = sum(r["weight"] * r[key] for r in rs)
        den = sum(r["weight"] for r in rs)
        return num / den if den else None

    # 全局均值（有历史的裁判）
    refs_with_hist = [weighted_mean(rs, k) for rs in by_ref.values() for k in ("yc90", "rc90", "pk90")]
    yc_vals = [weighted_mean(rs, "yc90") for rs in by_ref.values() if weighted_mean(rs, "yc90") is not None]
    rc_vals = [weighted_mean(rs, "rc90") for rs in by_ref.values() if weighted_mean(rs, "rc90") is not None]
    pk_vals = [weighted_mean(rs, "pk90") for rs in by_ref.values() if weighted_mean(rs, "pk90") is not None]
    cp_vals = [weighted_mean(rs, "card_pts90") for rs in by_ref.values() if weighted_mean(rs, "card_pts90") is not None]

    def mean_std(vals):
        if not vals:
            return 0.0, 1.0
        mu = sum(vals) / len(vals)
        var = sum((v - mu) ** 2 for v in vals) / max(len(vals), 1)
        return mu, math.sqrt(var) if var > 1e-9 else 1.0

    g_yc, s_yc = mean_std(yc_vals)
    g_rc, s_rc = mean_std(rc_vals)
    g_pk, s_pk = mean_std(pk_vals)
    g_cp, s_cp = mean_std(cp_vals)

    out = []
    for ref in all_referees():
        rs = by_ref.get(ref, [])
        if rs:
            yc90 = weighted_mean(rs, "yc90")
            rc90 = weighted_mean(rs, "rc90")
            pk90 = weighted_mean(rs, "pk90")
            cp90 = weighted_mean(rs, "card_pts90")
            matches_weighted = sum(r["weight"] for r in rs)
            yc90 = shrink_to_mean(yc90, matches_weighted, g_yc)
            rc90 = shrink_to_mean(rc90, matches_weighted, g_rc)
            pk90 = shrink_to_mean(pk90, matches_weighted, g_pk)
            cp90 = shrink_to_mean(cp90, matches_weighted, g_cp)
            conf = min(0.90, 0.45 + matches_weighted / 40)
        else:
            yc90, rc90, pk90, cp90 = g_yc, g_rc, g_pk, g_cp
            matches_weighted = 0.0
            conf = 0.30

        yc_z = zscore(yc90, g_yc, s_yc)
        rc_z = zscore(rc90, g_rc, s_rc)
        pk_z = zscore(pk90, g_pk, s_pk)
        strictness = 0.45 * yc_z + 0.35 * rc_z + 0.20 * cp90 / max(g_cp, 0.01)
        flow = -0.5 * yc_z - 0.3 * rc_z

        out.append(dict(
            referee=ref,
            matches_weighted=f"{matches_weighted:.1f}",
            yc90_z=f"{yc_z:.2f}",
            rc90_z=f"{rc_z:.2f}",
            pk90_z=f"{pk_z:.2f}",
            var_z="0.00",
            flow_z=f"{flow:.2f}",
            strictness_index=f"{strictness:.2f}",
            penalty_tendency=f"{pk_z:.2f}",
            red_card_tendency=f"{rc_z:.2f}",
            game_flow_index=f"{flow:.2f}",
            data_confidence=f"{conf:.2f}",
            updated_at=today,
        ))

    fields = [
        "referee", "matches_weighted", "yc90_z", "rc90_z", "pk90_z", "var_z", "flow_z",
        "strictness_index", "penalty_tendency", "red_card_tendency", "game_flow_index",
        "data_confidence", "updated_at",
    ]
    _write("referee_style_index.csv", out, fields)
    print(f"Wrote {len(out)} rows -> referee_style_index.csv")


if __name__ == "__main__":
    build()
