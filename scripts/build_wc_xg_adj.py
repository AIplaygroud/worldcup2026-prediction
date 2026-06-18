# -*- coding: utf-8 -*-
"""
首轮正赛 xG 对手强度标准化
========================

问题：R1 单场 xG 受对手强弱影响（德国 4.22 揍库拉索虚高，克罗地亚 0.70 遇英格兰偏低）。
做法：用 team_recent_form 的联赛均值与对手近期 xG/xGA，把原始 WC xG 折算为
「中性对手等效 xG」，再交给 predict_v2 / build_team_model 的混合逻辑。

公式（与 predict_v2 的 deff/att 口径一致）：
  league_xg  = mean(recent_xg_per_match)   over team_recent_form.csv
  league_xga = mean(recent_xga_per_match)  over team_recent_form.csv

  对每队 R1 对手 opp（来自 wc2026_match_xg.csv）：
    deff_opp  = clamp(opp.recent_xga_per_match / league_xga, 0.70, 1.40)
    att_opp   = clamp(opp.recent_xg_per_match  / league_xg , 0.70, 1.40)
    adj_wc_xg  = round(raw_wc_xg_per_match  / deff_opp, 3)   # 弱旅防守差→下调进攻 xG
    adj_wc_xga = round(raw_wc_xga_per_match / att_opp , 3)   # 强旅进攻→下调失球 xG

clamp [0.70, 1.40] 为单场样本兜底，避免极端对手无限放大/缩小。

输入：wc2026_match_xg.csv, team_recent_form.csv, wc2026_team_xg.csv
输出：database/xGdatabase/processed/wc2026_team_xg_adj.csv

运行：python build_wc_xg_adj.py
"""

from __future__ import annotations

import csv
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
XG = os.path.join(HERE, "..", "database", "xGdatabase", "processed")
MATCH_XG = os.path.join(XG, "wc2026_match_xg.csv")
FORM = os.path.join(XG, "team_recent_form.csv")
TEAM_XG = os.path.join(XG, "wc2026_team_xg.csv")
OUT = os.path.join(XG, "wc2026_team_xg_adj.csv")

CLAMP_LO, CLAMP_HI = 0.70, 1.40
FIELDS = [
    "team", "r1_opponent",
    "raw_wc_xg", "raw_wc_xga",
    "opp_recent_xga", "opp_recent_xg",
    "deff_opp_clamped", "att_opp_clamped",
    "adj_wc_xg", "adj_wc_xga",
    "note",
]


def load_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def fnum(x, default=None):
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def league_means(form_rows: list[dict]) -> tuple[float, float]:
    xg_vals, xga_vals = [], []
    for r in form_rows:
        xg = fnum(r.get("recent_xg_per_match"))
        xga = fnum(r.get("recent_xga_per_match"))
        if xg is not None:
            xg_vals.append(xg)
        if xga is not None:
            xga_vals.append(xga)
    lx = sum(xg_vals) / len(xg_vals) if xg_vals else 1.0
    lxa = sum(xga_vals) / len(xga_vals) if xga_vals else 1.0
    return lx, lxa


def build_r1_opponents(matches: list[dict]) -> dict[str, tuple[str, float, float]]:
    """team -> (opponent, raw_xg, raw_xga) from match-level file."""
    out: dict[str, tuple[str, float, float]] = {}
    for m in matches:
        home, away = m["home_team"], m["away_team"]
        hxg, axg = fnum(m["home_xg"]), fnum(m["away_xg"])
        out[home] = (away, hxg, axg)
        out[away] = (home, axg, hxg)
    return out


def main():
    matches = load_csv(MATCH_XG)
    form = {r["team"]: r for r in load_csv(FORM)}
    wc = {r["team"]: r for r in load_csv(TEAM_XG)}
    r1_map = build_r1_opponents(matches)
    league_xg, league_xga = league_means(list(form.values()))

    rows = []
    for team in sorted(r1_map.keys()):
        opp, match_xg, match_xga = r1_map[team]
        wc_row = wc.get(team, {})
        raw_xg = fnum(wc_row.get("wc_xg_per_match"), match_xg)
        raw_xga = fnum(wc_row.get("wc_xga_per_match"), match_xga)

        note = ""
        if opp not in form:
            adj_xg, adj_xga = raw_xg, raw_xga
            deff_c, att_c = "", ""
            opp_xga, opp_xg = "", ""
            note = f"opponent {opp} missing in team_recent_form; fallback raw"
        else:
            opp_xga = fnum(form[opp]["recent_xga_per_match"])
            opp_xg = fnum(form[opp]["recent_xg_per_match"])
            deff_raw = opp_xga / league_xga if league_xga else 1.0
            att_raw = opp_xg / league_xg if league_xg else 1.0
            deff_c = round(clamp(deff_raw, CLAMP_LO, CLAMP_HI), 4)
            att_c = round(clamp(att_raw, CLAMP_LO, CLAMP_HI), 4)
            adj_xg = round(raw_xg / deff_c, 3) if deff_c else raw_xg
            adj_xga = round(raw_xga / att_c, 3) if att_c else raw_xga

        rows.append({
            "team": team,
            "r1_opponent": opp,
            "raw_wc_xg": raw_xg,
            "raw_wc_xga": raw_xga,
            "opp_recent_xga": opp_xga,
            "opp_recent_xg": opp_xg,
            "deff_opp_clamped": deff_c,
            "att_opp_clamped": att_c,
            "adj_wc_xg": adj_xg,
            "adj_wc_xga": adj_xga,
            "note": note,
        })

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"league_xg={league_xg:.4f}  league_xga={league_xga:.4f}")
    print(f"wc2026_team_xg_adj.csv 写入 {len(rows)} 行 → {OUT}")
    for t in ("Germany", "Croatia", "Switzerland", "Qatar", "Spain", "England"):
        r = next((x for x in rows if x["team"] == t), None)
        if r:
            print(f"  {t:<12} vs {r['r1_opponent']:<22} "
                  f"raw {r['raw_wc_xg']:.2f}→adj {r['adj_wc_xg']:.3f}  "
                  f"xga {r['raw_wc_xga']:.2f}→{r['adj_wc_xga']:.3f}")


if __name__ == "__main__":
    main()
