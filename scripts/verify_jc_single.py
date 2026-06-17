"""Verify single-bet (单关) flags in jc-odds against live sporttery API."""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "database" / "jc-odds" / "processed"
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_jc_odds import (  # noqa: E402
    POOL_CODE_MAP,
    build_pools_block,
    extract_pool_meta,
    merge_pool_meta,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.sporttery.cn/",
    "Origin": "https://www.sporttery.cn",
}
API = (
    "https://webapi.sporttery.cn/gateway/jc/football/"
    "getMatchCalculatorV1.qry?channel=c&poolCode="
)

CSV_SINGLE_COLS = {
    "had": "had_single",
    "hhad": "hhad_single",
    "ttg": "ttg_single",
    "hafu": "hafu_single",
    "crs": "crs_single",
}


def fetch(pool: str) -> dict:
    req = urllib.request.Request(API + pool, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def pool_to_csv_text(pools: dict, key: str) -> str:
    info = pools.get(key) or {}
    if not info.get("selling"):
        return "未开售"
    return "是" if info.get("single") else "否"


def build_api_match(mid: int, api_by_id: dict[int, dict]) -> dict:
    return build_pools_block(api_by_id[mid])


def main() -> None:
    local = json.loads((PROCESSED / "match_odds_top8.json").read_text(encoding="utf-8"))
    summary_rows = list(
        csv.DictReader((PROCESSED / "match_odds_summary.csv").open(encoding="utf-8-sig"))
    )
    local_matches = local["matches"]

    api_by_id: dict[int, dict] = {}
    for pool in ("had,hhad", "crs", "ttg", "hafu"):
        time.sleep(1.5)
        resp = fetch(pool)
        for day in resp["value"]["matchInfoList"]:
            for m in day["subMatchList"]:
                mid = m["matchId"]
                if mid not in api_by_id:
                    api_by_id[mid] = {"matchId": mid, "_poolMeta": {}}
                for key in ("had", "hhad", "crs", "ttg", "hafu", "matchNumStr", "homeTeamAbbName"):
                    if m.get(key):
                        api_by_id[mid][key] = m[key]
                api_by_id[mid]["_poolMeta"] = merge_pool_meta(
                    api_by_id[mid]["_poolMeta"],
                    extract_pool_meta(m.get("poolList")),
                )
                api_by_id[mid]["poolList"] = m.get("poolList", [])

    print("=== 单关信息校验报告 ===\n")
    ok = True
    mismatches: list[str] = []

    for m in local_matches:
        mid = m["matchId"]
        label = m["matchNumStr"]
        api_pools = build_api_match(mid, api_by_id)
        local_pools = m.get("pools") or {}

        for key in ("had", "hhad", "ttg", "hafu", "crs"):
            lp = local_pools.get(key) or {}
            ap = api_pools.get(key) or {}
            if lp.get("selling") != ap.get("selling"):
                mismatches.append(
                    f"{label} {key} selling: local={lp.get('selling')} api={ap.get('selling')}"
                )
            if lp.get("single") != ap.get("single"):
                mismatches.append(
                    f"{label} {key} single: local={lp.get('single')} api={ap.get('single')}"
                )

    summary_by_num = {r["matchNumStr"]: r for r in summary_rows}
    for m in local_matches:
        row = summary_by_num.get(m["matchNumStr"])
        if not row:
            mismatches.append(f"{m['matchNumStr']} 不在 summary CSV 中")
            continue
        pools = m.get("pools") or {}
        for key, col in CSV_SINGLE_COLS.items():
            expected = pool_to_csv_text(pools, key)
            if row.get(col) != expected:
                mismatches.append(
                    f"{m['matchNumStr']} CSV {col}: local={row.get(col)} expected={expected}"
                )

    if mismatches:
        ok = False
        print(f"[FAIL] 发现 {len(mismatches)} 处不一致：")
        for line in mismatches:
            print(f"  - {line}")
    else:
        print("[PASS] JSON pools 与当前 API poolList 单关/开售状态完全一致")
        print("[PASS] summary CSV 单关列与 JSON 一致")

    print("\n=== API 原始 poolList.single（供人工核对）===\n")
    for m in local_matches:
        mid = m["matchId"]
        print(f"{m['matchNumStr']} {m['homeTeam']} vs {m['awayTeam']}")
        pool_singles: dict[str, int] = {}
        for pl in api_by_id[mid].get("poolList") or []:
            code = (pl.get("poolCode") or "").upper()
            key = POOL_CODE_MAP.get(code)
            if not key:
                continue
            single = max(
                int(pl.get("single") or 0),
                int(pl.get("bettingSingle") or 0),
                int(pl.get("cbtSingle") or 0),
            )
            pool_singles[key] = max(pool_singles.get(key, 0), single)
        for key in ("had", "hhad", "ttg", "hafu", "crs"):
            api_p = build_api_match(mid, api_by_id)[key]
            raw = pool_singles.get(key, -1)
            status = "未开售"
            if api_p["selling"]:
                status = "可单关" if api_p["single"] else "仅过关"
            print(f"  {api_p['label']}: API single={raw} -> {status}")
        print()

    print("=== 本地记录（JSON / CSV）===\n")
    for m, row in zip(local_matches, summary_rows):
        pools = m.get("pools") or {}
        parts = []
        for key in ("had", "hhad", "ttg", "hafu", "crs"):
            info = pools[key]
            if not info["selling"]:
                parts.append(f"{info['label']}:未开售")
            elif info["single"]:
                parts.append(f"{info['label']}:可单关")
            else:
                parts.append(f"{info['label']}:仅过关")
        print(f"{m['matchNumStr']} {m['homeTeam']} vs {m['awayTeam']}")
        print(f"  JSON: {' | '.join(parts)}")
        print(
            f"  CSV: had={row['had_single']} hhad={row['hhad_single']} "
            f"ttg={row['ttg_single']} hafu={row['hafu_single']} crs={row['crs_single']}"
        )
        print()

    print("结论:", "单关信息正确。" if ok else "单关信息有误，请重新运行 fetch_jc_odds.py。")


if __name__ == "__main__":
    main()
