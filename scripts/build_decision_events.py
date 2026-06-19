# -*- coding: utf-8 -*-
"""从 raw/manual_decision_events.csv 合并生成 decision_events.csv（若手工表存在）。"""
from __future__ import annotations

import csv
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DB = os.path.join(HERE, "..", "database", "referee")
PROC = os.path.join(REF_DB, "processed")
RAW_MANUAL = os.path.join(REF_DB, "raw", "manual_decision_events.csv")
OUT = os.path.join(PROC, "decision_events.csv")


def main():
    if os.path.isfile(RAW_MANUAL):
        shutil.copy(RAW_MANUAL, OUT)
        print(f"Copied manual events -> {OUT}")
    elif os.path.isfile(OUT):
        print(f"Kept existing {OUT}")
    else:
        print("No manual_decision_events.csv; decision_events.csv unchanged or missing.")


if __name__ == "__main__":
    main()
