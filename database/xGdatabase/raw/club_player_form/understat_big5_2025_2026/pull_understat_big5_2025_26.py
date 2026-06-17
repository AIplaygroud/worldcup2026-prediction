import csv
import gzip
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = ROOT / "processed"
ROSTER_PATH = ROOT.parent / "48-team-roster" / "processed" / "squads_48_teams.csv"

LAST_VERIFIED = "2026-06-15"
SEASON = "2025-26"
SEASON_START_YEAR = 2025
SOURCE = "Understat league player stats"
SOURCE_URL_TEMPLATE = "https://understat.com/league/{league}/{season}"

LEAGUES = {
    "EPL": "Premier League",
    "La_liga": "La Liga",
    "Bundesliga": "Bundesliga",
    "Serie_A": "Serie A",
    "Ligue_1": "Ligue 1",
}

CLUB_ALIASES = {
    "arsenal fc": "arsenal",
    "aston villa fc": "aston villa",
    "athletic club": "athletic club",
    "athletic bilbao": "athletic club",
    "atletico de madrid": "atletico madrid",
    "atletico madrid": "atletico madrid",
    "bayer 04 leverkusen": "bayer leverkusen",
    "bayern munchen": "bayern munich",
    "borussia m'gladbach": "borussia monchengladbach",
    "borussia monchengladbach": "borussia monchengladbach",
    "brighton & hove albion": "brighton",
    "brighton and hove albion": "brighton",
    "club atletico de madrid": "atletico madrid",
    "fc barcelona": "barcelona",
    "fc bayern munchen": "bayern munich",
    "fc bayern munich": "bayern munich",
    "fc internazionale milano": "inter",
    "fc internazionale": "inter",
    "inter milan": "inter",
    "juventus fc": "juventus",
    "lille osc": "lille",
    "manchester city fc": "manchester city",
    "manchester united fc": "manchester united",
    "newcastle united fc": "newcastle united",
    "nottingham forest fc": "nottingham forest",
    "ogc nice": "nice",
    "olympique de marseille": "marseille",
    "olympique lyonnais": "lyon",
    "paris saint germain": "paris saint germain",
    "paris sg": "paris saint germain",
    "paris s g": "paris saint germain",
    "rb leipzig": "rasenballsport leipzig",
    "real madrid cf": "real madrid",
    "real sociedad de futbol": "real sociedad",
    "ssc napoli": "napoli",
    "tottenham hotspur fc": "tottenham",
    "vfb stuttgart 1893": "vfb stuttgart",
    "vfl wolfsburg": "wolfsburg",
    "west ham united fc": "west ham",
}


def strip_accents(value):
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def norm_text(value):
    value = strip_accents(value).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def name_variants(value):
    """Build practical variants for FIFA PDF names such as 'Vinicius VINICIUS JUNIOR'."""
    normalized = norm_text(value)
    parts = normalized.split()
    variants = {normalized}
    if not parts:
        return variants
    deduped = []
    for part in parts:
        if part not in deduped:
            deduped.append(part)
    variants.add(" ".join(deduped))
    if len(parts) >= 2 and parts[0] == parts[1]:
        variants.add(" ".join(parts[1:]))
    if len(deduped) >= 2:
        variants.add(" ".join(deduped[-2:]))
        # FIFA PDF rows sometimes contain given name + common shirt name, while data
        # providers keep only the short football name, e.g. "Marcos MARQUINHOS".
        variants.add(deduped[-1])
    if len(parts) >= 3:
        variants.add(" ".join(parts[1:]))
    return {variant for variant in variants if variant}


def norm_club(value):
    value = re.sub(r"\s*\([A-Z]{2,4}\)\s*$", "", value or "")
    value = norm_text(value)
    value = re.sub(r"^(afc|cf|fc|sc|ss|ac|as|us|rc|cd|sd)\s+", "", value)
    value = re.sub(r"\s+(afc|cf|fc|sc|ss|ac|as|us|rc|cd|sd)$", "", value)
    return CLUB_ALIASES.get(value, value)


def to_float(value):
    if value in (None, ""):
        return 0.0
    return round(float(value), 3)


def to_int(value):
    if value in (None, ""):
        return 0
    return int(float(value))


def per90(total, minutes):
    if not minutes:
        return 0.0
    return round(total / minutes * 90, 3)


def fetch_understat_players(league):
    url = "https://understat.com/main/getPlayersStats/"
    body = urllib.parse.urlencode({"league": league, "season": str(SEASON_START_YEAR)}).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": SOURCE_URL_TEMPLATE.format(league=league, season=SEASON_START_YEAR),
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    raw = urllib.request.urlopen(request, timeout=30).read()
    try:
        payload = gzip.decompress(raw).decode("utf-8")
    except gzip.BadGzipFile:
        payload = raw.decode("utf-8")
    data = json.loads(payload)
    if not data.get("success"):
        raise RuntimeError(f"Understat request failed for {league}: {data!r}")
    return data["players"]


def write_json(path, rows):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_roster():
    with ROSTER_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def club_similarity(roster_club, understat_club):
    roster_norm = norm_club(roster_club)
    understat_norm = norm_club(understat_club)
    if not roster_norm or not understat_norm:
        return 0.0
    if roster_norm == understat_norm:
        return 1.0
    if roster_norm in understat_norm or understat_norm in roster_norm:
        return 0.92
    return round(SequenceMatcher(None, roster_norm, understat_norm).ratio(), 3)


def build_player_rows():
    rows = []
    for league_key, league_name in LEAGUES.items():
        snapshot_path = RAW_DIR / f"understat_{league_key.lower()}_players_2025_2026.json"
        if snapshot_path.exists():
            players = read_json(snapshot_path)
        else:
            players = fetch_understat_players(league_key)
            write_json(snapshot_path, players)
        source_url = SOURCE_URL_TEMPLATE.format(league=league_key, season=SEASON_START_YEAR)
        for player in players:
            minutes = to_int(player.get("time"))
            xg = to_float(player.get("xG"))
            xa = to_float(player.get("xA"))
            npxg = to_float(player.get("npxG"))
            rows.append(
                {
                    "player": player.get("player_name", ""),
                    "understat_id": player.get("id", ""),
                    "position": player.get("position", ""),
                    "club": player.get("team_title", ""),
                    "league": league_name,
                    "season": SEASON,
                    "matches_played": to_int(player.get("games")),
                    "minutes": minutes,
                    "goals": to_int(player.get("goals")),
                    "assists": to_int(player.get("assists")),
                    "shots": to_int(player.get("shots")),
                    "key_passes": to_int(player.get("key_passes")),
                    "yellow_cards": to_int(player.get("yellow_cards")),
                    "red_cards": to_int(player.get("red_cards")),
                    "xg": xg,
                    "npxg": npxg,
                    "xa": xa,
                    "xg_chain": to_float(player.get("xGChain")),
                    "xg_buildup": to_float(player.get("xGBuildup")),
                    "xg_per90": per90(xg, minutes),
                    "xa_per90": per90(xa, minutes),
                    "npxg_per90": per90(npxg, minutes),
                    "source": SOURCE,
                    "source_url": source_url,
                    "last_verified": LAST_VERIFIED,
                }
            )
    return rows


def match_roster(roster_rows, player_rows):
    by_name = {}
    for row in player_rows:
        for variant in name_variants(row["player"]):
            by_name.setdefault(variant, []).append(row)

    matched = []
    missing = []
    trusted = []
    for roster in roster_rows:
        candidates = []
        for variant in name_variants(roster["player"]):
            candidates.extend(by_name.get(variant, []))
        if not candidates:
            roster_norms = name_variants(roster["player"])
            for player in player_rows:
                player_norms = name_variants(player["player"])
                best_name_score = max(
                    SequenceMatcher(None, roster_name, player_name).ratio()
                    for roster_name in roster_norms
                    for player_name in player_norms
                )
                if best_name_score >= 0.88 and club_similarity(roster["club"], player["club"]) >= 0.86:
                    candidates.append(player)
        unique_candidates = {}
        for candidate in candidates:
            unique_candidates[(candidate["player"], candidate["club"], candidate["league"])] = candidate
        candidates = list(unique_candidates.values())
        if not candidates:
            missing.append(roster)
            continue
        best = max(candidates, key=lambda item: club_similarity(roster["club"], item["club"]))
        similarity = club_similarity(roster["club"], best["club"])
        if similarity >= 0.86:
            match_type = "name_and_similar_club"
            recommended_weight = "0.75"
        elif len(candidates) == 1:
            match_type = "name_only_club_differs"
            recommended_weight = "0.55"
        else:
            match_type = "name_only_multiple_candidates"
            recommended_weight = "0.35"

        out = {
            "national_team": roster["team"],
            "team_code": roster["team_code"],
            "group": roster["group"],
            "roster_player": roster["player"],
            "roster_position": roster["position"],
            "roster_club": roster["club"],
            "understat_player": best["player"],
            "understat_position": best["position"],
            "understat_club": best["club"],
            "league": best["league"],
            "season": best["season"],
            "matches_played": best["matches_played"],
            "minutes": best["minutes"],
            "goals": best["goals"],
            "assists": best["assists"],
            "shots": best["shots"],
            "key_passes": best["key_passes"],
            "xg": best["xg"],
            "npxg": best["npxg"],
            "xa": best["xa"],
            "xg_chain": best["xg_chain"],
            "xg_buildup": best["xg_buildup"],
            "xg_per90": best["xg_per90"],
            "xa_per90": best["xa_per90"],
            "npxg_per90": best["npxg_per90"],
            "match_type": match_type,
            "club_similarity": similarity,
            "recommended_weight": recommended_weight,
            "source": best["source"],
            "source_url": best["source_url"],
            "last_verified": LAST_VERIFIED,
            "notes": "Understat Big 5 2025-26 current-season club form. Understat uses its own xG model, not Opta/FBref.",
        }
        matched.append(out)
        if match_type == "name_and_similar_club":
            trusted.append(out)
    return matched, trusted, missing


def coverage_by_team(roster_rows, matched_rows):
    roster_counts = {}
    matched_counts = {}
    for row in roster_rows:
        roster_counts[row["team"]] = roster_counts.get(row["team"], 0) + 1
    for row in matched_rows:
        matched_counts[row["national_team"]] = matched_counts.get(row["national_team"], 0) + 1
    rows = []
    for team in sorted(roster_counts):
        total = roster_counts[team]
        matched = matched_counts.get(team, 0)
        rows.append(
            {
                "team": team,
                "total_roster_players": total,
                "matched_big5_2025_26": matched,
                "missing": total - matched,
                "coverage_pct": round(matched / total, 3),
                "source": "Understat Big 5 2025-26",
                "notes": "Coverage is partial: Understat covers EPL, La Liga, Bundesliga, Serie A, Ligue 1, and RFPL; this pull uses only the five major European leagues.",
            }
        )
    return rows


def write_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    player_rows = build_player_rows()
    roster_rows = load_roster()
    matched, trusted, missing = match_roster(roster_rows, player_rows)
    coverage = coverage_by_team(roster_rows, matched)

    player_fields = [
        "player",
        "understat_id",
        "position",
        "club",
        "league",
        "season",
        "matches_played",
        "minutes",
        "goals",
        "assists",
        "shots",
        "key_passes",
        "yellow_cards",
        "red_cards",
        "xg",
        "npxg",
        "xa",
        "xg_chain",
        "xg_buildup",
        "xg_per90",
        "xa_per90",
        "npxg_per90",
        "source",
        "source_url",
        "last_verified",
    ]
    match_fields = list(matched[0].keys()) if matched else []
    missing_fields = [
        "team",
        "team_code",
        "group",
        "player",
        "position",
        "club",
        "source",
        "notes",
    ]
    missing_rows = [
        {
            "team": row["team"],
            "team_code": row["team_code"],
            "group": row["group"],
            "player": row["player"],
            "position": row["position"],
            "club": row["club"],
            "source": "Understat Big 5 2025-26",
            "notes": "No exact player-name match in the pulled Understat Big 5 2025-26 player table.",
        }
        for row in missing
    ]

    write_csv(PROCESSED_DIR / "club_player_form_understat_big5_2025_26.csv", player_rows, player_fields)
    write_csv(PROCESSED_DIR / "player_form_matched_understat_big5_2025_26.csv", matched, match_fields)
    write_csv(PROCESSED_DIR / "player_form_trusted_understat_big5_2025_26.csv", trusted, match_fields)
    write_csv(PROCESSED_DIR / "player_form_missing_understat_coverage.csv", missing_rows, missing_fields)
    write_csv(
        PROCESSED_DIR / "player_form_coverage_by_team_understat_2025_26.csv",
        coverage,
        ["team", "total_roster_players", "matched_big5_2025_26", "missing", "coverage_pct", "source", "notes"],
    )

    print(f"players={len(player_rows)} matched={len(matched)} trusted={len(trusted)} missing={len(missing)}")


if __name__ == "__main__":
    main()
