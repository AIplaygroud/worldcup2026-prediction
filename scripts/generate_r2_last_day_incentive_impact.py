#!/usr/bin/env python3
"""Generate R2 last-day incentive impact notes after the G41-G44 backfill.

This is a report-layer helper.  It does not recalibrate match win probabilities
or tune model coefficients; it translates the updated live standings and best
third-place bubble into motivation / game-state implications for the remaining
R2 fixtures on 2026-06-23 (G45-G48).
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "database" / "competition"
OUT = ROOT / "outputs"
RUNTIME = COMP / "runtime"

SNAPSHOT_ID = "WC2026_GROUP_20260623_POST_G44"
SOURCE_CUTOFF = "2026-06-23T04:00:00Z"

STATE_ZH = {
    "must_win": "必须争胜",
    "must_not_lose": "不败优先",
    "control_destiny": "命运在自己手里",
    "near_clinched": "接近锁定",
    "top_slot_chase": "争第一/争路线",
    "third_place_bubble": "第三名边缘",
    "must_win_big": "必须争胜且修净胜球",
    "must_not_lose_but_win_preferred": "不能输，且更需要争胜",
    "near_clinch_with_win": "赢球接近锁定",
    "must_not_lose_or_chase_four_points": "至少不败，最好冲 4 分",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def zh_map() -> dict[str, str]:
    return {r["team_en"]: r.get("team_zh", r["team_en"]) for r in read_csv(COMP / "group_assignments.csv")}


def standings_map() -> dict[str, dict[str, str]]:
    rows = read_csv(COMP / "live_group_standings.csv")
    rows = [r for r in rows if r.get("snapshot_id") == SNAPSHOT_ID] or rows
    return {r["team"]: r for r in rows}


def group_rows(group: str) -> list[dict[str, str]]:
    rows = [r for r in read_csv(COMP / "live_group_standings.csv") if r.get("snapshot_id") == SNAPSHOT_ID and r.get("group") == group]
    return sorted(rows, key=lambda r: int(r["rank"]))


def path_map() -> dict[str, dict[str, str]]:
    rows = read_csv(COMP / "advancement_path_snapshot.csv")
    rows = [r for r in rows if r.get("snapshot_id") == SNAPSHOT_ID] or rows
    return {r["team"]: r for r in rows}


def fmt_pct(v: str | None) -> str:
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-md", type=Path, default=OUT / "r2_last_day_incentive_impact_20260623_post_g44.md")
    ap.add_argument("--out-csv", type=Path, default=RUNTIME / "r2_last_day_incentive_impact_post_g44.csv")
    args = ap.parse_args()

    zh = zh_map()
    st = standings_map()
    paths = path_map()
    fixtures = [r for r in read_csv(COMP / "wc2026_group_fixtures.csv") if r.get("fifa_match_id") in {"45", "46", "47", "48"}]
    fixtures.sort(key=lambda r: (r.get("match_date", ""), r.get("kickoff_et", ""), int(r.get("fifa_match_id", 0))))

    # Hand-authored interpretation based on the G44 live standings snapshot.  The
    # labels intentionally stay conservative and do not alter model parameters.
    notes = {
        "45": {
            "impact_level": "medium",
            "home_adjusted_incentive": "top_slot_chase",
            "away_adjusted_incentive": "top_slot_chase",
            "draw_acceptance": "medium_late_only",
            "summary": "英格兰与加纳均为 3 分，平局到 4 分通常接近安全，但 G44 后第三名池已经被 3 分队抬高，双方仍有争 6 分锁定前二和争 L 组第一的动力。",
            "eventflow_note": "若比赛末段仍平，双方平局接受度会高于 0/1 分队比赛；但开局阶段不宜降为无欲无求，仍保留争第一与路线选择权重。",
            "betting_note": "不因双方 3 分就自动判定默契平；若引用战意，应写成“平局后段接受度上升”，不是“必守平”。",
        },
        "46": {
            "impact_level": "high",
            "home_adjusted_incentive": "must_win",
            "away_adjusted_incentive": "must_win",
            "draw_acceptance": "very_low",
            "summary": "巴拿马与克罗地亚均 0 分。G44 后最好第三名实时门槛已出现多个 3 分队，双方若只拿 1 分，末轮即使赢到 4 分也可能受净胜球约束；输球一方几乎跌入淘汰边缘。",
            "eventflow_note": "应提高末段追分、开放比赛、换人冒险和防线身后空间剧本权重；不宜把平局视为双方可接受结果。",
            "betting_note": "战意层更支持分胜负或后段进球波动，但不得脱离赔率与基础概率直接下结论。",
        },
        "47": {
            "impact_level": "high",
            "home_adjusted_incentive": "must_win",
            "away_adjusted_incentive": "must_not_lose_but_win_preferred",
            "draw_acceptance": "low",
            "summary": "葡萄牙 1 分、乌兹别克斯坦 0 分。G44 后 2 分已经明显不够安全，葡萄牙若平局只到 2 分，末轮对哥伦比亚压力很大；乌兹别克斯坦输球则复制 0 分队困境。",
            "eventflow_note": "葡萄牙不能只按强队常规控球建模，需加入破低位失败后的焦躁、压上和被反击尾部；乌兹别克斯坦拿到平局时也仍有反击偷胜动机。",
            "betting_note": "战意层降低葡萄牙保守拿一分解释，增强强队主动进攻与尾部风险并存。",
        },
        "48": {
            "impact_level": "medium_high",
            "home_adjusted_incentive": "near_clinch_with_win",
            "away_adjusted_incentive": "must_not_lose_or_chase_four_points",
            "draw_acceptance": "context_dependent_on_G47",
            "summary": "哥伦比亚 3 分、刚果金 1 分。哥伦比亚赢球可到 6 分并基本锁定前二；平局到 4 分也较安全。刚果金若只平到 2 分，仍低于当前第三名安全线，若输球则末轮必须取胜。",
            "eventflow_note": "该场需要读取 G47 结果动态更新：若葡萄牙赢球，刚果金压力更大；若葡萄牙不胜，刚果金仍可通过本场取分掌控第二路径。",
            "betting_note": "赛前报告应标注“受同日早场 G47 影响”，不要用静态战意一次性锁死。",
        },
    }

    rows: list[dict[str, Any]] = []
    for fx in fixtures:
        mid = fx["fifa_match_id"]
        h = fx["home_team_en"]
        a = fx["away_team_en"]
        hn = notes[mid]
        hp = paths.get(h, {})
        apath = paths.get(a, {})
        rows.append({
            "snapshot_id": SNAPSHOT_ID,
            "source_cutoff_time": SOURCE_CUTOFF,
            "match_id": f"WC2026-{fx['group']}{mid}",
            "fifa_match_id": mid,
            "group": fx["group"],
            "match_date": fx["match_date"],
            "kickoff_et": fx["kickoff_et"],
            "home": h,
            "away": a,
            "home_points_before_match": st.get(h, {}).get("points", ""),
            "away_points_before_match": st.get(a, {}).get("points", ""),
            "home_gd_before_match": st.get(h, {}).get("gd", ""),
            "away_gd_before_match": st.get(a, {}).get("gd", ""),
            "home_p_advance_structural": hp.get("p_advance", ""),
            "away_p_advance_structural": apath.get("p_advance", ""),
            "impact_level": hn["impact_level"],
            "home_adjusted_incentive": hn["home_adjusted_incentive"],
            "away_adjusted_incentive": hn["away_adjusted_incentive"],
            "draw_acceptance_after_g44": hn["draw_acceptance"],
            "post_g44_influence_summary": hn["summary"],
            "eventflow_implication": hn["eventflow_note"],
            "betting_semantics_note": hn["betting_note"],
        })

    fields = list(rows[0].keys()) if rows else []
    write_csv(args.out_csv, rows, fields)

    thirds = [r for r in read_csv(COMP / "third_place_rankings.csv") if r.get("snapshot_id") == SNAPSHOT_ID]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines: list[str] = [
        "# R2 最后一天比赛战意影响补充分析（G44 后）",
        "",
        f"- **snapshot_id**：`{SNAPSHOT_ID}`",
        f"- **source_cutoff_time**：`{SOURCE_CUTOFF}`",
        f"- **generated_at**：`{generated_at}`",
        "- **覆盖场次**：G45 英格兰 vs 加纳、G46 巴拿马 vs 克罗地亚、G47 葡萄牙 vs 乌兹别克斯坦、G48 哥伦比亚 vs 刚果金。",
        "- **口径说明**：本报告只补充战意、平局接受度、末段追分和 EventFlow 场景解释；不直接重拟合胜平负概率、不调整 λ、不改变投注正期望判断。",
        "",
        "## 一、总体结论",
        "",
        "G41–G44 的结果对第二轮最后一天有影响，但属于 **跨组第三名门槛抬高后的间接影响**。法国、挪威、阿根廷锁定前二，以及阿尔及利亚升到 3 分第三名，使实时最好第三名池出现更多 3 分队；这会压低 K/L 组 0 分、1 分球队对平局的接受度。",
        "",
        "具体到模型层面，应做三件事：",
        "",
        "1. 对 **0 分 vs 0 分** 或 **1 分 vs 0 分** 的 R2 比赛，增强 `must_win`、`late_push`、`late_game_opening`、`transition_tail` 等 EventFlow 解释；",
        "2. 对 **3 分 vs 3 分** 的比赛，不直接写成无欲无求，仍保留争小组第一与 6 分锁定前二动机，但允许末段平局接受度上升；",
        "3. 对同一天不同开球时间的 K 组比赛，G48 哥伦比亚 vs 刚果金必须读取早场 G47 的结果后再最终解释战意。",
        "",
        "## 二、最好第三名压力变化",
        "",
        "G44 后实时第三名池的关键参照：",
        "",
        "| 排名 | 小组 | 球队 | 分 | 净胜球 | 状态 |",
        "|---:|---:|---|---:|---:|---|",
    ]
    for r in thirds[:8]:
        lines.append(f"| {r['rank_3rd']} | {r['group']} | {zh.get(r['team'], r['team'])} | {r['points']} | {r['gd']} | {r['third_place_status']} |")
    lines.extend([
        "",
        "这意味着：2 分队或 1 分队在最后一轮前不再适合被描述为“守平即可接受”；3 分但净胜球为负的球队也仍处于边缘，需要继续修净胜球。",
        "",
        "## 三、逐场影响",
        "",
        "| 场次 | 比赛 | 赛前积分 | 影响级别 | G44 后战意修正 | 平局接受度 | EventFlow 处理 |",
        "|---|---|---|---|---|---|---|",
    ])
    for r in rows:
        h_zh = zh.get(r["home"], r["home"])
        a_zh = zh.get(r["away"], r["away"])
        lines.append(
            f"| G{r['fifa_match_id']} | {h_zh} vs {a_zh} | {h_zh}{r['home_points_before_match']}分 / {a_zh}{r['away_points_before_match']}分 | "
            f"{r['impact_level']} | {STATE_ZH.get(r['home_adjusted_incentive'], r['home_adjusted_incentive'])} / {STATE_ZH.get(r['away_adjusted_incentive'], r['away_adjusted_incentive'])} | "
            f"{r['draw_acceptance_after_g44']} | {r['eventflow_implication']} |"
        )

    for r in rows:
        h_zh = zh.get(r["home"], r["home"])
        a_zh = zh.get(r["away"], r["away"])
        lines.extend(["", f"### G{r['fifa_match_id']} {h_zh} vs {a_zh}", "", r["post_g44_influence_summary"], "", f"- **模型解释**：{r['eventflow_implication']}", f"- **投注语义纪律**：{r['betting_semantics_note']}", ""])

    lines.extend([
        "## 四、对代码 / 报告层的执行建议",
        "",
        "- 预测 G45–G48 时，必须先读取 `database/competition/runtime/r2_last_day_incentive_impact_post_g44.csv`，再解释战意。",
        "- 该 CSV 的 `impact_level` 和 `draw_acceptance_after_g44` 只进入 EventFlow / 报告层，不覆盖 `predict_v2.py` 的基础 λ。",
        "- 赛中或赛前若 G47 已完赛，G48 需要重新生成一次本报告或至少人工刷新 K 组局势；禁止继续使用过时的静态战意。",
        "- 所有“第三名安全线”表述必须标注为阶段性快照，K/L 少赛导致跨组排名仍会快速变化。",
    ])

    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out_md}")
    print(f"Wrote {args.out_csv}")


if __name__ == "__main__":
    main()
