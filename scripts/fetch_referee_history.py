# -*- coding: utf-8 -*-
"""占位：从 Transfermarkt/StatBunker 抓取裁判历史（待接入）。"""
from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "database", "referee", "processed", "referee_style_history.csv")


def main():
    if os.path.isfile(OUT):
        print(f"Kept existing {OUT}; automated fetch not yet implemented.")
    else:
        print("No referee_style_history.csv; seed manually or add fetch logic.")


if __name__ == "__main__":
    main()
