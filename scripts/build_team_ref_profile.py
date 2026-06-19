# -*- coding: utf-8 -*-
"""从公平竞赛表 + team_model 构建球队判罚暴露画像 team_ref_profile.csv。"""
from __future__ import annotations

import csv
import math
import os
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DB = os.path.join(HERE, "..", "database", "referee", "processed")
XGB_DB = os.path.join(HERE, "..", "database", "xGdatabase", "processed")
FAIR_PLAY = os.path.join(HERE, "..", "database", "competition", "wc2026_fair_play_r1.csv")


def _load(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write(name, rows, fieldnames):
    path = os.path.join(REF_DB, name)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def zscore_map(values):
    if not values:
        return {k: 0.0 for k in values}
    mu = sum(values.values()) / len(values)
    var = sum((v - mu) ** 2 for v in values.values()) / max(len(values), 1)
    std = math.sqrt(var) if var > 1e-9 else 1.0
    return {k: (v - mu) / std for k, v in values.items()}


def build():
    teams = {r["team"]: r for r in _load(os.path.join(XGB_DB, "team_model.csv"))}
    fair = defaultdict(lambda: dict(yc=0.0, rc=0.0, matches=0))
    for r in _load(FAIR_PLAY):
        t = r.get("team_en", "")
        if not t:
            continue
        try:
            yc = float(r.get("yellow_cards") or 0)
            sy = float(r.get("second_yellow_reds") or 0)
            dr = float(r.get("direct_reds") or 0)
        except ValueError:
            yc = sy = dr = 0.0
        fair[t]["yc"] += yc
        fair[t]["rc"] += sy + dr
        fair[t]["matches"] += 1

    raw = {}
    for team, tm in teams.items():
        fp = fair.get(team, dict(yc=0, rc=0, matches=0))
        m = max(fp["matches"], 1)
        press = float(tm.get("pressing_intensity") or 0.55)
        trans = float(tm.get("transition_quality") or 50) / 50.0
        atk = float(tm.get("attack_power") or 50) / 50.0
        raw[team] = dict(
            matches=m,
            penalties_for90=0.0,
            penalties_against90=0.0,
            yellow_cards90=fp["yc"] / m,
            red_cards90=fp["rc"] / m,
            fouls_for90=8.0 + press * 4,
            fouls_against90=10.0,
            box_touches90=20.0 + atk * 12,
            dribbles90=8.0 + trans * 6,
            pressing_foul_risk=press,
            handball_risk=0.12,
            simulation_risk=0.10,
            ref_benefit_index=0.0,
            ref_harm_index=0.0,
            data_confidence=0.55 if fp["matches"] else 0.40,
        )

    z_keys = [
        "penalties_for90", "penalties_against90", "yellow_cards90", "red_cards90",
        "fouls_for90", "fouls_against90", "box_touches90", "dribbles90",
        "pressing_foul_risk", "handball_risk", "simulation_risk",
    ]
    zmaps = {k: zscore_map({t: raw[t][k] for t in raw}) for k in z_keys}

    today = date.today().isoformat()
    out = []
    for team, r in sorted(raw.items()):
        row = dict(
            team=team,
            period="wc2026_current",
            matches=r["matches"],
            penalties_for90=f"{r['penalties_for90']:.2f}",
            penalties_against90=f"{r['penalties_against90']:.2f}",
            yellow_cards90=f"{r['yellow_cards90']:.2f}",
            red_cards90=f"{r['red_cards90']:.2f}",
            fouls_for90=f"{r['fouls_for90']:.1f}",
            fouls_against90=f"{r['fouls_against90']:.1f}",
            box_touches90=f"{r['box_touches90']:.1f}",
            dribbles90=f"{r['dribbles90']:.1f}",
            pressing_foul_risk=f"{r['pressing_foul_risk']:.2f}",
            handball_risk=f"{r['handball_risk']:.2f}",
            simulation_risk=f"{r['simulation_risk']:.2f}",
            ref_benefit_index=f"{r['ref_benefit_index']:.2f}",
            ref_harm_index=f"{r['ref_harm_index']:.2f}",
            data_confidence=f"{r['data_confidence']:.2f}",
        )
        for k in z_keys:
            row[k + "_z"] = f"{zmaps[k][team]:.2f}"
        row["updated_at"] = today
        out.append(row)

    fields = [
        "team", "period", "matches", "penalties_for90", "penalties_against90",
        "yellow_cards90", "red_cards90", "fouls_for90", "fouls_against90",
        "box_touches90", "dribbles90", "pressing_foul_risk", "handball_risk",
        "simulation_risk", "ref_benefit_index", "ref_harm_index", "data_confidence",
    ] + [k + "_z" for k in z_keys] + ["updated_at"]
    _write("team_ref_profile.csv", out, fields)
    print(f"Wrote {len(out)} rows -> team_ref_profile.csv")


if __name__ == "__main__":
    build()
