import csv
import math
import unicodedata
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT.parent
PROCESSED = ROOT / "processed"
ROSTER = DATABASE / "48-team-roster" / "processed" / "squads_48_teams.csv"
LAST_VERIFIED = "2026-06-15"

# Source xG tables spell some nations differently from the roster. Canonicalize
# both sides (accent-stripped, lowercased) and alias the known mismatches so the
# team join does not drop teams that actually have xG data.
TEAM_ALIASES = {
    "congo dr": "dr congo",
    "czech republic": "czechia",
    "korea republic": "south korea",
    "ir iran": "iran",
    "cote d ivoire": "ivory coast",
    "turkiye": "turkey",
    "united states": "usa",
    "usmnt": "usa",
}


def canon_team(name):
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", name or "")
        if not unicodedata.combining(ch)
    ).lower().strip()
    text = " ".join(text.replace("'", " ").replace(".", " ").split())
    return TEAM_ALIASES.get(text, text)


def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def f(value, default=0.0):
    if value in (None, ""):
        return default
    return float(value)


def i(value, default=0):
    if value in (None, ""):
        return default
    return int(float(value))


def weighted_add(bucket, row, weight, source_label):
    matches = i(row.get("matches_played"))
    weighted_matches = matches * weight
    bucket["weighted_matches"] += weighted_matches
    bucket["raw_matches"] += matches
    bucket["weighted_xg"] += f(row.get("xg_per_match")) * weighted_matches
    bucket["weighted_xga"] += f(row.get("xga_per_match")) * weighted_matches
    bucket["weighted_xgd"] += f(row.get("xgd_per_match")) * weighted_matches
    bucket["weighted_gf"] += f(row.get("goals_for_per_match")) * weighted_matches
    bucket["weighted_ga"] += f(row.get("goals_against_per_match")) * weighted_matches
    bucket["sources"].add(source_label)


def avg(bucket, key):
    if bucket["weighted_matches"] == 0:
        return ""
    return round(bucket[key] / bucket["weighted_matches"], 3)


def percentile(values, value, reverse=False):
    values = [v for v in values if v is not None and not math.isnan(v)]
    if not values:
        return ""
    if len(values) == 1:
        return 1.0
    lower = sum(1 for v in values if v <= value)
    pct = (lower - 1) / (len(values) - 1)
    return round(1 - pct if reverse else pct, 3)


def build_team_recent_form(teams):
    buckets = {
        team: {
            "raw_matches": 0,
            "weighted_matches": 0.0,
            "weighted_xg": 0.0,
            "weighted_xga": 0.0,
            "weighted_xgd": 0.0,
            "weighted_gf": 0.0,
            "weighted_ga": 0.0,
            "sources": set(),
            "qualifier_rows": 0,
            "context_rows": 0,
        }
        for team in teams
    }
    canon_to_team = {canon_team(team): team for team in teams}

    for row in read_csv(PROCESSED / "team_xg_summary.csv"):
        team = canon_to_team.get(canon_team(row["team"]))
        if team is None:
            continue
        weighted_add(buckets[team], row, 1.0, row["competition"])
        buckets[team]["qualifier_rows"] += 1

    for row in read_csv(PROCESSED / "context_xg_summary.csv"):
        team = canon_to_team.get(canon_team(row["team"]))
        if team is None:
            continue
        weighted_add(buckets[team], row, f(row.get("recommended_weight"), 0.5), row["competition"])
        buckets[team]["context_rows"] += 1

    rows = []
    for team in teams:
        bucket = buckets[team]
        weighted_matches = round(bucket["weighted_matches"], 3)
        quality_flag = "ok"
        if weighted_matches == 0:
            quality_flag = "missing_team_xg"
        elif bucket["qualifier_rows"] == 0:
            quality_flag = "context_only"
        elif weighted_matches < 4:
            quality_flag = "thin_sample"

        rows.append(
            {
                "team": team,
                "raw_matches": bucket["raw_matches"],
                "weighted_matches": weighted_matches,
                "recent_xg_per_match": avg(bucket, "weighted_xg"),
                "recent_xga_per_match": avg(bucket, "weighted_xga"),
                "recent_xgd_per_match": avg(bucket, "weighted_xgd"),
                "recent_goals_for_per_match": avg(bucket, "weighted_gf"),
                "recent_goals_against_per_match": avg(bucket, "weighted_ga"),
                "has_qualifier_xg": "yes" if bucket["qualifier_rows"] else "no",
                "context_rows": bucket["context_rows"],
                "sources": " | ".join(sorted(bucket["sources"])),
                "quality_flag": quality_flag,
                "last_verified": LAST_VERIFIED,
                "notes": "Weighted xG uses qualifiers at 1.00 and context rows at each row's recommended_weight.",
            }
        )
    return rows


def build_player_form_summary(roster_rows):
    roster_order = {(r["team"], r["player"]): idx for idx, r in enumerate(roster_rows)}
    roster_lookup = {(r["team"], r["player"]): r for r in roster_rows}
    best = {}

    def put(key, row):
        current = best.get(key)
        if current is None or f(row["recommended_weight"]) >= f(current["recommended_weight"]):
            best[key] = row

    for row in read_csv(PROCESSED / "player_form_matched_understat_big5_2025_26.csv"):
        key = (row["national_team"], row["roster_player"])
        put(
            key,
            {
                "team": row["national_team"],
                "team_code": row["team_code"],
                "group": row["group"],
                "player": row["roster_player"],
                "position": row["roster_position"],
                "club": row["roster_club"],
                "league": row["league"],
                "season": row["season"],
                "matches_played": row["matches_played"],
                "minutes": row["minutes"],
                "goals": row["goals"],
                "assists": row["assists"],
                "shots": row["shots"],
                "key_passes": row["key_passes"],
                "xg": row["xg"],
                "npxg": row["npxg"],
                "xa": row["xa"],
                "xg_per90": row["xg_per90"],
                "xa_per90": row["xa_per90"],
                "source_layer": "understat_big5_2025_26",
                "recommended_weight": row["recommended_weight"],
                "source": row["source"],
                "source_url": row["source_url"],
                "data_status": row["match_type"],
                "last_verified": row["last_verified"],
                "notes": row["notes"],
            },
        )

    manual_path = PROCESSED / "player_form_manual_supplement_2025_26.csv"
    if manual_path.exists():
        for row in read_csv(manual_path):
            key = (row["national_team"], row["roster_player"])
            put(
                key,
                {
                    "team": row["national_team"],
                    "team_code": row["team_code"],
                    "group": row["group"],
                    "player": row["roster_player"],
                    "position": row["roster_position"],
                    "club": row["roster_club"],
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
                    "source_layer": "manual_supplement_2025_26",
                    "recommended_weight": row["recommended_weight"],
                    "source": row["source"],
                    "source_url": row["source_url"],
                    "data_status": row["match_confidence"],
                    "last_verified": row["last_verified"],
                    "notes": row["notes"],
                },
            )

    non_big5_path = PROCESSED / "player_form_non_big5_supplement_2025_26.csv"
    if non_big5_path.exists():
        for row in read_csv(non_big5_path):
            key = (row["national_team"], row["roster_player"])
            put(
                key,
                {
                    "team": row["national_team"],
                    "team_code": row["team_code"],
                    "group": row["group"],
                    "player": row["roster_player"],
                    "position": row["roster_position"],
                    "club": row["roster_club"],
                    "league": row["league"],
                    "season": row["season"],
                    "matches_played": row["matches_played"],
                    "minutes": row["minutes"],
                    "goals": row["goals"],
                    "assists": row["assists"],
                    "shots": row["shots"],
                    "key_passes": row["key_passes"],
                    "xg": row["xg"],
                    "npxg": row["npxg"],
                    "xa": row["xa"],
                    "xg_per90": row["xg_per90"],
                    "xa_per90": row["xa_per90"],
                    "source_layer": "non_big5_supplement_2025_26",
                    "recommended_weight": row["recommended_weight"],
                    "source": row["source"],
                    "source_url": row["source_url"],
                    "data_status": row["match_confidence"],
                    "last_verified": row["last_verified"],
                    "notes": row["notes"],
                },
            )

    # Newly pulled 2025-26 supplements that share the non-Big-5 schema:
    #   - MLS/USL via the American Soccer Analysis official xG API
    #   - Saudi/Eredivisie/Primeira/Qatar/Iran via FootyStats per-player lookup
    # Both layer in by recommended_weight just like the non-Big-5 supplement.
    for sup_path, layer in (
        (PROCESSED / "player_form_mls_usl_supplement_2026.csv", "mls_usl_asa_2026"),
        (PROCESSED / "player_form_non_big5_footystats_supplement.csv", "non_big5_footystats_2025_26"),
    ):
        if not sup_path.exists():
            continue
        for row in read_csv(sup_path):
            key = (row["national_team"], row["roster_player"])
            put(
                key,
                {
                    "team": row["national_team"],
                    "team_code": row["team_code"],
                    "group": row["group"],
                    "player": row["roster_player"],
                    "position": row["roster_position"],
                    "club": row["roster_club"],
                    "league": row["league"],
                    "season": row["season"],
                    "matches_played": row["matches_played"],
                    "minutes": row["minutes"],
                    "goals": row["goals"],
                    "assists": row["assists"],
                    "shots": row["shots"],
                    "key_passes": row["key_passes"],
                    "xg": row["xg"],
                    "npxg": row["npxg"],
                    "xa": row["xa"],
                    "xg_per90": row["xg_per90"],
                    "xa_per90": row["xa_per90"],
                    "source_layer": layer,
                    "recommended_weight": row["recommended_weight"],
                    "source": row["source"],
                    "source_url": row["source_url"],
                    "data_status": row["match_confidence"],
                    "last_verified": row["last_verified"],
                    "notes": row["notes"],
                },
            )

    # FBref 2024-25 is a fallback only when no 2025-26 layer exists.
    for row in read_csv(PROCESSED / "player_form_matched_big5_2024_25.csv"):
        key = (row["national_team"], row["roster_player"])
        if key in best:
            continue
        put(
            key,
            {
                "team": row["national_team"],
                "team_code": row["team_code"],
                "group": row["group"],
                "player": row["roster_player"],
                "position": row["roster_position"],
                "club": row["roster_club"],
                "league": row["league"],
                "season": row["season"],
                "matches_played": row["matches_played"],
                "minutes": row["minutes"],
                "goals": row["goals"],
                "assists": row["assists"],
                "shots": "",
                "key_passes": "",
                "xg": row["xg"],
                "npxg": row["npxg"],
                "xa": row["xag"],
                "xg_per90": row["xg_per90"],
                "xa_per90": row["xag_per90"],
                "source_layer": "fbref_big5_2024_25_fallback",
                "recommended_weight": row["recommended_weight"],
                "source": row["source"],
                "source_url": row["source_url"],
                "data_status": row["match_type"],
                "last_verified": row["last_verified"],
                "notes": "Fallback baseline because no 2025-26 player form row is available.",
            },
        )

    rows = []
    for key, idx in sorted(roster_order.items(), key=lambda item: item[1]):
        if key in best:
            rows.append(best[key])
            continue
        roster = roster_lookup[key]
        rows.append(
            {
                "team": roster["team"],
                "team_code": roster["team_code"],
                "group": roster["group"],
                "player": roster["player"],
                "position": roster["position"],
                "club": roster["club"],
                "league": "",
                "season": "",
                "matches_played": "",
                "minutes": "",
                "goals": "",
                "assists": "",
                "shots": "",
                "key_passes": "",
                "xg": "",
                "npxg": "",
                "xa": "",
                "xg_per90": "",
                "xa_per90": "",
                "source_layer": "missing",
                "recommended_weight": "0.00",
                "source": "",
                "source_url": "",
                "data_status": "missing_player_form",
                "last_verified": LAST_VERIFIED,
                "notes": "No matched 2025-26 row or 2024-25 Big-5 fallback row.",
            }
        )
    return rows


def build_opponent_strength(team_recent_rows):
    numeric_rows = []
    for row in team_recent_rows:
        if row["recent_xgd_per_match"] == "":
            continue
        numeric_rows.append(row)
    xg_values = [f(r["recent_xg_per_match"]) for r in numeric_rows]
    xga_values = [f(r["recent_xga_per_match"]) for r in numeric_rows]
    xgd_values = [f(r["recent_xgd_per_match"]) for r in numeric_rows]
    wm_values = [f(r["weighted_matches"]) for r in numeric_rows]

    rows = []
    for row in team_recent_rows:
        if row["recent_xgd_per_match"] == "":
            attack = defense = xgd = sample = index = ""
        else:
            attack = percentile(xg_values, f(row["recent_xg_per_match"]))
            defense = percentile(xga_values, f(row["recent_xga_per_match"]), reverse=True)
            xgd = percentile(xgd_values, f(row["recent_xgd_per_match"]))
            sample = percentile(wm_values, f(row["weighted_matches"]))
            index = round(0.35 * attack + 0.35 * defense + 0.25 * xgd + 0.05 * sample, 3)
        rows.append(
            {
                "team": row["team"],
                "opponent_strength_index": index,
                "attack_percentile": attack,
                "defense_percentile": defense,
                "xgd_percentile": xgd,
                "sample_size_percentile": sample,
                "weighted_matches": row["weighted_matches"],
                "quality_flag": row["quality_flag"],
                "source": "team_recent_form.csv",
                "last_verified": LAST_VERIFIED,
                "notes": "Relative strength index from weighted xG/xGA/xGD and sample size. Higher is stronger.",
            }
        )
    ranked = [r for r in rows if r["opponent_strength_index"] != ""]
    ranked.sort(key=lambda r: r["opponent_strength_index"], reverse=True)
    rank_by_team = {r["team"]: idx + 1 for idx, r in enumerate(ranked)}
    for row in rows:
        row["strength_rank"] = rank_by_team.get(row["team"], "")
    return rows


def write_quality_notes(team_recent, player_summary):
    qualifier_coverage = read_csv(PROCESSED / "qualifier_xg_coverage.csv")
    context_coverage = read_csv(PROCESSED / "context_xg_coverage.csv")
    non_big5_status_path = PROCESSED / "player_form_non_big5_source_status.csv"
    non_big5_status = read_csv(non_big5_status_path) if non_big5_status_path.exists() else []
    missing_team_xg = [r["team"] for r in team_recent if r["quality_flag"] == "missing_team_xg"]
    context_only = [r["team"] for r in team_recent if r["quality_flag"] == "context_only"]
    player_layers = defaultdict(int)
    for row in player_summary:
        player_layers[row["source_layer"]] += 1

    lines = [
        "# Data Quality Notes",
        "",
        f"Last verified: {LAST_VERIFIED}",
        "",
        "## Generated Summary Tables",
        "",
        "- `team_recent_form.csv`: weighted team xG/xGA recent-form summary from qualifiers and context competitions.",
        "- `player_form_summary.csv`: one row per roster player, preferring the 2025-26 layer with the highest recommended_weight (Understat Big-5, manual/non-Big-5 supplements, MLS-USL ASA API, FootyStats non-Big-5), then FBref 2024-25 fallback.",
        "- `opponent_strength.csv`: relative team strength index derived from `team_recent_form.csv`.",
        "",
        "## Known Team xG Gaps",
        "",
    ]
    for row in qualifier_coverage:
        if row["data_status"] != "public_table_parsed":
            lines.append(f"- {row['competition']}: {row['data_status']} - {row['notes']}")
    for row in context_coverage:
        if row["data_status"] not in ("public_table_parsed", "stats_table_parsed"):
            lines.append(f"- {row['competition']} {row['season']}: {row['data_status']} - {row['notes']}")
    if missing_team_xg:
        lines.append(f"- Teams with no team xG row in current summaries: {', '.join(missing_team_xg)}.")
    if context_only:
        lines.append(f"- Teams with context-only team xG: {', '.join(context_only)}.")

    lines.extend(
        [
            "",
            "## Player Form Coverage",
            "",
            f"- Understat 2025-26 rows: {player_layers['understat_big5_2025_26']}",
            f"- Manual 2025-26 supplement rows: {player_layers['manual_supplement_2025_26']}",
            f"- Non-Big-5 2025-26 supplement rows: {player_layers['non_big5_supplement_2025_26']}",
            f"- MLS/USL (ASA) 2026 rows: {player_layers['mls_usl_asa_2026']}",
            f"- Non-Big-5 FootyStats 2025-26 rows: {player_layers['non_big5_footystats_2025_26']}",
            f"- FBref 2024-25 fallback rows: {player_layers['fbref_big5_2024_25_fallback']}",
            f"- Missing player-form rows: {player_layers['missing']}",
            "",
            "## Non-Big-5 Club Form Gaps",
            "",
        ]
    )
    for row in non_big5_status:
        lines.append(
            f"- {row['target_league']} ({row['club_country_code']}): "
            f"{row['missing_players']} target missing players; "
            f"automation_status={row['automation_status']}; {row['notes']}"
        )

    lines.extend(
        [
            "",
            "## Use In Prediction",
            "",
            "- Do not mix xG models as if they are identical. Keep source-layer weights in downstream modeling.",
            "- `opponent_strength_index` is a relative index for comparison, not an absolute probability.",
            "- Non-Big-5 supplements are lower-confidence than Understat because they mix FotMob, Transfermarkt, FBref snapshots, and public leaderboard snippets.",
            "- Injury/suspension and projected XI files are still separate inputs and should be updated before match-level predictions.",
            "",
        ]
    )
    (PROCESSED / "data_quality_notes.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    roster_rows = read_csv(ROSTER)
    teams = sorted({row["team"] for row in roster_rows})

    team_recent = build_team_recent_form(teams)
    write_csv(
        PROCESSED / "team_recent_form.csv",
        team_recent,
        [
            "team",
            "raw_matches",
            "weighted_matches",
            "recent_xg_per_match",
            "recent_xga_per_match",
            "recent_xgd_per_match",
            "recent_goals_for_per_match",
            "recent_goals_against_per_match",
            "has_qualifier_xg",
            "context_rows",
            "sources",
            "quality_flag",
            "last_verified",
            "notes",
        ],
    )

    player_summary = build_player_form_summary(roster_rows)
    write_csv(
        PROCESSED / "player_form_summary.csv",
        player_summary,
        [
            "team",
            "team_code",
            "group",
            "player",
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
            "xg",
            "npxg",
            "xa",
            "xg_per90",
            "xa_per90",
            "source_layer",
            "recommended_weight",
            "source",
            "source_url",
            "data_status",
            "last_verified",
            "notes",
        ],
    )

    opponent_strength = build_opponent_strength(team_recent)
    write_csv(
        PROCESSED / "opponent_strength.csv",
        opponent_strength,
        [
            "team",
            "strength_rank",
            "opponent_strength_index",
            "attack_percentile",
            "defense_percentile",
            "xgd_percentile",
            "sample_size_percentile",
            "weighted_matches",
            "quality_flag",
            "source",
            "last_verified",
            "notes",
        ],
    )

    write_quality_notes(team_recent, player_summary)
    print(
        "generated",
        len(team_recent),
        "team_recent_form rows,",
        len(player_summary),
        "player_form_summary rows,",
        len(opponent_strength),
        "opponent_strength rows",
    )


if __name__ == "__main__":
    main()
