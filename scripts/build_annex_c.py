#!/usr/bin/env python3
"""Build annex_c_round_of_32.csv from FIFA Annex C (via Wikipedia table export)."""
import csv
import re
import pathlib

GROUPS = list("ABCDEFGHIJKL")
WINNER_SLOTS = ["1A", "1B", "1D", "1E", "1G", "1I", "1K", "1L"]
MATCH_BY_WINNER = {
    "1A": 79, "1B": 85, "1D": 81, "1E": 74,
    "1G": 82, "1I": 77, "1K": 87, "1L": 80,
}

SRC = pathlib.Path(r"C:\Users\10272\.cursor\projects\e-WORLDCUP2026\agent-tools\b054dc5e-5c4e-47f2-9a34-431185fef38c.txt")
OUT = pathlib.Path(r"e:\WORLDCUP2026\prediction-skill\database\competition\annex_c_round_of_32.csv")

ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([A-L])\s*\|\s*([A-L])\s*\|\s*([A-L])\s*\|\s*([A-L])\s*\|\s*([A-L])\s*\|\s*([A-L])\s*\|\s*([A-L])\s*\|\s*([A-L])\s*\|\s*(3[A-L])\s*\|\s*(3[A-L])\s*\|\s*(3[A-L])\s*\|\s*(3[A-L])\s*\|\s*(3[A-L])\s*\|\s*(3[A-L])\s*\|\s*(3[A-L])\s*\|\s*(3[A-L])\s*\|"
)

def main():
    text = SRC.read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        m = ROW_RE.match(line.strip())
        if not m:
            continue
        parts = m.groups()
        option = int(parts[0])
        advancing = sorted(parts[1:9])
        eliminated = sorted(g for g in GROUPS if g not in advancing)
        assignments = parts[9:17]
        row = {
            "option": option,
            "advancing_groups": "".join(advancing),
            "eliminated_groups": "".join(eliminated),
        }
        for slot, assign in zip(WINNER_SLOTS, assignments):
            row[f"vs_{slot}"] = assign
        rows.append(row)

    if len(rows) != 495:
        raise SystemExit(f"expected 495 rows, got {len(rows)}")

  # verify unique advancing keys
    keys = [r["advancing_groups"] for r in rows]
    if len(set(keys)) != 495:
        raise SystemExit("duplicate advancing_groups keys")

    fields = ["option", "advancing_groups", "eliminated_groups"] + [f"vs_{s}" for s in WINNER_SLOTS]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} rows -> {OUT}")

if __name__ == "__main__":
    main()
