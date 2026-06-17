import csv
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "processed"
LAST_VERIFIED = "2026-06-15"

TARGET_LEAGUES = {
    "KSA": "Saudi Pro League",
    "USA": "Major League Soccer",
    "NED": "Eredivisie",
    "TUR": "Super Lig",
    "POR": "Primeira Liga",
    "QAT": "Qatar Stars League",
    "IRN": "Persian Gulf Pro League",
}

SOURCE_STATUS = {
    "KSA": (
        "FotMob / PlayerStats.football / Transfermarkt",
        "partial",
        "FotMob pages expose player xG snippets, but batch API and SofaScore tooling failed in this environment.",
    ),
    "USA": (
        "FBref MLS 2025 / FotMob",
        "team_xg_snapshot_available",
        "FBref 2025 MLS page is available through cached search output; direct FBref fetch is 403.",
    ),
    "NED": (
        "SofaScore via football-data-mcp / FBref / PlayerStats.football",
        "candidate",
        "football-data-mcp supports Eredivisie xG/xAG, but Botasaurus DLL download failed over SSL here.",
    ),
    "TUR": (
        "FBref / FootyStats / MakeYourStats / Transfermarkt",
        "basic_or_partial_xg",
        "FBref cached page has standard 2024-25 data; 2025-26 player xG needs FootyStats or paid/API sources.",
    ),
    "POR": (
        "SofaScore via football-data-mcp / FBref / PlayerStats.football",
        "candidate",
        "football-data-mcp supports Primeira Liga xG/xAG, but Botasaurus DLL download failed over SSL here.",
    ),
    "QAT": (
        "FootyStats / DJYY / PerformanceOdds / Transfermarkt",
        "manual_only",
        "Public pages expose selected player or team xG, not reliable full player batch tables.",
    ),
    "IRN": (
        "IPLstats / 365Scores / GioScore / Transfermarkt",
        "basic_only",
        "Reliable public xG was not found; goals, assists, and minutes are the practical fallback.",
    ),
}


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def club_country(club):
    match = re.search(r"\(([A-Z]{2,4})\)\s*$", club or "")
    return match.group(1) if match else ""


def build_targets(summary_rows):
    rows = []
    for row in summary_rows:
        code = club_country(row["club"])
        if row["source_layer"] != "missing" or code not in TARGET_LEAGUES:
            continue
        rows.append(
            {
                "club_country_code": code,
                "target_league": TARGET_LEAGUES[code],
                "team": row["team"],
                "team_code": row["team_code"],
                "group": row["group"],
                "player": row["player"],
                "position": row["position"],
                "club": row["club"],
                "current_source_status": SOURCE_STATUS[code][1],
                "recommended_sources": SOURCE_STATUS[code][0],
                "notes": SOURCE_STATUS[code][2],
            }
        )
    return sorted(rows, key=lambda r: (r["club_country_code"], r["team"], r["club"], r["player"]))


def build_source_status(target_rows):
    counts = defaultdict(int)
    clubs = defaultdict(list)
    for row in target_rows:
        code = row["club_country_code"]
        counts[code] += 1
        if row["club"] not in clubs[code]:
            clubs[code].append(row["club"])

    rows = []
    for code, league in TARGET_LEAGUES.items():
        sources, status, notes = SOURCE_STATUS[code]
        rows.append(
            {
                "club_country_code": code,
                "target_league": league,
                "missing_players": counts[code],
                "top_clubs": " | ".join(clubs[code][:8]),
                "recommended_sources": sources,
                "automation_status": status,
                "last_verified": LAST_VERIFIED,
                "notes": notes,
            }
        )
    return rows


def build_non_big5_supplement():
    manual_path = PROCESSED / "player_form_manual_supplement_2025_26.csv"
    if not manual_path.exists():
        return []

    rows = []
    for row in read_csv(manual_path):
        code = club_country(row["roster_club"])
        if code not in TARGET_LEAGUES:
            continue
        rows.append(
            {
                "national_team": row["national_team"],
                "team_code": row["team_code"],
                "group": row["group"],
                "roster_player": row["roster_player"],
                "roster_position": row["roster_position"],
                "roster_club": row["roster_club"],
                "matched_player": row["matched_player"],
                "club": row["club"],
                "league": row["league"],
                "season": row["season"],
                "matches_played": "",
                "minutes": row["minutes"],
                "goals": row["goals"],
                "assists": row["assists"],
                "shots": row["shots"],
                "key_passes": "",
                "xg": row["xg"],
                "npxg": row["npxg"],
                "xa": row["xa"],
                "xg_per90": "",
                "xa_per90": "",
                "source": row["source"],
                "source_url": row["source_url"],
                "last_verified": row["last_verified"],
                "match_confidence": row["match_confidence"],
                "recommended_weight": row["recommended_weight"],
                "notes": row["notes"],
            }
        )
    return rows


def main():
    summary_rows = read_csv(PROCESSED / "player_form_summary.csv")
    target_rows = build_targets(summary_rows)
    write_csv(
        PROCESSED / "player_form_non_big5_target_gaps.csv",
        target_rows,
        [
            "club_country_code",
            "target_league",
            "team",
            "team_code",
            "group",
            "player",
            "position",
            "club",
            "current_source_status",
            "recommended_sources",
            "notes",
        ],
    )
    write_csv(
        PROCESSED / "player_form_non_big5_source_status.csv",
        build_source_status(target_rows),
        [
            "club_country_code",
            "target_league",
            "missing_players",
            "top_clubs",
            "recommended_sources",
            "automation_status",
            "last_verified",
            "notes",
        ],
    )
    write_csv(
        PROCESSED / "player_form_non_big5_supplement_2025_26.csv",
        build_non_big5_supplement(),
        [
            "national_team",
            "team_code",
            "group",
            "roster_player",
            "roster_position",
            "roster_club",
            "matched_player",
            "club",
            "league",
            "season",
            "matches_played",
            "minutes",
            "goals",
            "assists",
            "shots",
            "key_passes",
            "xg",
            "npxg",
            "xa",
            "xg_per90",
            "xa_per90",
            "source",
            "source_url",
            "last_verified",
            "match_confidence",
            "recommended_weight",
            "notes",
        ],
    )
    print(f"non-Big-5 target gaps: {len(target_rows)}")


if __name__ == "__main__":
    main()
