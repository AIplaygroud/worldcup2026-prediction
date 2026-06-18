# -*- coding: utf-8 -*-
"""
2b · team_model —— 战术匹配 + 模拟级球队维度（V2.0 中间层）
==========================================================

输入：
  · player_model.csv          (2a，先跑 build_player_model.py)
  · team_recent_form.csv       (球队近期 xG)
  · opponent_strength.csv      (相对强度)
  · squad_depth_summary.csv    (GK/DF/MF/FW 人数)
  · coach_profiles.csv         (2c，可选；缺失则用中性默认)

输出：database/xGdatabase/processed/team_model.csv —— 含两类列：
  (A) 展示维度：squad_quality / squad_depth_ratio / attack_power / midfield_control /
      defensive_solidity / set_piece_strength / transition_quality / pressing_capability /
      experience_score / bench_impact / tactical_fit / form_index
  (B) λ 钩子（直接喂 predict_v2.py）：key_attacker / key_attacker_share / counter_quality /
      pressing_intensity / in_game_adaptability / depth_collapse_mult

运行：python build_team_model.py
依赖：仅标准库。
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
ROSTER = os.path.join(HERE, "..", "database", "48-team-roster", "processed")
COMP = os.path.join(HERE, "..", "database", "competition")
OUT = os.path.join(XG, "team_model.csv")


def load(path, enc="utf-8-sig"):
    if not os.path.exists(path):
        return []
    with open(path, encoding=enc) as f:
        return list(csv.DictReader(f))


def fnum(x, d=None):
    try:
        return float(x)
    except (ValueError, TypeError):
        return d


def mean(xs, d=0.0):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else d


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def main():
    players_all = load(os.path.join(XG, "player_model.csv"))
    form = {r["team"]: r for r in load(os.path.join(XG, "team_recent_form.csv"))}
    strength = {r["team"]: r for r in load(os.path.join(XG, "opponent_strength.csv"))}
    coaches = {r["team"]: r for r in load(os.path.join(COMP, "coach_profiles.csv"))}

    by_team = {}
    for p in players_all:
        by_team.setdefault(p["team"], []).append(p)

    rows = []
    for team, ps in by_team.items():
        for p in ps:
            p["_ovr"] = fnum(p["overall"], 0)
            p["_att"] = fnum(p["att_score"], 0)
            p["_def"] = fnum(p["def_score"], 0)
            p["_aer"] = fnum(p["aerial_score"], 0)
            p["_phys"] = fnum(p["phys_score"], 0)
            p["_exp"] = fnum(p["exp_score"], 0)
            p["_min"] = fnum(p["minutes"], 0) or 0

        by_ovr = sorted(ps, key=lambda r: -r["_ovr"])
        starters = by_ovr[:11]
        bench = by_ovr[11:23]
        atk = sorted(ps, key=lambda r: -r["_att"])
        fw = [p for p in ps if p["position"] == "FW"]
        mf = [p for p in ps if p["position"] == "MF"]
        df = [p for p in ps if p["position"] == "DF"]

        squad_quality = mean([p["_ovr"] for p in by_ovr[:16]])
        depth_ratio = (mean([p["_ovr"] for p in bench[:7]]) /
                       mean([p["_ovr"] for p in starters], 1)) if starters else 0.85

        attack_power = mean(sorted([p["_att"] for p in ps], reverse=True)[:4])
        midfield_control = mean(sorted([0.5 * p["_att"] + 0.5 * p["_def"] for p in mf],
                                       reverse=True)[:4]) if mf else 45
        defensive_solidity = (0.7 * mean(sorted([p["_def"] for p in df], reverse=True)[:4]) +
                              0.3 * mean(sorted([p["_aer"] for p in df], reverse=True)[:4])) if df else 50
        set_piece_strength = mean(sorted([p["_aer"] for p in ps], reverse=True)[:5])
        transition_quality = 0.5 * mean(sorted([p["_phys"] for p in fw], reverse=True)[:3] or [60]) + 0.5 * attack_power
        experience_score = mean(sorted([p["_exp"] for p in ps], reverse=True)[:16])

        # 教练（2c）
        c = coaches.get(team, {})
        pressing_intensity = fnum(c.get("pressing_intensity"), 0.50)
        adaptability = fnum(c.get("in_game_adaptability"), 0.78)
        attacking_intent = fnum(c.get("attacking_intent"), 0.55)
        set_piece_usage = fnum(c.get("set_piece_usage"), 0.50)
        coach_name = c.get("coach", "")

        pressing_capability = 100 * pressing_intensity if c else mean(sorted([p["_phys"] for p in mf], reverse=True)[:4] or [55])

        # tactical_fit：教练意图与阵容画像的对齐（越接近越契合）
        fit_attack = 1 - abs(attacking_intent - attack_power / 100.0)
        fit_press = 1 - abs(pressing_intensity - clamp(transition_quality / 100.0, 0, 1))
        tactical_fit = round(50 * (fit_attack + fit_press), 1)

        form_index = 0.0
        if team in form:
            rx = fnum(form[team]["recent_xg_per_match"], 1.3)
            si = fnum(strength.get(team, {}).get("opponent_strength_index"), 0.5)
            form_index = round(rx * (0.6 + 0.4 * si), 3)
        bench_impact = round(clamp((depth_ratio - 0.75) / 0.2, 0, 1), 3)

        # ---- λ 钩子 ----
        top4_att = sorted([p["_att"] for p in ps], reverse=True)[:4] or [0]
        key = max((p for p in ps if p["position"] in ("FW", "MF")),
                  key=lambda r: r["_att"] * (0.5 + 0.5 * min(1, r["_min"] / 2000)), default=atk[0])
        key_share = round(key["_att"] / (sum(top4_att) or 1), 3)
        counter_quality = round(clamp(0.55 + attack_power / 100.0 * 0.85, 0.5, 1.3), 3)
        depth_collapse_mult = round(clamp(0.85 + depth_ratio * 0.32, 0.85, 1.18), 3)

        conf = "stats_full" if sum(1 for p in ps if p["confidence"] == "stats_full") >= 13 else \
               ("stats_partial" if sum(1 for p in ps if p["confidence"] != "inferred") >= 10 else "inferred")

        rows.append(dict(
            team=team, team_code=ps[0].get("team_code", ""), group=ps[0].get("group", ""),
            squad_quality=round(squad_quality, 1), squad_depth_ratio=round(depth_ratio, 3),
            attack_power=round(attack_power, 1), midfield_control=round(midfield_control, 1),
            defensive_solidity=round(defensive_solidity, 1), set_piece_strength=round(set_piece_strength, 1),
            transition_quality=round(transition_quality, 1), pressing_capability=round(pressing_capability, 1),
            experience_score=round(experience_score, 1), bench_impact=bench_impact,
            tactical_fit=tactical_fit, form_index=form_index,
            key_attacker=key["player"], key_attacker_share=key_share,
            counter_quality=counter_quality, coach=coach_name,
            pressing_intensity=round(pressing_intensity, 2), in_game_adaptability=round(adaptability, 2),
            depth_collapse_mult=depth_collapse_mult, confidence=conf,
        ))

    rows.sort(key=lambda r: -r["squad_quality"])
    cols = ["team", "team_code", "group", "squad_quality", "squad_depth_ratio", "attack_power",
            "midfield_control", "defensive_solidity", "set_piece_strength", "transition_quality",
            "pressing_capability", "experience_score", "bench_impact", "tactical_fit", "form_index",
            "key_attacker", "key_attacker_share", "counter_quality", "coach",
            "pressing_intensity", "in_game_adaptability", "depth_collapse_mult", "confidence"]
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print(f"team_model.csv 写入 {len(rows)} 行 → {OUT}")
    print(f"  coach_profiles.csv {'已接入' if coaches else '未找到(用中性默认)'}")
    for t in ("France", "Senegal", "Norway", "Iraq", "Argentina", "Algeria", "Austria", "Jordan"):
        r = next((x for x in rows if x["team"] == t), None)
        if r:
            print(f"  {t:<10} 攻击力 {r['attack_power']:>5} 防守 {r['defensive_solidity']:>5} "
                  f"深度 {r['squad_depth_ratio']:.2f} 反击质量 {r['counter_quality']:.2f} "
                  f"逼抢 {r['pressing_intensity']:.2f} 适应 {r['in_game_adaptability']:.2f} "
                  f"核心 {r['key_attacker']}({r['key_attacker_share']:.2f})")


if __name__ == "__main__":
    main()
