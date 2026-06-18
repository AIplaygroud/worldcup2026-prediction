# -*- coding: utf-8 -*-
"""
2a · player_model —— 五维球员评分（V2.0 自下而上地基）
======================================================

把 `squads_48_teams.csv`（含 height_cm、date_of_birth）与 `player_form_summary.csv`
（含 xg/xa per90、覆盖标记）join 起来，为每名球员产出五维评分 + overall + 置信度。

诚实原则（遵守 skill.md「禁止编造」）：
  · 进攻 attack   —— 多数 MEASURED（xg_per90 + xa_per90，按联赛档位归一化）；无数据时按位置×联赛档位 INFERRED
  · 高空 aerial   —— MEASURED（height_cm）
  · 身体 physical —— MEASURED 代理（年龄曲线 × 出场时间，年龄来自 date_of_birth）
  · 防守 defense  —— INFERRED（位置模板 × 联赛档位；我们没有抢断/拦截数据，FBref 防守表 403 封锁）
  · 履历 exp / 门将 gk —— INFERRED（年龄 + 联赛档位；caps/扑救数据缺失）

置信度分级（对齐参考模型 stats_full / stats_partial / inferred）：
  understat_big5 → stats_full；footystats/mls/supplement/fbref_fallback → stats_partial；missing → inferred

输出：database/xGdatabase/processed/player_model.csv
运行：python build_player_model.py
依赖：仅标准库。
"""

from __future__ import annotations

import csv
import datetime
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
XG = os.path.join(HERE, "..", "database", "xGdatabase", "processed")
ROSTER = os.path.join(HERE, "..", "database", "48-team-roster", "processed")
OUT = os.path.join(XG, "player_model.csv")
REF_DATE = datetime.date(2026, 6, 15)

# 联赛档位（用于跨联赛归一化球员产出；越高代表联赛越强、同样数据含金量越高）
LEAGUE_TIER = {
    # Big 5 = 1.00
    "premier league": 1.00, "epl": 1.00, "la liga": 1.00, "laliga": 1.00,
    "bundesliga": 1.00, "serie a": 1.00, "ligue 1": 1.00,
    # 次级欧洲 = 0.78
    "eredivisie": 0.78, "primeira liga": 0.78, "liga portugal": 0.78,
    "jupiler pro league": 0.72, "belgian pro league": 0.72,
    "championship": 0.68, "süper lig": 0.66, "super lig": 0.66,
    # 海湾 / 美 / 其它 = 0.50~0.62
    "saudi pro league": 0.62, "major league soccer": 0.58, "mls": 0.58,
    "usl championship": 0.45, "qatar stars league": 0.50,
    "persian gulf pro league": 0.50, "eerste divisie": 0.55,
    # 强二线/洲际主流联赛（FootyStats/补充源常见）
    "brazil serie a": 0.74, "brasileirao serie a": 0.74,
    "argentine primera": 0.70, "liga mx": 0.68,
    "swiss super league": 0.66, "austrian bundesliga": 0.62,
    "scottish premiership": 0.62, "danish superliga": 0.60,
    "czech first league": 0.58, "norwegian eliteserien": 0.56,
    "greek super league": 0.56, "uae pro league": 0.48,
    "south africa psl": 0.48, "uzbekistan super league": 0.44,
    "iraq stars league": 0.40,
}
DEFAULT_TIER = 0.52

CONF = {
    "understat_big5_2025_26": "stats_full",
    "non_big5_footystats_2025_26": "stats_partial",
    "mls_usl_asa_2026": "stats_partial",
    "non_big5_supplement_2025_26": "stats_partial",
    "fbref_big5_2024_25_fallback": "stats_partial",
    "missing": "inferred",
}


def league_tier(name: str) -> float:
    if not name:
        return DEFAULT_TIER
    key = name.strip().lower()
    if key in LEAGUE_TIER:
        return LEAGUE_TIER[key]
    # Source strings occasionally contain prefixes such as "gPremier League".
    # Prefer conservative substring matches over dropping covered rows to default.
    for label, tier in LEAGUE_TIER.items():
        if label in key:
            return tier
    return DEFAULT_TIER


def parse_age(dob: str) -> float | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            d = datetime.datetime.strptime(dob.strip(), fmt).date()
            return round((REF_DATE - d).days / 365.25, 1)
        except (ValueError, AttributeError):
            continue
    return None


def fnum(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


# ---- 各维度评分 -------------------------------------------------------------
def attack_score(xg90, xa90, pos, tier):
    """优先 MEASURED：(xg90+xa90)*联赛档位 → 0-100。无数据则位置×档位 INFERRED。"""
    if xg90 is not None and xa90 is not None:
        raw = (xg90 + xa90) * tier
        return clamp(raw * 75.0), True   # 1.2 combined per90 (big5) ≈ 90
    base = {"FW": 46, "MF": 34, "DF": 17, "GK": 7}.get(pos, 25)
    return clamp(base * (0.6 + 0.4 * tier)), False


def aerial_score(height_cm):
    if height_cm is None:
        return 45.0, False
    return clamp((height_cm - 165) / (200 - 165) * 100), True


def physical_score(age, minutes):
    if age is None:
        af = 0.85
    elif age <= 21:
        af = 0.80 + (age - 18) * 0.04
    elif age <= 29:
        af = 1.00
    elif age <= 33:
        af = 1.00 - (age - 29) * 0.06
    else:
        af = max(0.55, 0.76 - (age - 33) * 0.05)
    mf = 0.6 if minutes is None else 0.5 + 0.5 * min(1.0, minutes / 2500.0)
    return clamp(af * 100 * (0.55 + 0.45 * mf)), (age is not None)


def defense_score(pos, tier):  # INFERRED：无抢断/拦截数据
    base = {"DF": 70, "GK": 62, "MF": 50, "FW": 26}.get(pos, 40)
    return clamp(base * (0.7 + 0.3 * tier))


def experience_score(age, tier):  # INFERRED：caps 缺失，用年龄+联赛档位代理
    if age is None:
        return 45.0
    a = clamp((age - 18) * 6.0, 0, 70)
    return clamp(a + 30 * tier)


def gk_score(tier):  # INFERRED：扑救数据缺失，用联赛档位
    return clamp(30 + 45 * tier)


def overall(pos, att, aer, phys, dfn, gk):
    if pos == "GK":
        return clamp(0.65 * gk + 0.20 * aer + 0.15 * phys)
    w = {
        "FW": (0.55, 0.15, 0.20, 0.10),
        "MF": (0.40, 0.10, 0.25, 0.25),
        "DF": (0.15, 0.30, 0.25, 0.30),
    }.get(pos, (0.35, 0.20, 0.25, 0.20))
    return clamp(w[0] * att + w[1] * aer + w[2] * phys + w[3] * dfn)


def main():
    form = {}
    with open(os.path.join(XG, "player_form_summary.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            form[(r["team"], r["player"])] = r

    rows = []
    with open(os.path.join(ROSTER, "squads_48_teams.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            key = (r["team"], r["player"])
            fr = form.get(key, {})
            pos = (r.get("position") or fr.get("position") or "MF").strip()
            tier = league_tier(fr.get("league", ""))
            age = parse_age(r.get("date_of_birth", ""))
            height = fnum(r.get("height_cm"))
            minutes = fnum(fr.get("minutes"))
            xg90 = fnum(fr.get("xg_per90"))
            xa90 = fnum(fr.get("xa_per90"))

            att, att_meas = attack_score(xg90, xa90, pos, tier)
            aer, _ = aerial_score(height)
            phys, _ = physical_score(age, minutes)
            dfn = defense_score(pos, tier)
            exp = experience_score(age, tier)
            gk = gk_score(tier) if pos == "GK" else 0.0
            ovr = overall(pos, att, aer, phys, dfn, gk)
            conf = CONF.get(fr.get("source_layer", "missing"), "inferred")

            rows.append(dict(
                team=r["team"], team_code=r.get("team_code", ""), group=r.get("group", ""),
                player=r["player"], position=pos,
                age="" if age is None else age,
                height_cm="" if height is None else int(height),
                club=(fr.get("club") or r.get("club") or "").strip(),
                league=fr.get("league", ""), league_tier=round(tier, 2),
                minutes="" if minutes is None else int(minutes),
                xg_per90="" if xg90 is None else round(xg90, 3),
                xa_per90="" if xa90 is None else round(xa90, 3),
                att_score=round(att, 1), att_measured=int(att_meas),
                aerial_score=round(aer, 1), phys_score=round(phys, 1),
                def_score=round(dfn, 1), exp_score=round(exp, 1),
                gk_score=round(gk, 1), overall=round(ovr, 1), confidence=conf,
            ))

    cols = ["team", "team_code", "group", "player", "position", "age", "height_cm",
            "club", "league", "league_tier", "minutes", "xg_per90", "xa_per90",
            "att_score", "att_measured", "aerial_score", "phys_score", "def_score",
            "exp_score", "gk_score", "overall", "confidence"]
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    c = Counter(r["confidence"] for r in rows)
    meas = sum(r["att_measured"] for r in rows)
    print(f"player_model.csv 写入 {len(rows)} 行 → {OUT}")
    print(f"  置信度: {dict(c)}")
    print(f"  进攻 MEASURED(有xG): {meas} / {len(rows)}（其余 attack 为位置×联赛档位 INFERRED）")
    # 抽样校验：展示每队最强「非门将」与最强攻击手
    for t in ("France", "Argentina", "Norway", "Jordan"):
        team_rows = [r for r in rows if r["team"] == t]
        field = sorted((r for r in team_rows if r["position"] != "GK"), key=lambda r: -r["overall"])
        atk = sorted(team_rows, key=lambda r: -r["att_score"])
        print(f"  {t:<10} 最强球员: {field[0]['player']} ({field[0]['position']}) ovr={field[0]['overall']} | "
              f"最强攻击手: {atk[0]['player']} att={atk[0]['att_score']} conf={atk[0]['confidence']}")


if __name__ == "__main__":
    main()
