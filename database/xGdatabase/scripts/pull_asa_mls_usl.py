"""
Pull MLS / USL Championship / USL League One player xG form from the
American Soccer Analysis (ASA) public API and match it to the World Cup
roster's MLS/USL data gaps (player_form_non_big5_target_gaps.csv).

ASA is a free, reliable, advanced-stats source that publishes per-player
xG / xA totals. It is the cleanest automatable option for North American
leagues (Understat does not cover MLS; FBref direct fetch is 403 here).

Output schema matches processed/player_form_non_big5_supplement_2025_26.csv
so the result can be appended / consumed the same way.
"""
import csv
import json
import os
import time
import unicodedata
import urllib.request
from difflib import SequenceMatcher

API = "https://app.americansocceranalysis.com/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "raw", "club_player_form", "asa_mls_2026")
PROC = os.path.join(ROOT, "processed")
GAPS = os.path.join(PROC, "player_form_non_big5_target_gaps.csv")
OUT = os.path.join(PROC, "player_form_mls_usl_supplement_2026.csv")

LEAGUES = ["mls", "uslc", "usl1"]
SEASONS = ["2026", "2025"]  # 2026 = current/recent form; 2025 = full-season fallback
MIN_MINUTES_2026 = 300       # below this in 2026, fall back to 2025 full season

os.makedirs(RAW, exist_ok=True)


def fetch(url, cache_name):
    """GET JSON with a small on-disk cache so reruns are cheap/idempotent."""
    cache = os.path.join(RAW, cache_name)
    if os.path.exists(cache) and os.path.getsize(cache) > 2:
        with open(cache, "rb") as f:
            return json.loads(f.read())
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=120).read()
    with open(cache, "wb") as f:
        f.write(data)
    time.sleep(0.4)
    return json.loads(data)


def strip_accents(s):
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", s or "")
        if not unicodedata.combining(ch)
    )


def norm(s):
    s = strip_accents(s).lower()
    s = s.replace(".", " ").replace("'", " ").replace("-", " ")
    return " ".join(s.split())


def dedup_tokens(tokens):
    """FIFA roster names repeat the popular name in caps, e.g.
    'Steven STEVEN MOREIRA' -> tokens ['steven','moreira']."""
    out = []
    for t in tokens:
        if t not in out:
            out.append(t)
    return out


def roster_name_variants(raw):
    """Return a set of normalized name variants for a roster player."""
    toks = dedup_tokens(norm(raw).split())
    variants = {" ".join(toks)}
    if len(toks) >= 2:
        variants.add(toks[0] + " " + toks[-1])   # first + last
        variants.add(" ".join(toks[1:]))           # drop leading given name
        variants.add(toks[-1])                      # surname only (weak)
    return {v for v in variants if v}


def sim(a, b):
    return SequenceMatcher(None, a, b).ratio()


def load_gaps():
    rows = []
    with open(GAPS, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["target_league"] == "Major League Soccer":
                rows.append(r)
    return rows


def build_index():
    """Return (player_id->info, team_id->team_name) across all leagues,
    plus xgoals records keyed by (league, season) -> list."""
    players = {}
    teams = {}
    xg = {}
    for lg in LEAGUES:
        try:
            for p in fetch(f"{API}/{lg}/players", f"{lg}_players.json"):
                players[p["player_id"]] = {
                    "name": p.get("player_name", ""),
                    "nat": p.get("nationality", ""),
                }
        except Exception as e:
            print(f"[warn] {lg} players: {e}")
        try:
            for t in fetch(f"{API}/{lg}/teams", f"{lg}_teams.json"):
                teams[t["team_id"]] = t.get("team_name", "")
        except Exception as e:
            print(f"[warn] {lg} teams: {e}")
        for sea in SEASONS:
            try:
                recs = fetch(
                    f"{API}/{lg}/players/xgoals?season_name={sea}&minimum_minutes=1",
                    f"{lg}_xgoals_{sea}.json",
                )
                xg[(lg, sea)] = recs
            except Exception as e:
                print(f"[warn] {lg} xgoals {sea}: {e}")
                xg[(lg, sea)] = []
    return players, teams, xg


def candidate_pool(players, teams, xg):
    """Flatten xgoals into candidate dicts with resolved name + team."""
    pool = {}  # (league, season) -> list of candidates
    for (lg, sea), recs in xg.items():
        lst = []
        for r in recs:
            pid = r.get("player_id")
            info = players.get(pid, {})
            name = info.get("name", "")
            if not name:
                continue
            tid = r.get("team_id")
            if isinstance(tid, list):
                team_name = " / ".join(teams.get(t, "") for t in tid if teams.get(t))
            else:
                team_name = teams.get(tid, "")
            lst.append({
                "league": lg,
                "season": sea,
                "name": name,
                "nname": norm(name),
                "team": team_name,
                "minutes": r.get("minutes_played") or 0,
                "shots": r.get("shots"),
                "goals": r.get("goals"),
                "key_passes": r.get("key_passes"),
                "assists": r.get("primary_assists"),
                "xg": r.get("xgoals"),
                "xa": r.get("xassists"),
            })
        pool[(lg, sea)] = lst
    return pool


def match_player(roster_raw, club, pool):
    """Find the best ASA record for a roster player.
    Returns (record, season, confidence) or (None, None, None).
    Tries 2026 first (recent form); falls back to 2025 if 2026 minutes are low.
    Uses surname-token containment + fuzzy ratio; club name used as a soft guard.
    """
    variants = roster_name_variants(roster_raw)
    toks_r = dedup_tokens(norm(roster_raw).split())
    sig_toks = [t for t in toks_r if len(t) >= 3]   # significant tokens
    collapsed_r = "".join(toks_r)
    surname = toks_r[-1] if toks_r else ""
    club_n = norm(club)

    def best_in(season):
        best = None
        best_score = 0.0
        for lg in LEAGUES:
            for cand in pool.get((lg, season), []):
                cname = cand["nname"]
                collapsed_c = cname.replace(" ", "")
                vmax = max((sim(v, cname) for v in variants), default=0.0)
                cscore = sim(collapsed_r, collapsed_c)
                full_first_last = toks_r[0] + " " + toks_r[-1] if len(toks_r) >= 2 else ""
                exact = cname in variants or (full_first_last and full_first_last == cname)
                # all significant roster tokens appear inside the space-stripped
                # candidate name (handles "Son Heung-min" / "O'Neill" / accents)
                all_sub = bool(sig_toks) and all(t in collapsed_c for t in sig_toks)
                surname_ok = surname and surname in cname.split()
                # given-name guard: first roster token must also appear, to stop
                # surname-only collisions (e.g. Markhus Lacroix vs Duke Lacroix)
                given = toks_r[0] if toks_r else ""
                c_first = cname.split()[0] if cname.split() else ""
                given_ok = bool(given) and (
                    given in collapsed_c or (len(given) >= 3 and c_first.startswith(given[:3]))
                )
                # club similarity: guards spelling-variant matches and breaks ties
                csim = sim(club_n, norm(cand["team"]))
                if exact:
                    score = 1.0
                elif all_sub and cscore >= 0.55:
                    score = max(0.85, cscore)
                elif cscore >= 0.85 and csim >= 0.5:
                    # near-identical full name + same club (umlaut/transliteration
                    # variants e.g. Juergen<->Jurgen, Qasim<->Qasem at same club)
                    score = cscore
                elif surname_ok and given_ok and vmax >= 0.72:
                    score = vmax
                else:
                    continue
                score += 0.05 * csim
                if score > best_score:
                    best_score = score
                    best = cand
        return best, min(best_score, 1.0)

    rec26, s26 = best_in("2026")
    if rec26 and rec26["minutes"] >= MIN_MINUTES_2026 and s26 >= 0.72:
        return rec26, "2026", round(s26, 3)
    rec25, s25 = best_in("2025")
    # prefer whichever season has a confident match w/ enough minutes
    cands = []
    if rec26 and s26 >= 0.72:
        cands.append((rec26, "2026", s26))
    if rec25 and s25 >= 0.72:
        cands.append((rec25, "2025", s25))
    if not cands:
        return None, None, None
    # pick higher minutes if both confident, else higher score
    cands.sort(key=lambda c: (c[2] >= 0.85, c[0]["minutes"]), reverse=True)
    rec, sea, sc = cands[0]
    return rec, sea, round(sc, 3)


def per90(v, minutes):
    if v is None or not minutes:
        return ""
    return round(float(v) / minutes * 90, 3)


def main():
    gaps = load_gaps()
    players, teams, xg = build_index()
    pool = candidate_pool(players, teams, xg)

    out_rows = []
    matched = 0
    unmatched = []
    for g in gaps:
        rec, sea, conf = match_player(g["player"], g["club"], pool)
        if not rec:
            unmatched.append(g["player"] + " (" + g["club"] + ")")
            continue
        matched += 1
        minutes = rec["minutes"]
        league_disp = {"mls": "Major League Soccer", "uslc": "USL Championship",
                       "usl1": "USL League One"}.get(rec["league"], rec["league"])
        conf_label = "asa_exact" if conf >= 0.999 else (
            "asa_high" if conf >= 0.85 else "asa_fuzzy")
        out_rows.append({
            "national_team": g["team"],
            "team_code": g["team_code"],
            "group": g["group"],
            "roster_player": g["player"],
            "roster_position": g["position"],
            "roster_club": g["club"],
            "matched_player": rec["name"],
            "club": rec["team"],
            "league": league_disp,
            "season": sea,
            "matches_played": "",
            "minutes": minutes,
            "goals": rec["goals"],
            "assists": rec["assists"],
            "shots": rec["shots"],
            "key_passes": rec["key_passes"],
            "xg": rec["xg"],
            "npxg": "",
            "xa": rec["xa"],
            "xg_per90": per90(rec["xg"], minutes),
            "xa_per90": per90(rec["xa"], minutes),
            "source": "American Soccer Analysis (ASA) API",
            "source_url": f"{API}/{rec['league']}/players/xgoals?season_name={sea}",
            "last_verified": "2026-06-15",
            "match_confidence": conf_label,
            "recommended_weight": 0.5,
            "notes": (
                f"ASA official advanced stats. season={sea}; "
                f"match_ratio={conf}. xG/xA are open-play+set-play totals "
                f"(penalties included); npxG not separated by ASA totals endpoint."
            ),
        })

    fieldnames = list(out_rows[0].keys()) if out_rows else []
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    print(f"gaps(MLS)={len(gaps)} matched={matched} unmatched={len(unmatched)}")
    print("OUTPUT:", OUT)
    if unmatched:
        print("UNMATCHED:")
        for u in unmatched:
            print("  -", u)


if __name__ == "__main__":
    main()
