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
TEAM_CANONICAL_BY_ODDS_NAME = {
    "阿尔及利": ("Algeria", "ALG", "阿尔及利亚"),
    "阿尔及利亚": ("Algeria", "ALG", "阿尔及利亚"),
    "阿根廷": ("Argentina", "ARG", "阿根廷"),
    "奥地利": ("Austria", "AUT", "奥地利"),
    "巴拿马": ("Panama", "PAN", "巴拿马"),
    "波黑": ("Bosnia and Herzegovina", "BIH", "波黑"),
    "法国": ("France", "FRA", "法国"),
    "刚果(金)": ("DR Congo", "COD", "刚果金"),
    "刚果金": ("DR Congo", "COD", "刚果金"),
    "哥伦比亚": ("Colombia", "COL", "哥伦比亚"),
    "加纳": ("Ghana", "GHA", "加纳"),
    "加拿大": ("Canada", "CAN", "加拿大"),
    "捷克": ("Czechia", "CZE", "捷克"),
    "卡塔尔": ("Qatar", "QAT", "卡塔尔"),
    "克罗地亚": ("Croatia", "CRO", "克罗地亚"),
    "墨西哥": ("Mexico", "MEX", "墨西哥"),
    "南非": ("South Africa", "RSA", "南非"),
    "葡萄牙": ("Portugal", "POR", "葡萄牙"),
    "塞内加尔": ("Senegal", "SEN", "塞内加尔"),
    "瑞士": ("Switzerland", "SUI", "瑞士"),
    "乌兹别克": ("Uzbekistan", "UZB", "乌兹别克斯坦"),
    "乌兹别克斯坦": ("Uzbekistan", "UZB", "乌兹别克斯坦"),
    "伊拉克": ("Iraq", "IRQ", "伊拉克"),
    "英格兰": ("England", "ENG", "英格兰"),
    "约旦": ("Jordan", "JOR", "约旦"),
    "韩国": ("Korea Republic", "KOR", "韩国"),
    "挪威": ("Norway", "NOR", "挪威"),
}


def canonical_team(odds_name: str, all_name: str = "") -> dict:
    """Return stable team identifiers while preserving Sporttery display names."""
    team_en, team_code, team_cn = TEAM_CANONICAL_BY_ODDS_NAME.get(
        odds_name,
        TEAM_CANONICAL_BY_ODDS_NAME.get(all_name, (all_name or odds_name, "", all_name or odds_name)),
    )
    return {
        "teamCn": team_cn,
        "teamEn": team_en,
        "teamCode": team_code,
        "oddsName": odds_name,
        "apiAllName": all_name or odds_name,
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
                    home = canonical_team(
                        m.get("homeTeamAbbName", ""),
                        m.get("homeTeamAllName", ""),
                    )
                    away = canonical_team(
                        m.get("awayTeamAbbName", ""),
                        m.get("awayTeamAllName", ""),
                    )
                    matches[mid] = {
                        "matchId": mid,
                        "matchNum": m.get("matchNum"),
                        "matchNumStr": m.get("matchNumStr", ""),
                        "matchDate": m.get("matchDate", ""),
                        "matchTime": m.get("matchTime", ""),
                        "matchKey": f"{home['teamCode']}-{away['teamCode']}" if home["teamCode"] and away["teamCode"] else "",
                        "homeTeam": home["teamCn"],
                        "awayTeam": away["teamCn"],
                        "homeTeamOddsName": home["oddsName"],
                        "awayTeamOddsName": away["oddsName"],
                        "homeTeamAllName": home["apiAllName"],
                        "awayTeamAllName": away["apiAllName"],
                        "homeTeamEn": home["teamEn"],
                        "awayTeamEn": away["teamEn"],
                        "homeTeamCode": home["teamCode"],
                        "awayTeamCode": away["teamCode"],
                        "homeTeamApiCode": m.get("homeTeamCode", ""),
                        "awayTeamApiCode": m.get("awayTeamCode", ""),
                        "homeTeamApiEnName": m.get("homeTeamAbbEnName", ""),
                        "awayTeamApiEnName": m.get("awayTeamAbbEnName", ""),
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
        "matchKey",
        "matchDate",
        "matchTime",
        "homeTeam",
        "awayTeam",
        "homeTeamEn",
        "awayTeamEn",
        "homeTeamCode",
        "awayTeamCode",
        "homeTeamOddsName",
        "awayTeamOddsName",
        "homeTeamApiCode",
        "awayTeamApiCode",
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
                    "matchKey": r["matchKey"],
                    "matchDate": r["matchDate"],
                    "matchTime": r["matchTime"],
                    "homeTeam": r["homeTeam"],
                    "awayTeam": r["awayTeam"],
                    "homeTeamEn": r["homeTeamEn"],
                    "awayTeamEn": r["awayTeamEn"],
                    "homeTeamCode": r["homeTeamCode"],
                    "awayTeamCode": r["awayTeamCode"],
                    "homeTeamOddsName": r["homeTeamOddsName"],
                    "awayTeamOddsName": r["awayTeamOddsName"],
                    "homeTeamApiCode": r["homeTeamApiCode"],
                    "awayTeamApiCode": r["awayTeamApiCode"],
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
                        "matchKey": r["matchKey"],
                        "matchDate": r["matchDate"],
                        "homeTeam": r["homeTeam"],
                        "awayTeam": r["awayTeam"],
                        "homeTeamEn": r["homeTeamEn"],
                        "awayTeamEn": r["awayTeamEn"],
                        "homeTeamCode": r["homeTeamCode"],
                        "awayTeamCode": r["awayTeamCode"],
                        "homeTeamOddsName": r["homeTeamOddsName"],
                        "awayTeamOddsName": r["awayTeamOddsName"],
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
            f"- 匹配键: `{r['matchKey']}` | 英文: {r['homeTeamEn']} vs {r['awayTeamEn']} | "
            f"体彩简称: {r['homeTeamOddsName']} vs {r['awayTeamOddsName']}"
        )
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


def build_records(raw_by_pool: dict[str, dict], limit: int) -> list[dict]:
    merged = merge_matches(raw_by_pool)
    ordered = sorted(merged.values(), key=lambda m: (m["matchDate"], m["matchTime"]))
    selected = ordered[:limit]
    return [build_match_record(m) for m in selected]


def write_processed_outputs(meta: dict, records: list[dict]) -> Path:
    PROCESSED.mkdir(parents=True, exist_ok=True)

    payload = {"meta": meta, "matches": records}
    json_path = PROCESSED / "match_odds_top8.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    write_summary_csv(PROCESSED / "match_odds_summary.csv", records)
    write_detail_csv(
        PROCESSED / "match_odds_ttg.csv",
        records,
        "ttg",
        [
            "matchNumStr",
            "matchKey",
            "matchDate",
            "homeTeam",
            "awayTeam",
            "homeTeamEn",
            "awayTeamEn",
            "homeTeamCode",
            "awayTeamCode",
            "homeTeamOddsName",
            "awayTeamOddsName",
            "goals",
            "sp",
        ],
    )
    write_detail_csv(
        PROCESSED / "match_odds_hafu.csv",
        records,
        "hafu",
        [
            "matchNumStr",
            "matchKey",
            "matchDate",
            "homeTeam",
            "awayTeam",
            "homeTeamEn",
            "awayTeamEn",
            "homeTeamCode",
            "awayTeamCode",
            "homeTeamOddsName",
            "awayTeamOddsName",
            "code",
            "label",
            "sp",
        ],
    )
    write_detail_csv(
        PROCESSED / "match_odds_crs.csv",
        records,
        "crs",
        [
            "matchNumStr",
            "matchKey",
            "matchDate",
            "homeTeam",
            "awayTeam",
            "homeTeamEn",
            "awayTeamEn",
            "homeTeamCode",
            "awayTeamCode",
            "homeTeamOddsName",
            "awayTeamOddsName",
            "score",
            "code",
            "sp",
        ],
    )
    write_board_md(PROCESSED / "odds_board.md", meta, records)
    return json_path


def save_raw_snapshot(meta: dict, raw_by_pool: dict[str, dict]) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = RAW / f"api_snapshot_{stamp}.json"
    raw_path.write_text(
        json.dumps({"meta": meta, "rawByPool": raw_by_pool}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return raw_path


def build_meta(raw_by_pool: dict[str, dict], records: list[dict], fetched_at: str | None = None) -> dict:
    last_update = (
        raw_by_pool.get("had,hhad", {})
        .get("value", {})
        .get("lastUpdateTime")
    )
    return {
        "source": "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry",
        "fetchedAt": fetched_at
        or datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "lastUpdateTime": last_update,
        "matchCount": len(records),
        "poolErrors": {k: v["error"] for k, v in raw_by_pool.items() if v.get("error")},
    }


def pull_odds(limit: int = 8) -> dict:
    pools = ["had,hhad", "crs", "ttg", "hafu"]
    raw_by_pool: dict[str, dict] = {}
    for pool in pools:
        time.sleep(1.5)
        try:
            raw_by_pool[pool] = fetch(pool)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raw_by_pool[pool] = {"error": str(exc)}

    records = build_records(raw_by_pool, limit)
    meta = build_meta(raw_by_pool, records)
    raw_path = save_raw_snapshot(meta, raw_by_pool)
    if not records:
        return {
            "meta": meta,
            "paths": {"raw": str(raw_path)},
            "processedSkipped": True,
        }

    json_path = write_processed_outputs(meta, records)

    return {"meta": meta, "paths": {"json": str(json_path), "raw": str(raw_path)}}


def restore_from_raw(raw_path: Path, limit: int = 8) -> dict:
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    raw_by_pool = payload["rawByPool"]
    records = build_records(raw_by_pool, limit)
    if not records:
        raise RuntimeError(f"raw snapshot has no recoverable matches: {raw_path}")
    meta = build_meta(
        raw_by_pool,
        records,
        fetched_at=payload.get("meta", {}).get("fetchedAt"),
    )
    json_path = write_processed_outputs(meta, records)
    return {"meta": meta, "paths": {"json": str(json_path), "raw": str(raw_path)}}


def main() -> None:
    parser = argparse.ArgumentParser(description="拉取竞彩足球世界杯在售赔率")
    parser.add_argument("--limit", type=int, default=8, help="拉取场次数（默认 8）")
    parser.add_argument("--from-raw", type=Path, help="从已有 raw/api_snapshot_*.json 重建 processed 表")
    args = parser.parse_args()
    if args.from_raw:
        result = restore_from_raw(args.from_raw, limit=args.limit)
    else:
        result = pull_odds(limit=args.limit)
    meta = result["meta"]
    if result.get("processedSkipped"):
        print(f"接口未返回可用场次，已保留现有 processed，仅保存 raw -> {ODDS_DIR}")
    else:
        print(f"已保存 {meta['matchCount']} 场 -> {ODDS_DIR}")
    print(f"拉取时间: {meta['fetchedAt']}")
    print(f"官方更新: {meta.get('lastUpdateTime', '未知')}")
    if meta.get("poolErrors"):
        print("警告:", meta["poolErrors"])


if __name__ == "__main__":
    main()
