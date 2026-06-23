#!/usr/bin/env python3
"""Generate a human-readable Chinese standings / advancement situation report.

The report is intentionally descriptive, not a betting recommendation.  The
advancement probabilities are structural scenario probabilities from the
project's group-state engine; they are not calibrated match win probabilities.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "database" / "competition"
OUT = ROOT / "outputs"
PHASE = OUT / "phase06_group_state"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def team_zh_map() -> dict[str, str]:
    return {r["team_en"]: r.get("team_zh", r["team_en"]) for r in read_csv(COMP / "group_assignments.csv")}


STATE_ZH = {
    "clinched_top2": "已锁定前二",
    "near_clinched": "基本安全 / 可争名次",
    "top_slot_chase": "争小组第一",
    "control_destiny": "命运在自己手里",
    "must_not_lose": "末轮不败优先",
    "third_place_bubble": "第三名资格边缘",
    "must_win": "必须取胜",
    "must_win_big": "必须取胜且尽量多净胜球",
    "eliminated": "已出局",
    "opening_round": "首轮后开放态势",
}


def get_snapshot_rows(rows: list[dict[str, str]], snapshot_id: str) -> list[dict[str, str]]:
    subset = [r for r in rows if r.get("snapshot_id") == snapshot_id]
    return subset if subset else rows


def fixture_label(row: dict[str, str], zh: dict[str, str]) -> str:
    h = row.get("home_team_en", row.get("home_team", ""))
    a = row.get("away_team_en", row.get("away_team", ""))
    mid = row.get("fifa_match_id", row.get("internal_match_id", ""))
    return f"G{mid} {zh.get(h, h)} vs {zh.get(a, a)}"


def remaining_fixtures(zh: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for r in read_csv(COMP / "wc2026_group_fixtures.csv"):
        if r.get("status") == "finished":
            continue
        label = fixture_label(r, zh)
        rnd = r.get("round", "")
        if rnd:
            label = f"R{rnd} " + label
        out[r["group"]].append(label)
    return dict(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-id", required=True)
    ap.add_argument("--standings", type=Path, default=COMP / "live_group_standings.csv")
    ap.add_argument("--paths", type=Path, default=COMP / "advancement_path_snapshot.csv")
    ap.add_argument("--third", type=Path, default=COMP / "third_place_rankings.csv")
    ap.add_argument("--out", type=Path, default=OUT / "standings_update_20260623_post_g44.md")
    args = ap.parse_args()

    zh = team_zh_map()
    standings = get_snapshot_rows(read_csv(args.standings), args.snapshot_id)
    paths = {r["team"]: r for r in get_snapshot_rows(read_csv(args.paths), args.snapshot_id)}
    thirds = get_snapshot_rows(read_csv(args.third), args.snapshot_id)
    fixtures = remaining_fixtures(zh)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cutoff = standings[0].get("source_cutoff_time", "") if standings else ""
    result_rows_used = standings[0].get("result_rows_used", "") if standings else ""

    groups = sorted({r["group"] for r in standings})
    by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in standings:
        by_group[r["group"]].append(r)
    for g in by_group:
        by_group[g].sort(key=lambda x: int(x["rank"]))

    lines: list[str] = [
        "# 2026 世界杯小组积分榜与晋级路径快照",
        "",
        f"- **snapshot_id**：`{args.snapshot_id}`",
        f"- **source_cutoff_time**：`{cutoff}`",
        f"- **generated_at**：`{generated_at}`",
        f"- **已纳入赛果数**：{result_rows_used} 场",
        "- **概率口径**：晋级路径概率来自小组状态枚举和 Annex C 第三名落位模型，是结构性情景概率，不等同于赛前胜平负校准概率。",
        "- **第三名口径**：当前第三名表是实时快照，因 K/L 等组仍少赛，跨组排名只作阶段性参照。",
        "",
        "## 一、核心变化",
        "",
        "- I 组新增法国 3-0 伊拉克、挪威 3-2 塞内加尔后，法国与挪威同积 6 分，已经锁定前二；末轮直接争小组第一。",
        "- J 组新增阿根廷 2-0 奥地利、约旦 1-2 阿尔及利亚后，阿根廷 6 分领跑并锁定前二；奥地利与阿尔及利亚末轮直接争第二，阿尔及利亚当前也进入最好第三名安全区边缘。",
        "- 塞内加尔、伊拉克、约旦均已失去前二路径，只能通过末轮取胜并争最好第三名；且净胜球压力较大。",
        "",
        "## 二、各组实时积分榜",
        "",
    ]

    for g in groups:
        lines.append(f"### {g} 组")
        lines.append("")
        lines.append("| 排名 | 球队 | 场 | 胜 | 平 | 负 | 进 | 失 | 净 | 分 | 局势 | 晋级概率 |")
        lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|")
        for r in by_group[g]:
            p = paths.get(r["team"], {})
            state = STATE_ZH.get(p.get("path_state", ""), p.get("path_state", ""))
            lines.append(
                f"| {r['rank']} | {zh.get(r['team'], r['team'])} | {r['played']} | {r['wins']} | {r['draws']} | {r['losses']} | "
                f"{r['gf']} | {r['ga']} | {r['gd']} | {r['points']} | {state} | {pct(p.get('p_advance'))} |"
            )
        if fixtures.get(g):
            lines.append("")
            lines.append("后续赛程：" + "；".join(fixtures[g]))
        lines.append("")

    lines.extend([
        "## 三、最好第三名实时排名",
        "",
        "| 第三名排名 | 小组 | 球队 | 分 | 净 | 进球 | 状态 | 预计晋级概率 |",
        "|---:|---:|---|---:|---:|---:|---|---:|",
    ])
    for r in thirds:
        p = paths.get(r["team"], {})
        lines.append(
            f"| {r['rank_3rd']} | {r['group']} | {zh.get(r['team'], r['team'])} | {r['points']} | {r['gd']} | {r['gf']} | "
            f"{r['third_place_status']} | {pct(p.get('p_best8_third'))} |"
        )

    lines.extend([
        "",
        "## 四、I/J 组晋级路径重点分析",
        "",
        "### I 组",
        "",
        "- **法国**：6 分、净胜球 +5，已锁定前二。末轮对挪威不败即可大概率以小组第一出线；若输给挪威则第二。",
        "- **挪威**：6 分、净胜球 +4，已锁定前二。末轮必须击败法国才能反超为小组第一；平局通常维持第二。",
        "- **塞内加尔**：0 分、净胜球 -3，前二已无路径。末轮必须击败伊拉克，并尽量扩大净胜球，才有最好第三名机会。",
        "- **伊拉克**：0 分、净胜球 -6，前二已无路径。末轮即使取胜也需要大幅修复净胜球，最好第三名路径很窄。",
        "",
        "### J 组",
        "",
        "- **阿根廷**：6 分、净胜球 +5，已锁定前二；在常规比分情景下基本锁定小组第一，末轮可控制节奏但仍需防极端净胜球波动。",
        "- **奥地利**：3 分、净胜球 0。末轮对阿尔及利亚不败即可守住第二；输球则大概率跌到第三并转入最好第三名比较。",
        "- **阿尔及利亚**：3 分、净胜球 -2。末轮击败奥地利即可升至第二；打平或输球则主要依赖最好第三名，当前第三名池位置尚可但不稳。",
        "- **约旦**：0 分、净胜球 -3。末轮必须击败阿根廷，同时还要争取净胜球，晋级路径属于低概率。",
        "",
        "## 五、使用建议",
        "",
        "- 赛前预测 R3 时，必须读取本快照、`advancement_path_snapshot.csv`、`third_place_rankings.csv` 与 `runtime/match_incentive_runtime_R3.csv`。",
        "- 已锁定前二球队的轮换、控分和小组第一路径要进入 EventFlow，但不得把路线选择写成确定性动机。",
        "- 第三名争夺要优先看积分、净胜球和最后一轮对手强弱；当前跨组第三名排名不可直接当最终晋级名单。",
    ])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    # Also write a stable copy under phase06 for downstream agents.
    PHASE.mkdir(parents=True, exist_ok=True)
    (PHASE / "group_situation_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
