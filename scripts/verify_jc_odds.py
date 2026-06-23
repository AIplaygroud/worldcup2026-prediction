"""Verify local jc-odds data against live sporttery API."""
from __future__ import annotations

import csv
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "database" / "jc-odds" / "processed"
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
CRS_OTHER = {"s1sh": "胜其他", "s1sd": "平其他", "s1sa": "负其他"}


def fetch(pool: str) -> dict:
    req = urllib.request.Request(API + pool, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def api_crs_count(crs: dict) -> int:
    return len(
        [
            k
            for k, v in crs.items()
            if k not in ("updateDate", "updateTime", "goalLine", "goalLineValue")
            and not k.endswith("f")
            and v
        ]
    )


def api_ttg_map(ttg: dict) -> dict[str, str]:
    out = {}
    for k, v in ttg.items():
        if k.endswith("f") or not v or not k.startswith("s"):
            continue
        out["7+" if k == "s7" else k[1:]] = v
    return out


def main() -> None:
    local_path = PROCESSED / "match_odds_top8.json"
    local = json.loads(local_path.read_text(encoding="utf-8"))
    local_matches = local["matches"]

    api_by_id: dict[int, dict] = {}
    for pool in ("had,hhad", "crs", "ttg", "hafu"):
        time.sleep(1.5)
        resp = fetch(pool)
        for day in resp["value"]["matchInfoList"]:
            for m in day["subMatchList"]:
                mid = m["matchId"]
                if mid not in api_by_id:
                    api_by_id[mid] = m
                for key in ("had", "hhad", "crs", "ttg", "hafu"):
                    if m.get(key):
                        api_by_id[mid][key] = m[key]

    api_top8 = sorted(api_by_id.values(), key=lambda x: (x["matchDate"], x["matchTime"]))
    api_top8 = [m for m in api_top8 if m.get("leagueAbbName") == "世界杯"][:8]
    local_ids = [m["matchId"] for m in local_matches]
    api_ids = [m["matchId"] for m in api_top8]

    print("=== 校验报告 ===\n")
    print(f"本地文件: {local_path}")
    print(f"本地拉取时间: {local['meta']['fetchedAt']}")
    print(f"官方最后更新: {local['meta'].get('lastUpdateTime')}")
    print(f"本地场次数: {len(local_matches)}")
    print()

    ok = True

    if local_ids == api_ids:
        print("[PASS] 场次选择与排序：与 API 世界杯在售前 8 场一致")
    else:
        ok = False
        print("[FAIL] 场次选择与排序不一致")
        print(f"  本地: {local_ids}")
        print(f"  API:  {api_ids}")

    # CSV row count
    summary_rows = list(csv.DictReader((PROCESSED / "match_odds_summary.csv").open(encoding="utf-8-sig")))
    if len(summary_rows) == 8:
        print("[PASS] match_odds_summary.csv 行数 = 8")
    else:
        ok = False
        print(f"[FAIL] match_odds_summary.csv 行数 = {len(summary_rows)} (期望 8)")

    for name, expected in (
        ("match_odds_ttg.csv", 64),
        ("match_odds_hafu.csv", 72),
        ("match_odds_crs.csv", 248),
    ):
        rows = list(csv.DictReader((PROCESSED / name).open(encoding="utf-8-sig")))
        if len(rows) == expected:
            print(f"[PASS] {name} 行数 = {expected}")
        else:
            ok = False
            print(f"[FAIL] {name} 行数 = {len(rows)} (期望 {expected})")

    mismatches: list[str] = []
    for m in local_matches:
        api = api_by_id[m["matchId"]]
        label = m["matchNumStr"]

        if m.get("had") and api.get("had"):
            for side, key in (("home", "h"), ("draw", "d"), ("away", "a")):
                if m["had"].get(side) != api["had"].get(key):
                    mismatches.append(f"{label} had.{side}: local={m['had'].get(side)} api={api['had'].get(key)}")
        elif m.get("had") or api.get("had"):
            mismatches.append(f"{label} had 开售状态不一致")

        if m.get("hhad") and api.get("hhad"):
            for field, key in (("goalLine", "goalLine"), ("home", "h"), ("draw", "d"), ("away", "a")):
                if m["hhad"].get(field) != api["hhad"].get(key):
                    mismatches.append(
                        f"{label} hhad.{field}: local={m['hhad'].get(field)} api={api['hhad'].get(key)}"
                    )

        api_ttg = api_ttg_map(api.get("ttg") or {})
        for row in m.get("ttg") or []:
            if api_ttg.get(row["goals"]) != row["sp"]:
                mismatches.append(
                    f"{label} ttg {row['goals']}: local={row['sp']} api={api_ttg.get(row['goals'])}"
                )

        for row in m.get("hafu") or []:
            av = (api.get("hafu") or {}).get(row["code"])
            if av != row["sp"]:
                mismatches.append(f"{label} hafu {row['code']}: local={row['sp']} api={av}")

        if len(m.get("crs") or []) != api_crs_count(api.get("crs") or {}):
            mismatches.append(
                f"{label} crs count: local={len(m.get('crs') or [])} api={api_crs_count(api.get('crs') or {})}"
            )

    if not mismatches:
        print("[PASS] 全部 SP 值与当前 API 一致（胜平负/让球/总进球/半全场）")
    else:
        ok = False
        print(f"[FAIL] 发现 {len(mismatches)} 处 SP 或条数不一致：")
        for line in mismatches[:20]:
            print(f"  - {line}")

  # internal consistency JSON vs CSV
    json_summary = {
        (m["matchNumStr"], m["homeTeam"], m["awayTeam"]): m for m in local_matches
    }
    for row in summary_rows:
        key = (row["matchNumStr"], row["homeTeam"], row["awayTeam"])
        m = json_summary.get(key)
        if not m:
            ok = False
            print(f"[FAIL] CSV 场次 {key} 在 JSON 中不存在")
            continue
        had = m.get("had") or {}
        if row["had_home"] != (had.get("home") or ""):
            ok = False
            print(f"[FAIL] CSV/JSON had 不一致: {key}")

    print()
    if ok:
        print("结论: 拉取正确，数据完整且与官方 API 一致。")
    else:
        print("结论: 存在问题，建议重新运行 fetch_jc_odds.py。")

    print("\n=== 8 场一览 ===")
    for m in local_matches:
        had = m.get("had") or {}
        hhad = m.get("hhad") or {}
        had_s = f"{had.get('home','-')}/{had.get('draw','-')}/{had.get('away','-')}" if had else "未开售"
        hhad_s = (
            f"{hhad.get('goalLine', '')} {hhad.get('home', '-')}/{hhad.get('draw', '-')}/{hhad.get('away', '-')}"
            if hhad
            else "-"
        )
        print(
            f"{m['matchNumStr']} {m['matchDate']} {m['matchTime']} "
            f"{m['homeTeam']} vs {m['awayTeam']} | 胜平负 {had_s} | 让球 {hhad_s} | "
            f"ttg={len(m.get('ttg') or [])} hafu={len(m.get('hafu') or [])} crs={len(m.get('crs') or [])}"
        )


if __name__ == "__main__":
    main()
