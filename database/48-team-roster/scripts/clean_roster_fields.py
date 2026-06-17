#!/usr/bin/env python3
"""Clean the messy `name_on_shirt` and `head_coach_raw` fields produced by the
FIFA squad-list PDF text extraction.

The PDF-to-text step merged adjacent columns, so both fields contain duplicated
and concatenated tokens, e.g.:

    name_on_shirt : "MASTIL MASTIL"          -> "MASTIL"
                    "AÏT-NOURI AÏT NOURI"     -> "AÏT-NOURI"
    head_coach_raw: "PETKOVIC Vladimir Vladimir PETKOVIĆ Switzerland"
                    -> head_coach="Vladimir PETKOVIĆ", nationality="Switzerland"

The script is idempotent: it always rebuilds the cleaned columns from the
preserved raw columns (`name_on_shirt_raw`, `head_coach_raw`), so it can be run
repeatedly without degrading the data.
"""

from __future__ import annotations

import csv
import sys
import unicodedata
from pathlib import Path

PROCESSED = Path(__file__).resolve().parent.parent / "processed"
SQUADS_CSV = PROCESSED / "squads_48_teams.csv"
SUMMARY_CSV = PROCESSED / "squad_depth_summary.csv"

# Coach nationalities as they appear at the end of head_coach_raw. Multi-word
# entries are matched first so the country boundary is detected correctly.
COUNTRIES = [
    "Bosnia And Herzegovina",
    "Korea Republic",
    "Czech Republic",
    "Cabo Verde",
    "New Zealand",
    "Côte D'Ivoire",
    "IR Iran",
    "Saudi Arabia",
    "Switzerland", "Argentina", "Australia", "Germany", "France", "Italy",
    "USA", "Croatia", "Netherlands", "Egypt", "Portugal", "Japan", "Morocco",
    "Mexico", "Norway", "Spain", "Greece", "Scotland", "Senegal", "Belgium",
    "England", "Brazil",
]
# Longest first so "Czech Republic" wins over "Republic"-style partial matches.
COUNTRIES.sort(key=lambda c: len(c.split()), reverse=True)


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def is_allcaps(token: str) -> bool:
    letters = [c for c in token if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def surname_tokens(player: str) -> list[str]:
    """Trailing all-caps tokens of the full name are the surname."""
    toks = player.split()
    surname: list[str] = []
    for tok in reversed(toks):
        if is_allcaps(tok):
            surname.insert(0, tok)
        else:
            break
    return surname or [toks[-1]] if toks else []


def clean_shirt_name(player: str, raw: str) -> str:
    """Return the player's shirt name, preferring the accented spelling found
    in the raw value when it matches the surname taken from `player`."""
    surname = surname_tokens(player)
    key = " ".join(strip_accents(t).upper() for t in surname)

    raw_toks = raw.split()
    n = len(surname)
    for i in range(len(raw_toks) - n + 1):
        run = raw_toks[i:i + n]
        if " ".join(strip_accents(t).upper() for t in run) == key:
            return " ".join(run).upper()
    return " ".join(surname).upper()


def split_nationality(raw: str) -> tuple[str, str]:
    """Split trailing country off the raw coach string."""
    text = raw.strip()
    for country in COUNTRIES:
        if text.endswith(country) and (
            len(text) == len(country) or text[-len(country) - 1] == " "
        ):
            return text[: -len(country)].strip(), country
    # Fallback: assume the last token is the country.
    toks = text.split()
    return " ".join(toks[:-1]), toks[-1] if toks else ""


def clean_coach(raw: str) -> tuple[str, str]:
    """Return (head_coach, nationality) from a raw coach string of the form
    `<SURNAME> <First> <full given names...> <SURNAME(accented)> <Country>`."""
    name_part, nationality = split_nationality(raw)
    toks = name_part.split()
    if not toks:
        return "", nationality

    # First given name = first token after the leading all-caps surname run.
    i = 0
    while i < len(toks) and is_allcaps(toks[i]):
        i += 1
    first_name = toks[i] if i < len(toks) else toks[0]

    # Surname = trailing run of all-caps tokens (length >= 2 skips initials).
    j = len(toks)
    while j > 0 and is_allcaps(toks[j - 1]) and len(toks[j - 1]) >= 2:
        j -= 1
    surname = toks[j:] if j < len(toks) else toks[:i]

    coach = " ".join([first_name] + surname).strip()
    return coach, nationality


def clean_squads() -> int:
    with SQUADS_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return 0

    fieldnames = list(rows[0].keys())
    if "name_on_shirt_raw" not in fieldnames:
        fieldnames.append("name_on_shirt_raw")

    for row in rows:
        raw = row.get("name_on_shirt_raw") or row.get("name_on_shirt", "")
        row["name_on_shirt_raw"] = raw
        row["name_on_shirt"] = clean_shirt_name(row.get("player", ""), raw)

    with SQUADS_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def clean_summary() -> int:
    with SUMMARY_CSV.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return 0

    fieldnames = list(rows[0].keys())
    for col in ("head_coach", "head_coach_nationality"):
        if col not in fieldnames:
            idx = fieldnames.index("head_coach_raw") + 1
            fieldnames.insert(idx, col)

    for row in rows:
        coach, nat = clean_coach(row.get("head_coach_raw", ""))
        row["head_coach"] = coach
        row["head_coach_nationality"] = nat

    with SUMMARY_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    n_players = clean_squads()
    n_teams = clean_summary()
    print(f"Cleaned name_on_shirt for {n_players} players in {SQUADS_CSV.name}")
    print(f"Cleaned head_coach for {n_teams} teams in {SUMMARY_CSV.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
