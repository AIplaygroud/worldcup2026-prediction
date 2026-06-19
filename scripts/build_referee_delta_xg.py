# -*- coding: utf-8 -*-
"""汇总 decision_events.csv → 球队/球员/裁判判罚 ΔxG 榜。"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DB = os.path.join(HERE, "..", "database", "referee", "processed")

CONTROVERSY_W = {"low": 0.3, "medium": 0.5, "high": 0.8}


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


def fnum(row, key, default=0.0):
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def build():
    events = _load("decision_events.csv")
    today = date.today().isoformat()

    team_acc = defaultdict(lambda: dict(
        matches=set(), benefit=0.0, harm=0.0, bxp=0.0, hxp=0.0,
        pen_net=0.0, red_net=0.0, var_net=0.0, controversy=0.0, n=0,
    ))
    player_acc = defaultdict(lambda: dict(
        team="", events=0, benefit=0.0, harm=0.0, pen_w=0, pen_c=0,
        red_drawn=0, cards=0, controversy=0.0,
    ))
    ref_acc = defaultdict(lambda: dict(
        matches=set(), abs_dxg=0.0, penalties=0, reds=0, var_ov=0,
        controversy=0.0, n=0,
    ))

    for ev in events:
        dxg = fnum(ev, "direct_xg_delta")
        xpf = fnum(ev, "xpoints_delta_for")
        xpa = fnum(ev, "xpoints_delta_against")
        cw = CONTROVERSY_W.get(ev.get("controversy_level", "medium"), 0.5)
        conf = fnum(ev, "confidence", 0.5)
        tf, ta = ev.get("team_for", ""), ev.get("team_against", "")
        ref = ev.get("referee", "")
        et = ev.get("event_type", "")

        if tf:
            team_acc[tf]["matches"].add(ev.get("match_id", ""))
            if dxg > 0:
                team_acc[tf]["benefit"] += dxg
            else:
                team_acc[tf]["harm"] += abs(dxg)
            team_acc[tf]["bxp"] += max(xpf, 0)
            team_acc[tf]["hxp"] += max(-xpf, 0)
            team_acc[tf]["controversy"] += cw * conf
            team_acc[tf]["n"] += 1
            if et == "penalty_awarded":
                team_acc[tf]["pen_net"] += 1
        if ta:
            team_acc[ta]["matches"].add(ev.get("match_id", ""))
            if dxg < 0:
                team_acc[ta]["harm"] += abs(dxg)
            team_acc[ta]["hxp"] += max(xpa, 0)
            team_acc[ta]["controversy"] += cw * conf
            team_acc[ta]["n"] += 1
            if et == "penalty_awarded":
                team_acc[ta]["pen_net"] -= 1

        pf = ev.get("player_for", "")
        if pf:
            pa = player_acc[pf]
            pa["team"] = tf
            pa["events"] += 1
            if dxg > 0:
                pa["benefit"] += dxg
            else:
                pa["harm"] += abs(dxg)
            if et == "penalty_awarded":
                pa["pen_w"] += 1
            pa["controversy"] += cw * conf

        if ref:
            ra = ref_acc[ref]
            ra["matches"].add(ev.get("match_id", ""))
            ra["abs_dxg"] += abs(dxg)
            ra["controversy"] += cw
            ra["n"] += 1
            if et == "penalty_awarded":
                ra["penalties"] += 1
            if "red" in et:
                ra["reds"] += 1
            if ev.get("after_var", "").lower() == "true":
                ra["var_ov"] += 1

    team_rows = []
    for team, a in sorted(team_acc.items()):
        net = a["benefit"] - a["harm"]
        team_rows.append(dict(
            team=team,
            matches=len(a["matches"]),
            benefit_dxg=f"{a['benefit']:.2f}",
            harm_dxg=f"{a['harm']:.2f}",
            net_dxg=f"{net:.2f}",
            benefit_xpoints=f"{a['bxp']:.2f}",
            harm_xpoints=f"{a['hxp']:.2f}",
            net_xpoints=f"{a['bxp'] - a['hxp']:.2f}",
            penalty_net=f"{a['pen_net']:.2f}",
            red_card_net=f"{a['red_net']:.2f}",
            var_net=f"{a['var_net']:.2f}",
            controversy_weighted=f"{a['controversy'] / max(a['n'], 1):.2f}",
            updated_at=today,
        ))

    player_rows = []
    for player, a in sorted(player_acc.items()):
        net = a["benefit"] - a["harm"]
        player_rows.append(dict(
            player=player,
            team=a["team"],
            events=a["events"],
            benefit_dxg=f"{a['benefit']:.2f}",
            harm_dxg=f"{a['harm']:.2f}",
            net_dxg=f"{net:.2f}",
            penalties_won=a["pen_w"],
            penalties_conceded=a["pen_c"],
            red_cards_drawn=a["red_drawn"],
            cards_received=a["cards"],
            controversy_weighted=f"{a['controversy'] / max(a['events'], 1):.2f}",
        ))

    ref_rows = []
    for ref, a in sorted(ref_acc.items()):
        ref_rows.append(dict(
            referee=ref,
            matches=len(a["matches"]),
            total_abs_dxg=f"{a['abs_dxg']:.2f}",
            total_net_home_dxg="0.00",
            total_net_fav_dxg="0.00",
            penalties=a["penalties"],
            reds=a["reds"],
            var_overturns=a["var_ov"],
            avg_controversy=f"{a['controversy'] / max(a['n'], 1):.2f}",
            impact_index=f"{a['abs_dxg']:.2f}",
            data_confidence="0.70",
        ))

    _write("team_ref_delta_xg.csv", team_rows, [
        "team", "matches", "benefit_dxg", "harm_dxg", "net_dxg",
        "benefit_xpoints", "harm_xpoints", "net_xpoints",
        "penalty_net", "red_card_net", "var_net", "controversy_weighted", "updated_at",
    ])
    _write("player_ref_delta_xg.csv", player_rows, [
        "player", "team", "events", "benefit_dxg", "harm_dxg", "net_dxg",
        "penalties_won", "penalties_conceded", "red_cards_drawn", "cards_received",
        "controversy_weighted",
    ])
    _write("referee_impact_summary.csv", ref_rows, [
        "referee", "matches", "total_abs_dxg", "total_net_home_dxg", "total_net_fav_dxg",
        "penalties", "reds", "var_overturns", "avg_controversy", "impact_index", "data_confidence",
    ])
    print(f"team={len(team_rows)} player={len(player_rows)} referee={len(ref_rows)}")


if __name__ == "__main__":
    build()
