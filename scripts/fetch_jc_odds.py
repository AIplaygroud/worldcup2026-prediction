"""Fetch China Sports Lottery (竞彩足球) World Cup odds and save to database/jc-odds/."""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.sporttery.cn/",
    "Origin": "https://www.sporttery.cn",
}
API_BASE = (
    "https://webapi.sporttery.cn/gateway/jc/football/"
    "getMatchCalculatorV1.qry?channel=c&poolCode="
)
ROOT = Path(__file__).resolve().parents[1]
ODDS_DIR = ROOT / "database" / "jc-odds"
PROCESSED = ODDS_DIR / "processed"
RAW = ODDS_DIR / "raw"

META_SKIP = {"updateDate", "updateTime", "goalLine", "goalLineValue"}
HAFU_LABELS = {
    "hh": "主/主",
    "hd": "主/平",
    "ha": "主/客",
    "dh": "平/主",
    "dd": "平/平",
    "da": "平/客",
    "ah": "客/主",
    "ad": "客/平",
    "aa": "客/客",
}
CRS_OTHER_LABELS = {
    "s1sh": "胜其他",
    "s1sd": "平其他",
    "s1sa": "负其他",
}
POOL_CODE_MAP = {
    "HAD": "had",
    "HHAD": "hhad",
    "TTG": "ttg",
    "HAFU": "hafu",
    "CRS": "crs",
}
POOL_LABELS_CN = {
    "had": "胜平负",
    "hhad": "让球胜平负",
    "ttg": "总进球",
    "hafu": "半全场",
    "crs": "比分",
}


def fetch(pool: str) -> dict:
    req = urllib.request.Request(API_BASE + pool, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def crs_key_to_score(key: str) -> str | None:
    """Map API key like s01s02 -> 1:2, or s1sh -> 胜其他."""
    if key in CRS_OTHER_LABELS:
        return CRS_OTHER_LABELS[key]
    if not key.startswith("s") or "s" not in key[1:]:
        return None
    parts = key[1:].split("s", 1)
    if len(parts) != 2:
        return None
    try:
        home = int(parts[0])
        away = int(parts[1])
    except ValueError:
        return None
    return f"{home}:{away}"


def ttg_key_to_label(key: str) -> str | None:
    if key == "s7":
        return "7+"
    if key.startswith("s") and key[1:].isdigit():
        return key[1:]
    return None


def normalize_had(raw: dict | None) -> dict | None:
    if not raw:
        return None
    return {
        "home": raw.get("h"),
        "draw": raw.get("d"),
        "away": raw.get("a"),
        "updateDate": raw.get("updateDate"),
        "updateTime": raw.get("updateTime"),
    }


def normalize_hhad(raw: dict | None) -> dict | None:
    if not raw:
        return None
    return {
        "goalLine": raw.get("goalLine"),
        "home": raw.get("h"),
        "draw": raw.get("d"),
        "away": raw.get("a"),
        "updateDate": raw.get("updateDate"),
        "updateTime": raw.get("updateTime"),
    }


def normalize_ttg(raw: dict | None) -> list[dict]:
    if not raw:
        return []
    rows = []
    for key, value in sorted(raw.items()):
        if key in META_SKIP or key.endswith("f") or not value:
            continue
        label = ttg_key_to_label(key)
        if label:
            rows.append({"goals": label, "sp": value})
    return rows


def normalize_hafu(raw: dict | None) -> list[dict]:
    if not raw:
        return []
    rows = []
    for key, value in sorted(raw.items()):
        if key in META_SKIP or not value or len(key) != 2:
            continue
        rows.append({"code": key, "label": HAFU_LABELS.get(key, key), "sp": value})
    return rows


def normalize_crs(raw: dict | None) -> list[dict]:
    if not raw:
        return []
    rows = []
    for key, value in sorted(raw.items()):
        if key in META_SKIP or key.endswith("f") or not value:
            continue
        score = crs_key_to_score(key)
        if score:
            rows.append({"score": score, "code": key, "sp": value})
    return rows


def extract_pool_meta(pool_list: list[dict] | None) -> dict[str, dict]:
    """Merge poolList entries; single=1 means 可单关购买."""
    meta: dict[str, dict] = {}
    for pl in pool_list or []:
        key = POOL_CODE_MAP.get((pl.get("poolCode") or "").upper())
        if not key:
            continue
        single_flag = max(
            int(pl.get("single") or 0),
            int(pl.get("bettingSingle") or 0),
            int(pl.get("cbtSingle") or 0),
        )
        selling = pl.get("poolStatus") == "Selling"
        if key not in meta:
            meta[key] = {"single": single_flag, "selling": selling}
        else:
            meta[key]["single"] = max(meta[key]["single"], single_flag)
            meta[key]["selling"] = meta[key]["selling"] or selling
    return meta


def merge_pool_meta(existing: dict[str, dict], incoming: dict[str, dict]) -> dict[str, dict]:
    merged = dict(existing)
    for key, info in incoming.items():
        if key not in merged:
            merged[key] = dict(info)
        else:
            merged[key]["single"] = max(merged[key]["single"], info["single"])
            merged[key]["selling"] = merged[key]["selling"] or info["selling"]
    return merged


def build_pools_block(raw: dict) -> dict[str, dict]:
    """Per-play selling and single-bet flags for agent consumption."""
    pool_meta = raw.get("_poolMeta") or {}
    pools: dict[str, dict] = {}
    for key in ("had", "hhad", "ttg", "hafu", "crs"):
        has_odds = bool(raw.get(key))
        info = pool_meta.get(key, {})
        selling = has_odds and info.get("selling", has_odds)
        pools[key] = {
            "label": POOL_LABELS_CN[key],
            "selling": selling,
            "single": bool(selling and info.get("single", 0) == 1),
        }
    return pools


def merge_matches(raw_by_pool: dict[str, dict]) -> dict[int, dict]:
    matches: dict[int, dict] = {}
    for pool, resp in raw_by_pool.items():
        if resp.get("error"):
            continue
        for day in resp.get("value", {}).get("matchInfoList", []):
            for m in day.get("subMatchList", []):
                mid = m["matchId"]
                if mid not in matches:
                    matches[mid] = {
                        "matchId": mid,
                        "matchNum": m.get("matchNum"),
                        "matchNumStr": m.get("matchNumStr", ""),
                        "matchDate": m.get("matchDate", ""),
                        "matchTime": m.get("matchTime", ""),
                        "homeTeam": m.get("homeTeamAbbName", ""),
                        "awayTeam": m.get("awayTeamAbbName", ""),
                        "homeRank": m.get("homeRank", ""),
                        "awayRank": m.get("awayRank", ""),
                        "league": m.get("leagueAbbName", ""),
                        "matchStatus": m.get("matchStatus", ""),
                        "remark": m.get("remark", ""),
                        "_poolMeta": {},
                    }
                matches[mid]["_poolMeta"] = merge_pool_meta(
                    matches[mid]["_poolMeta"],
                    extract_pool_meta(m.get("poolList")),
                )
                for key in ("had", "hhad", "crs", "ttg", "hafu"):
                    if m.get(key):
                        matches[mid][key] = m[key]
    return matches


def build_match_record(raw: dict) -> dict:
    base = {k: raw[k] for k in raw if k not in ("had", "hhad", "crs", "ttg", "hafu", "_poolMeta")}
    return {
        **base,
        "pools": build_pools_block(raw),
        "had": normalize_had(raw.get("had")),
        "hhad": normalize_hhad(raw.get("hhad")),
        "ttg": normalize_ttg(raw.get("ttg")),
        "hafu": normalize_hafu(raw.get("hafu")),
        "crs": normalize_crs(raw.get("crs")),
    }


def single_cell(pools: dict, key: str) -> str:
    p = pools.get(key) or {}
    if not p.get("selling"):
        return "未开售"
    return "是" if p.get("single") else "否"


def write_summary_csv(path: Path, records: list[dict]) -> None:
    fields = [
        "matchNumStr",
        "matchDate",
        "matchTime",
        "homeTeam",
        "awayTeam",
        "had_home",
        "had_draw",
        "had_away",
        "had_single",
        "hhad_line",
        "hhad_home",
        "hhad_draw",
        "hhad_away",
        "hhad_single",
        "ttg_count",
        "ttg_single",
        "hafu_count",
        "hafu_single",
        "crs_count",
        "crs_single",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            had = r.get("had") or {}
            hhad = r.get("hhad") or {}
            pools = r.get("pools") or {}
            writer.writerow(
                {
                    "matchNumStr": r["matchNumStr"],
                    "matchDate": r["matchDate"],
                    "matchTime": r["matchTime"],
                    "homeTeam": r["homeTeam"],
                    "awayTeam": r["awayTeam"],
                    "had_home": had.get("home", ""),
                    "had_draw": had.get("draw", ""),
                    "had_away": had.get("away", ""),
                    "had_single": single_cell(pools, "had"),
                    "hhad_line": hhad.get("goalLine", ""),
                    "hhad_home": hhad.get("home", ""),
                    "hhad_draw": hhad.get("draw", ""),
                    "hhad_away": hhad.get("away", ""),
                    "hhad_single": single_cell(pools, "hhad"),
                    "ttg_count": len(r.get("ttg") or []),
                    "ttg_single": single_cell(pools, "ttg"),
                    "hafu_count": len(r.get("hafu") or []),
                    "hafu_single": single_cell(pools, "hafu"),
                    "crs_count": len(r.get("crs") or []),
                    "crs_single": single_cell(pools, "crs"),
                }
            )


def write_detail_csv(path: Path, records: list[dict], pool: str, columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in records:
            for row in r.get(pool) or []:
                writer.writerow(
                    {
                        "matchNumStr": r["matchNumStr"],
                        "matchDate": r["matchDate"],
                        "homeTeam": r["homeTeam"],
                        "awayTeam": r["awayTeam"],
                        **row,
                    }
                )


def write_board_md(path: Path, meta: dict, records: list[dict]) -> None:
    lines = [
        "# 竞彩足球 · 世界杯在售赔率",
        "",
        f"- 数据来源: {meta['source']}",
        f"- 拉取时间: {meta['fetchedAt']}",
        f"- 官方最后更新: {meta.get('lastUpdateTime', '未知')}",
        f"- 场次范围: 在售前 {len(records)} 场（按开赛时间排序）",
        "",
        "> 仅供娱乐模拟盘分析；SP 值会变动，预测前请重新拉取。",
        "",
    ]
    for r in records:
        had = r.get("had") or {}
        hhad = r.get("hhad") or {}
        lines.append(f"## {r['matchNumStr']} {r['homeTeam']} vs {r['awayTeam']}")
        lines.append("")
        lines.append(
            f"- 开赛: {r['matchDate']} {r['matchTime']} | {r['homeRank']} vs {r['awayRank']}"
        )
        pools = r.get("pools") or {}
        single_parts = []
        for key, info in pools.items():
            if not info.get("selling"):
                single_parts.append(f"{info['label']}:未开售")
            elif info.get("single"):
                single_parts.append(f"{info['label']}:可单关")
            else:
                single_parts.append(f"{info['label']}:仅过关")
        lines.append(f"- **单关**: {' | '.join(single_parts)}")
        if had:
            lines.append(
                f"- **胜平负**: 主 {had.get('home')} | 平 {had.get('draw')} | 客 {had.get('away')}"
            )
        else:
            lines.append("- **胜平负**: 未开售")
        if hhad:
            lines.append(
                f"- **让球({hhad.get('goalLine')})**: 主 {hhad.get('home')} | "
                f"平 {hhad.get('draw')} | 客 {hhad.get('away')}"
            )
        lines.append("")
        lines.append("### 总进球 SP")
        lines.append("")
        lines.append("| 进球数 | SP |")
        lines.append("|:---:|:---:|")
        for row in r.get("ttg") or []:
            lines.append(f"| {row['goals']} | {row['sp']} |")
        lines.append("")
        lines.append("### 半全场 SP")
        lines.append("")
        lines.append("| 结果 | SP |")
        lines.append("|:---|:---:|")
        for row in r.get("hafu") or []:
            lines.append(f"| {row['label']} ({row['code']}) | {row['sp']} |")
        lines.append("")
        lines.append("### 比分 SP")
        lines.append("")
        lines.append("| 比分 | SP |")
        lines.append("|:---:|:---:|")
        for row in r.get("crs") or []:
            lines.append(f"| {row['score']} | {row['sp']} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def pull_odds(limit: int = 8) -> dict:
    pools = ["had,hhad", "crs", "ttg", "hafu"]
    raw_by_pool: dict[str, dict] = {}
    for pool in pools:
        time.sleep(1.5)
        try:
            raw_by_pool[pool] = fetch(pool)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raw_by_pool[pool] = {"error": str(exc)}

    merged = merge_matches(raw_by_pool)
    ordered = sorted(merged.values(), key=lambda m: (m["matchDate"], m["matchTime"]))
    selected = ordered[:limit]
    records = [build_match_record(m) for m in selected]

    fetched_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    last_update = (
        raw_by_pool.get("had,hhad", {})
        .get("value", {})
        .get("lastUpdateTime")
    )
    meta = {
        "source": "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry",
        "fetchedAt": fetched_at,
        "lastUpdateTime": last_update,
        "matchCount": len(records),
        "poolErrors": {k: v["error"] for k, v in raw_by_pool.items() if v.get("error")},
    }

    PROCESSED.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = RAW / f"api_snapshot_{stamp}.json"
    raw_path.write_text(
        json.dumps({"meta": meta, "rawByPool": raw_by_pool}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    payload = {"meta": meta, "matches": records}
    json_path = PROCESSED / "match_odds_top8.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    write_summary_csv(PROCESSED / "match_odds_summary.csv", records)
    write_detail_csv(
        PROCESSED / "match_odds_ttg.csv",
        records,
        "ttg",
        ["matchNumStr", "matchDate", "homeTeam", "awayTeam", "goals", "sp"],
    )
    write_detail_csv(
        PROCESSED / "match_odds_hafu.csv",
        records,
        "hafu",
        ["matchNumStr", "matchDate", "homeTeam", "awayTeam", "code", "label", "sp"],
    )
    write_detail_csv(
        PROCESSED / "match_odds_crs.csv",
        records,
        "crs",
        ["matchNumStr", "matchDate", "homeTeam", "awayTeam", "score", "code", "sp"],
    )
    write_board_md(PROCESSED / "odds_board.md", meta, records)

    return {"meta": meta, "paths": {"json": str(json_path), "raw": str(raw_path)}}


def main() -> None:
    parser = argparse.ArgumentParser(description="拉取竞彩足球世界杯在售赔率")
    parser.add_argument("--limit", type=int, default=8, help="拉取场次数（默认 8）")
    args = parser.parse_args()
    result = pull_odds(limit=args.limit)
    meta = result["meta"]
    print(f"已保存 {meta['matchCount']} 场 -> {ODDS_DIR}")
    print(f"拉取时间: {meta['fetchedAt']}")
    print(f"官方更新: {meta.get('lastUpdateTime', '未知')}")
    if meta.get("poolErrors"):
        print("警告:", meta["poolErrors"])


if __name__ == "__main__":
    main()
