#!/usr/bin/env python3
"""Re-match the 48-team roster against the club player-form pools.

The original pulls matched roster players to the club xG pools using *exact*
normalized full-name equality. That failed for two reasons:

1. The roster `player` field carries FIFA-PDF artifacts where the popular name
   is duplicated, e.g. "Vinicius VINICIUS JUNIOR", "Mohamed MOHAMED SALAH",
   "Carlos CASEMIRO", "Raphael RAPHINHA", "Bruno BRUNO GUIMARAES".
2. Sources spell some names differently, e.g. Understat "Kylian Mbappe-Lottin"
   vs roster "Kylian MBAPPE".

As a result, elite attackers that ARE present in the pools were wrongly listed
as missing, understating coverage. This script rebuilds the matched / trusted /
missing / coverage outputs for both seasons using a more robust matcher:

  - collapse consecutive duplicate tokens ("vinicius vinicius junior" ->
    "vinicius junior"),
  - derive the roster "popular name" from the upper-case tokens,
  - accept exact full/popular-name equality, surname-token subset, or a high
    fuzzy ratio, with club similarity as a guard for the weaker matches.

It reads the already-parsed club pools (treated as ground truth) and the roster,
and only re-does the join, preserving each season's existing output schema.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

PROCESSED = Path(__file__).resolve().parent.parent / "processed"
ROSTER_PATH = (
    Path(__file__).resolve().parents[2]
    / "48-team-roster" / "processed" / "squads_48_teams.csv"
)
LAST_VERIFIED = "2026-06-15"

CLUB_ALIASES = {
    "arsenal fc": "arsenal", "aston villa fc": "aston villa",
    "athletic club": "athletic club", "athletic bilbao": "athletic club",
    "atletico de madrid": "atletico madrid", "atletico madrid": "atletico madrid",
    "bayer 04 leverkusen": "bayer leverkusen", "bayern munchen": "bayern munich",
    "borussia m'gladbach": "borussia monchengladbach",
    "borussia monchengladbach": "borussia monchengladbach",
    "brighton & hove albion": "brighton", "brighton and hove albion": "brighton",
    "club atletico de madrid": "atletico madrid", "fc barcelona": "barcelona",
    "fc bayern munchen": "bayern munich", "fc bayern munich": "bayern munich",
    "fc internazionale milano": "inter", "fc internazionale": "inter",
    "inter milan": "inter", "juventus fc": "juventus", "lille osc": "lille",
    "manchester city fc": "manchester city",
    "manchester united fc": "manchester united",
    "newcastle united fc": "newcastle united",
    "nottingham forest fc": "nottingham forest", "ogc nice": "nice",
    "olympique de marseille": "marseille", "olympique lyonnais": "lyon",
    "paris saint germain": "paris saint germain", "paris sg": "paris saint germain",
    "paris s g": "paris saint germain", "rb leipzig": "rasenballsport leipzig",
    "real madrid cf": "real madrid", "real sociedad de futbol": "real sociedad",
    "ssc napoli": "napoli", "tottenham hotspur fc": "tottenham",
    "vfb stuttgart 1893": "vfb stuttgart", "vfl wolfsburg": "wolfsburg",
    "west ham united fc": "west ham",
    "stade rennais": "rennes", "stade rennais fc": "rennes",
    "stade rennais football club": "rennes", "rc lens": "lens",
    "racing club de lens": "lens", "olympique de marseille": "marseille",
    "as monaco": "monaco", "as monaco fc": "monaco",
}


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def norm_text(value: str) -> str:
    value = strip_accents(value).lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def dedup_tokens(text: str) -> str:
    out: list[str] = []
    for tok in text.split():
        if not out or out[-1] != tok:
            out.append(tok)
    return " ".join(out)


def is_allcaps(token: str) -> bool:
    letters = [c for c in token if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def popular_name(player: str) -> str:
    caps = [t for t in player.split() if is_allcaps(t)]
    return " ".join(caps) if caps else player


def norm_club(value: str) -> str:
    value = re.sub(r"\s*\([A-Z]{2,4}\)\s*$", "", value or "")
    value = norm_text(value)
    value = re.sub(r"^(afc|cf|fc|sc|ss|ac|as|us|rc|cd|sd)\s+", "", value)
    value = re.sub(r"\s+(afc|cf|fc|sc|ss|ac|as|us|rc|cd|sd)$", "", value)
    return CLUB_ALIASES.get(value, value)


def club_similarity(roster_club: str, pool_club: str) -> float:
    a, b = norm_club(roster_club), norm_club(pool_club)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.92
    return round(SequenceMatcher(None, a, b).ratio(), 3)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def to_int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def best_match(roster_player: str, roster_club: str, pool: list[dict]):
    """Return (pool_row, club_sim, name_score) or None."""
    full = dedup_tokens(norm_text(roster_player))
    pop = dedup_tokens(norm_text(popular_name(roster_player)))
    pop_tokens = set(pop.split())

    best = None
    best_rank: tuple | None = None
    for row in pool:
        pname = dedup_tokens(norm_text(row["player"]))
        ptokens = set(pname.split())
        if pname in (full, pop):
            name_score = 1.0
        elif pop_tokens and (pop_tokens <= ptokens or ptokens <= pop_tokens):
            name_score = 0.9
        else:
            ratio = SequenceMatcher(None, pop or full, pname).ratio()
            name_score = ratio if ratio >= 0.9 else 0.0
        if name_score == 0.0:
            continue
        club_sim = club_similarity(roster_club, row["club"])
        # Weaker (non-exact) name matches must be backed by a similar club.
        if name_score < 1.0 and club_sim < 0.6:
            continue
        rank = (name_score >= 1.0, club_sim, name_score, to_int(row.get("minutes")))
        if best_rank is None or rank > best_rank:
            best_rank, best = rank, (row, club_sim, name_score)
    return best


def coverage_rows(roster: list[dict], matched: list[dict], matched_col: str,
                  source: str, note: str) -> list[dict]:
    totals: dict[str, int] = {}
    hits: dict[str, int] = {}
    for r in roster:
        totals[r["team"]] = totals.get(r["team"], 0) + 1
    for m in matched:
        hits[m["national_team"]] = hits.get(m["national_team"], 0) + 1
    rows = []
    for team in sorted(totals):
        total = totals[team]
        hit = hits.get(team, 0)
        rows.append({
            "team": team, "total_roster_players": total, matched_col: hit,
            "missing": total - hit, "coverage_pct": round(hit / total, 3),
            "source": source, "notes": note,
        })
    return rows


def run_understat(roster: list[dict]) -> tuple[int, int]:
    pool = read_csv(PROCESSED / "club_player_form_understat_big5_2025_26.csv")
    matched, trusted, missing = [], [], []
    for r in roster:
        hit = best_match(r["player"], r["club"], pool)
        if not hit:
            missing.append(r)
            continue
        p, club_sim, _ = hit
        if club_sim >= 0.86:
            match_type, weight = "name_and_similar_club", "0.75"
        elif club_sim >= 0.6:
            match_type, weight = "name_only_club_differs", "0.55"
        else:
            match_type, weight = "name_only_multiple_candidates", "0.35"
        out = {
            "national_team": r["team"], "team_code": r["team_code"],
            "group": r["group"], "roster_player": r["player"],
            "roster_position": r["position"], "roster_club": r["club"],
            "understat_player": p["player"], "understat_position": p["position"],
            "understat_club": p["club"], "league": p["league"],
            "season": p["season"], "matches_played": p["matches_played"],
            "minutes": p["minutes"], "goals": p["goals"], "assists": p["assists"],
            "shots": p["shots"], "key_passes": p["key_passes"], "xg": p["xg"],
            "npxg": p["npxg"], "xa": p["xa"], "xg_chain": p["xg_chain"],
            "xg_buildup": p["xg_buildup"], "xg_per90": p["xg_per90"],
            "xa_per90": p["xa_per90"], "npxg_per90": p["npxg_per90"],
            "match_type": match_type, "club_similarity": club_sim,
            "recommended_weight": weight, "source": p["source"],
            "source_url": p["source_url"], "last_verified": LAST_VERIFIED,
            "notes": "Understat Big 5 2025-26 current-season club form. "
                     "Understat uses its own xG model, not Opta/FBref.",
        }
        matched.append(out)
        if match_type == "name_and_similar_club":
            trusted.append(out)

    fields = list(matched[0].keys())
    write_csv(PROCESSED / "player_form_matched_understat_big5_2025_26.csv",
              matched, fields)
    write_csv(PROCESSED / "player_form_trusted_understat_big5_2025_26.csv",
              trusted, fields)
    miss_rows = [{
        "team": r["team"], "team_code": r["team_code"], "group": r["group"],
        "player": r["player"], "position": r["position"], "club": r["club"],
        "source": "Understat Big 5 2025-26",
        "notes": "No name match in the pulled Understat Big 5 2025-26 player "
                 "table (likely outside the five major European leagues).",
    } for r in missing]
    write_csv(PROCESSED / "player_form_missing_understat_coverage.csv", miss_rows,
              ["team", "team_code", "group", "player", "position", "club",
               "source", "notes"])
    write_csv(
        PROCESSED / "player_form_coverage_by_team_understat_2025_26.csv",
        coverage_rows(roster, matched, "matched_big5_2025_26",
                      "Understat Big 5 2025-26",
                      "Coverage is partial: Understat covers EPL, La Liga, "
                      "Bundesliga, Serie A, Ligue 1 only."),
        ["team", "total_roster_players", "matched_big5_2025_26", "missing",
         "coverage_pct", "source", "notes"])
    return len(matched), len(trusted)


def run_fbref(roster: list[dict]) -> tuple[int, int]:
    pool = read_csv(PROCESSED / "club_player_form_big5_2024_25.csv")
    matched, trusted, missing = [], [], []
    for r in roster:
        hit = best_match(r["player"], r["club"], pool)
        if not hit:
            missing.append(r)
            continue
        p, club_sim, _ = hit
        if club_sim >= 0.86:
            match_type, is_trusted = "name_and_similar_club", True
        elif club_sim >= 0.6:
            match_type, is_trusted = "name_and_club", True
        else:
            match_type, is_trusted = "name_only", False
        out = {
            "national_team": r["team"], "team_code": r["team_code"],
            "group": r["group"], "roster_player": r["player"],
            "roster_position": r["position"], "roster_club": r["club"],
            "fbref_player": p["player"], "fbref_position": p["position"],
            "fbref_club": p["club"], "league": p["league"], "season": p["season"],
            "matches_played": p["matches_played"], "starts": p["starts"],
            "minutes": p["minutes"], "goals": p["goals"], "assists": p["assists"],
            "xg": p["xg"], "npxg": p["npxg"], "xag": p["xag"],
            "xg_per90": p["xg_per90"], "xag_per90": p["xag_per90"],
            "match_type": match_type, "recommended_weight": "0.55",
            "source": p["source"], "source_url": p["source_url"],
            "last_verified": LAST_VERIFIED,
            "notes": "FBref Big 5 2024-25 baseline club form (Opta-lineage xG); "
                     "use as stable cross-check vs Understat 2025-26.",
        }
        matched.append(out)
        if is_trusted:
            trusted.append(out)

    fields = list(matched[0].keys())
    write_csv(PROCESSED / "player_form_matched_big5_2024_25.csv", matched, fields)
    write_csv(PROCESSED / "player_form_trusted_big5_2024_25.csv", trusted, fields)
    miss_rows = [{
        "national_team": r["team"], "team_code": r["team_code"],
        "group": r["group"], "roster_player": r["player"],
        "roster_position": r["position"], "roster_club": r["club"],
        "reason": "not_found_in_fbref_big5_2024_25",
        "recommended_next_sources": "Transfermarkt club profile; FBref single "
        "league if available; domestic league provider; FotMob/SofaScore player "
        "page",
    } for r in missing]
    write_csv(PROCESSED / "player_form_missing_coverage.csv", miss_rows,
              ["national_team", "team_code", "group", "roster_player",
               "roster_position", "roster_club", "reason",
               "recommended_next_sources"])
    write_csv(
        PROCESSED / "player_form_coverage_by_team.csv",
        coverage_rows(roster, matched, "matched_big5_2024_25",
                      "FBref Big 5 2024-25",
                      "Coverage is partial: FBref Big 5 covers EPL, La Liga, "
                      "Bundesliga, Serie A, Ligue 1 only."),
        ["team", "total_roster_players", "matched_big5_2024_25", "missing",
         "coverage_pct", "source", "notes"])
    return len(matched), len(trusted)


def rebuild_coverage_summary(roster: list[dict]) -> None:
    """Rebuild the mixed-source coverage summary on the corrected Understat
    matched set plus the manually verified non-Big-5 supplement, so the numbers
    reflect precise matches rather than the earlier inflated/false-positive set.
    """
    matched = read_csv(PROCESSED / "player_form_matched_understat_big5_2025_26.csv")
    supplement_path = PROCESSED / "player_form_manual_supplement_2025_26.csv"
    supplement = read_csv(supplement_path) if supplement_path.exists() else []

    totals: dict[str, int] = {}
    for r in roster:
        totals[r["team"]] = totals.get(r["team"], 0) + 1

    understat_by_team: dict[str, set[str]] = {}
    for m in matched:
        understat_by_team.setdefault(m["national_team"], set()).add(m["roster_player"])
    supp_by_team: dict[str, set[str]] = {}
    for s in supplement:
        supp_by_team.setdefault(s["national_team"], set()).add(s["roster_player"])

    rows = []
    for team in sorted(totals):
        total = totals[team]
        u_players = understat_by_team.get(team, set())
        # Only count supplement players not already covered by Understat.
        s_extra = supp_by_team.get(team, set()) - u_players
        covered = len(u_players) + len(s_extra)
        rows.append({
            "team": team, "total_roster_players": total,
            "understat_big5_2025_26": len(u_players),
            "manual_supplement_2025_26": len(s_extra),
            "covered_total": covered,
            "missing_after_supplement": total - covered,
            "coverage_pct": round(covered / total, 3),
            "notes": "Understat = precise Big-5 matches (club-similarity "
                     "guarded); manual supplement is source-mixed, lower weight.",
        })
    write_csv(
        PROCESSED / "player_form_current_coverage_summary.csv", rows,
        ["team", "total_roster_players", "understat_big5_2025_26",
         "manual_supplement_2025_26", "covered_total",
         "missing_after_supplement", "coverage_pct", "notes"])


def main() -> int:
    roster = read_csv(ROSTER_PATH)
    u_matched, u_trusted = run_understat(roster)
    f_matched, f_trusted = run_fbref(roster)
    rebuild_coverage_summary(roster)
    print(f"Understat 2025-26: matched={u_matched} trusted={u_trusted} "
          f"missing={len(roster) - u_matched}")
    print(f"FBref 2024-25:     matched={f_matched} trusted={f_trusted} "
          f"missing={len(roster) - f_matched}")
    print("Rebuilt player_form_current_coverage_summary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
