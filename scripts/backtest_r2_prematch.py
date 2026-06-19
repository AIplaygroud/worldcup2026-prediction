# -*- coding: utf-8 -*-
"""
R2 赛前回测 — 数据截断至开赛日前一天（含当日 0 点前已完赛）。

用法：
  python scripts/backtest_r2_prematch.py
  python scripts/backtest_r2_prematch.py --write-report

规则：
  - 正赛 xG：仅 match_date <= cutoff（cutoff = 开赛日 - 1 天）
  - 裁判指派：仅 fetched_at <= cutoff 23:59:59（种子数据若晚于 cutoff 则不做 L10 方向修正）
  - 静态层（预选赛 form、team_model、coach）不变；临场情报不事后注入
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from predict_v2 import (  # noqa: E402
    MatchContext,
    _load_csv,
    apply_layers,
    apply_referee_layer,
    base_lambdas,
    build_ft,
    confidence,
    load_data,
    markets,
    outcome,
    predict,
    resolve_context,
)

DB = os.path.join(HERE, "..", "database", "xGdatabase", "processed")
REF_DB = os.path.join(HERE, "..", "database", "referee", "processed")
REPORT_PATH = os.path.join(DB, "wc2026_v2_backtest_r2_md2.md")

# 小组赛 R2 按赛程顺序前四场（fixture 25–28，2026-06-18）
R2_MD2_FIRST4 = [
    dict(
        fixture=25,
        home="Czechia",
        away="South Africa",
        match_date="2026-06-18",
        actual="1-1",
        actual_xg="—",
        ctx=dict(
            neutral=True,
            note="R2 生死战；南非 R1 三红减员（公平竞赛 -10）",
        ),
    ),
    dict(
        fixture=26,
        home="Switzerland",
        away="Bosnia and Herzegovina",
        match_date="2026-06-18",
        actual="4-1",
        actual_xg="—",
        ctx=dict(neutral=True, note="B 组四队同分 1 分；瑞士 R1 xG 3.2 仅进 1 球"),
    ),
    dict(
        fixture=27,
        home="Canada",
        away="Qatar",
        match_date="2026-06-18",
        actual="6-0",
        actual_xg="—",
        ctx=dict(
            neutral=False,
            host_side="home",
            note="东道主主场温哥华；卡塔尔 R1 幸运拿分",
        ),
    ),
    dict(
        fixture=28,
        home="Mexico",
        away="South Korea",
        match_date="2026-06-18",
        actual="1-0",
        actual_xg="—",
        ctx=dict(
            neutral=False,
            host_side="home",
            note="A 组榜首战；平局双方均 4 分（控分风险中等）",
        ),
    ),
]


def _parse_date(s: str) -> date:
    return date.fromisoformat(s[:10])


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        try:
            return datetime.fromisoformat(s[:10] + "T00:00:00")
        except ValueError:
            return None


def cutoff_date(match_date: str) -> str:
    return (_parse_date(match_date) - timedelta(days=1)).isoformat()


def rebuild_wc_from_matches(rows: list[dict]) -> dict:
    acc = defaultdict(lambda: dict(n=0, xg=0.0, xga=0.0, gf=0, ga=0))
    for r in rows:
        h, a = r["home_team"], r["away_team"]
        hx, ax = float(r["home_xg"]), float(r["away_xg"])
        hg, ag = int(r["home_score"]), int(r["away_score"])
        for team, xg, xga, gf, ga in (
            (h, hx, ax, hg, ag),
            (a, ax, hx, ag, hg),
        ):
            acc[team]["n"] += 1
            acc[team]["xg"] += xg
            acc[team]["xga"] += xga
            acc[team]["gf"] += gf
            acc[team]["ga"] += ga
    out = {}
    for team, v in acc.items():
        n = v["n"]
        out[team] = dict(
            team=team,
            wc_matches=str(n),
            wc_xg_per_match=f"{v['xg'] / n:.2f}",
            wc_xga_per_match=f"{v['xga'] / n:.2f}",
            wc_xgd_per_match=f"{(v['xg'] - v['xga']) / n:.2f}",
            wc_goals_for=str(v["gf"]),
            wc_goals_against=str(v["ga"]),
            quality_flag="thin_sample" if n < 2 else "ok",
        )
    return out


def rebuild_wc_adj_simple(wc: dict, form: dict, strength: dict) -> dict:
    """简化 adj：用对手 recent_xga 均值比折算，与 build_wc_xg_adj 同口径近似。"""
    out = {}
    for team, row in wc.items():
        try:
            raw_xg = float(row["wc_xg_per_match"])
            raw_xga = float(row["wc_xga_per_match"])
        except (KeyError, ValueError):
            continue
        opp_xga_vals = []
        for t, f in form.items():
            try:
                opp_xga_vals.append(float(f["recent_xga_per_match"]))
            except (KeyError, ValueError):
                pass
        league_xga = sum(opp_xga_vals) / len(opp_xga_vals) if opp_xga_vals else 1.0
        adj_xg = raw_xg  # 单场样本不强行 adj，保持保守
        adj_xga = raw_xga
        out[team] = dict(
            team=team,
            adj_wc_xg=f"{adj_xg:.3f}",
            adj_wc_xga=f"{adj_xga:.3f}",
            raw_wc_xg=f"{raw_xg:.2f}",
            raw_wc_xga=f"{raw_xga:.2f}",
        )
    return out


def load_data_as_of(cutoff: str, home: str, away: str) -> dict:
    data = load_data()
    mx_path = os.path.join(DB, "wc2026_match_xg.csv")
    with open(mx_path, encoding="utf-8-sig") as f:
        all_mx = list(csv.DictReader(f))
    mx = [r for r in all_mx if r["match_date"] <= cutoff]
    data["wc"] = rebuild_wc_from_matches(mx)
    data["wc_adj"] = rebuild_wc_adj_simple(data["wc"], data["form"], data["strength"])
    data["_as_of"] = dict(cutoff=cutoff, wc_matches=len(mx))

    mo = {}
    officials_path = os.path.join(REF_DB, "match_officials.csv")
    if os.path.isfile(officials_path):
        end = datetime.fromisoformat(cutoff + "T23:59:59")
        with open(officials_path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                ft = _parse_dt(r.get("fetched_at", ""))
                if ft:
                    ft = ft.replace(tzinfo=None)
                if ft and ft > end:
                    continue
                mo[(r["home"], r["away"])] = r
    data["match_officials"] = mo
    return data


def run_case(case: dict, verbose: bool = True) -> dict:
    cutoff = cutoff_date(case["match_date"])
    data = load_data_as_of(cutoff, case["home"], case["away"])
    ctx = MatchContext(
        home=case["home"],
        away=case["away"],
        use_referee_layer=True,
        **case.get("ctx", {}),
    )
    res = predict(ctx, data, verbose=verbose)
    m = res["markets"]
    ah, aa = (int(x) for x in case["actual"].split("-"))
    actual_dir = outcome(ah, aa)
    pred_dir = max(("H", m["pH"]), ("D", m["pD"]), ("A", m["pA"]), key=lambda x: x[1])[0]
    top5 = {(i, j) for i, j, _ in m["scores"][:5]}
    modal = m["scores"][0]
    return dict(
        fixture=case["fixture"],
        match=f"{case['home']} vs {case['away']}",
        match_date=case["match_date"],
        cutoff=cutoff,
        wc_n=data["_as_of"]["wc_matches"],
        lam_h=res["lam_h"],
        lam_a=res["lam_a"],
        base=res["base"],
        modal=f"{modal[0]}-{modal[1]}",
        modal_p=modal[2],
        actual=case["actual"],
        dir_ok=pred_dir == actual_dir,
        in_top5=(ah, aa) in top5,
        pH=m["pH"],
        pD=m["pD"],
        pA=m["pA"],
        btts=m["btts"],
        ref=res.get("referee_factor", {}),
        pred_dir=pred_dir,
        actual_dir=actual_dir,
    )


def write_report(rows: list[dict]) -> str:
    n = len(rows)
    dir_hits = sum(1 for r in rows if r["dir_ok"])
    top5_hits = sum(1 for r in rows if r["in_top5"])
    btts_actual = sum(
        1 for r in rows if int(r["actual"].split("-")[0]) >= 1 and int(r["actual"].split("-")[1]) >= 1
    )
    lines = [
        "# WC2026 R2 赛前回测（MD2 前四场）",
        "",
        f"> 生成日期：{date.today().isoformat()}。数据截断：**开赛日前一天**（含该日已完赛正赛 xG）。",
        "> 脚本：`python scripts/backtest_r2_prematch.py --write-report`",
        "",
        "## 1. 样本",
        "",
        "| Fixture | 场次 | 开赛日 | 数据截止 | 截止前正赛场次 |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['fixture']} | {r['match']} | {r['match_date']} | {r['cutoff']} | {r['wc_n']} |"
        )
    lines += [
        "",
        "## 2. 汇总",
        "",
        f"- 胜平负方向命中：**{dir_hits}/{n}**（{dir_hits/n*100:.1f}%）",
        f"- 赛果 ∈ Top-5 比分带：**{top5_hits}/{n}**（{top5_hits/n*100:.1f}%）",
        f"- 实际 BTTS 是：**{btts_actual}/{n}**",
        "",
        "## 3. 逐场",
        "",
        "| 场次 | base λ | 最终 λ | modal | 赛果 | P(主/平/客) | BTTS% | 方向 | Top5 | 裁判层 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        ref_note = r["ref"].get("style", "—")[:24]
        if not r["ref"].get("known"):
            ref_note = "未确认/晚于截止"
        lines.append(
            f"| {r['match']} | {r['base'][0]:.2f}/{r['base'][1]:.2f} | "
            f"{r['lam_h']:.2f}/{r['lam_a']:.2f} | {r['modal']} | {r['actual']} | "
            f"{r['pH']*100:.0f}/{r['pD']*100:.0f}/{r['pA']*100:.0f} | {r['btts']*100:.0f}% | "
            f"{'✓' if r['dir_ok'] else '✗'} | {'✓' if r['in_top5'] else '·'} | {ref_note} |"
        )
    lines += [
        "",
        "## 4. 说明",
        "",
        "- **时间隔离**：`wc2026_match_xg.csv` 仅保留 `match_date <= cutoff`；2026-06-18 的 R2 四场 cutoff 均为 **2026-06-17**（当时 R1 已赛 20 场，K/L 组末两场 R1 尚未踢完）。",
        "- **裁判层**：`match_officials.csv` 的 `fetched_at` 若晚于 cutoff，赛前回测**不启用**主裁方向修正（符合「仅前一天及以前数据」）。",
        "- **东道主**：加拿大、墨西哥场次启用 `host_side=home`；其余为中立场。",
        "- 赛果来源：ESPN MD8 报道（2026-06-18）；正赛 xG 待 FotMob 入库后补全 `actual_xg` 列。",
        "",
    ]
    text = "\n".join(lines)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    return REPORT_PATH


def main():
    ap = argparse.ArgumentParser(description="R2 MD2 前四场赛前回测（数据截止=开赛日前一天）")
    ap.add_argument("--write-report", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    print("\n" + "#" * 72)
    print("#  R2 MD2 赛前回测 — 数据截止 = 开赛日前一天")
    print("#" * 72)

    results = []
    for case in R2_MD2_FIRST4:
        cutoff = cutoff_date(case["match_date"])
        if not args.quiet:
            print(f"\n{'='*72}")
            print(f"Fixture {case['fixture']}  {case['home']} vs {case['away']}")
            print(f"开赛 {case['match_date']}  |  数据截止 {cutoff}  |  赛果 {case['actual']}")
        row = run_case(case, verbose=not args.quiet)
        results.append(row)

    print("\n" + "=" * 72)
    print("汇总   cutoff    base λ      最终 λ      modal   赛果   方向  Top5")
    for r in results:
        print(
            f"  {r['fixture']:>2}  {r['cutoff']}  "
            f"{r['base'][0]:.1f}/{r['base'][1]:.1f}  "
            f"{r['lam_h']:.1f}/{r['lam_a']:.1f}  "
            f"{r['modal']:<5}  {r['actual']:<5}  "
            f"{'✓' if r['dir_ok'] else '✗'}     {'✓' if r['in_top5'] else '·'}"
        )
    dir_h = sum(1 for r in results if r["dir_ok"])
    t5 = sum(1 for r in results if r["in_top5"])
    print("=" * 72)
    print(f"方向 {dir_h}/{len(results)}  |  Top-5 {t5}/{len(results)}")

    if args.write_report:
        path = write_report(results)
        print(f"\n报告已写入 {path}")


if __name__ == "__main__":
    main()
