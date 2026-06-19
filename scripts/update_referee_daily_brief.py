# -*- coding: utf-8 -*-
"""每日裁判简报：列出未来 3 天已确认/未知裁判场次。"""
from __future__ import annotations

import csv
import os
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
OFFICIALS = os.path.join(HERE, "..", "database", "referee", "processed", "match_officials.csv")


def main():
    today = date.today()
    horizon = today + timedelta(days=3)
    with open(OFFICIALS, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"# Referee brief {today} — next 3 days\n")
    for r in rows:
        try:
            d = date.fromisoformat(r["date"])
        except ValueError:
            continue
        if today <= d <= horizon:
            status = r.get("status", "unknown")
            ref = r.get("referee") or "(未公布)"
            print(f"{r['date']}  {r['home']} vs {r['away']}  [{status}]  {ref}")


if __name__ == "__main__":
    main()
