#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3.5 betting strategy builder: availability gate + multi-engine candidate scoring + combos."""
from __future__ import annotations

import argparse
import glob
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from eventflow_common import ROOT, read_csv, read_json, write_json

try:
    from scenario_realization_common import load_v37_features
except ImportError:
    load_v37_features = None  # type: ignore

try:
    from v37_common import match_odds_by_teams
except ImportError:
    match_odds_by_teams = None  # type: ignore

ODDS_DB = ROOT / "database" / "jc-odds" / "processed"
EVENTFLOW_DB = ROOT / "database" / "eventflow" / "processed"
PROB_SCORES_CSV = ROOT / "database" / "eventflow" / "raw" / "probability_engine_scores.csv"

SEMANTICS_NOTE = (
    "V2 probability is probabilistic; EventFlow and fusion are ranking/support scores."
)
VALUE_PROXY_NOTE = "value_proxy 仅用于排序，不构成保证收益或真实 EV。"

HAFU_CODE_TO_LABEL = {
    "hh": "主/主", "hd": "主/平", "ha": "主/客",
    "dh": "平/主", "dd": "平/平", "da": "平/客",
    "ah": "客/主", "ad": "客/平", "aa": "客/客",
}
HAFU_SELECTION_RE = re.compile(r"^半全场[主平客](/[主平客])+$")


@dataclass
class MarketAvailability:
    match_key: str
    match: str
    had: str
    hhad: str
    ttg: str
    hafu: str
    crs: str
    note: str
    had_available: bool = False
    hhad_available: bool = False
    ttg_available: bool = False
    hafu_available: bool = False
    crs_available: bool = False
    had_single: bool = False
    hhad_single: bool = False
    ttg_single: bool = False
    hafu_single: bool = False
    crs_single: bool = False


@dataclass
class Candidate:
    match_id: str
    match: str
    market: str
    selection: str
    sp: float
    single_allowed: bool
    parlay_allowed: bool
    v2_model_probability: Optional[float]
    eventflow_alignment: float
    fusion_alignment: float
    value_proxy: Optional[float]
    strategy_score_conservative: float
    strategy_score_balanced: float
    strategy_score_aggressive: float
    supporting_scores: List[str] = field(default_factory=list)
    supporting_scenarios: List[str] = field(default_factory=list)
    risk_note: str = ""
    reason: str = ""
    fusion_topn_limited: bool = False
    conflict_count: int = 0
    tier: str = "balanced"


@dataclass
class ComboLeg:
    match: str
    selection: str
    market: str
    sp: float
    single_allowed: bool
    parlay_allowed: bool
    v2_model_probability: Optional[float]


@dataclass
class ComboRecommendation:
    tier: str
    combo_type: str
    label: str
    legs: List[ComboLeg]
    combo_probability: Optional[float]
    sp_display: str
    combo_score: float
    rationale: str
    risk_note: str
    all_parlay_ok: bool
    all_single_ok: bool


@dataclass
class StrategyResult:
    meta: Dict[str, Any]
    availability_audit: List[MarketAvailability]
    candidate_pool: List[Candidate]
    filtered_out: List[Dict[str, Any]]
    recommended_combos: List[ComboRecommendation]
    sections: Dict[str, str] = field(default_factory=dict)
    emit_recommendations: bool = False

    def to_markdown(self) -> str:
        return render_markdown(self)


def _sp_present(val: Any) -> bool:
    s = str(val or "").strip()
    return s not in ("", "未开售", "None", "nan")


def _single_yes(val: Any) -> bool:
    return str(val or "").strip() == "是"


def _parse_score(score: str) -> Optional[Tuple[int, int]]:
    s = score.replace(":", "-").strip()
    m = re.match(r"^(\d+)-(\d+)$", s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _parse_match_teams(payload: Dict[str, Any]) -> Tuple[str, str]:
    match_line = snum(payload, "match")
    if " vs " in match_line:
        home, away = match_line.split(" vs ", 1)
        return home.strip(), away.strip()
    return "", ""


def _resolve_odds_row(
    payload: Dict[str, Any],
    odds_by_key: Dict[str, Dict[str, str]],
    summary_rows: Sequence[Dict[str, str]],
) -> Optional[Dict[str, str]]:
    """Resolve jc-odds summary row by team names, then fifa id suffix fallback."""
    home_en, away_en = _parse_match_teams(payload)
    if match_odds_by_teams and home_en and away_en:
        row = match_odds_by_teams(home_en, away_en, summary_rows)
        if row:
            return row
    fifa_id = str(payload.get("fifa_match_id", "")).strip()
    if fifa_id:
        suffix = f"{int(fifa_id):03d}"
        for key, row in odds_by_key.items():
            if key.endswith(suffix):
                return row
    return None


def _filter_detail_rows(
    rows: Sequence[Dict[str, str]],
    match_key: str,
    home_cn: str,
    away_cn: str,
) -> List[Dict[str, str]]:
    """Restrict TTG/HAFU/CRS detail rows to this match (matchNumStr + home/away)."""
    return [
        r for r in rows
        if snum(r, "matchNumStr") == match_key
        and snum(r, "homeTeam") == home_cn
        and snum(r, "awayTeam") == away_cn
    ]


def _contains_foreign_team_name(
    selection: str,
    home_cn: str,
    away_cn: str,
    known_teams: Sequence[str],
) -> bool:
    allowed = {t for t in (home_cn, away_cn) if t}
    for team in known_teams:
        if team and len(team) >= 2 and team not in allowed and team in selection:
            return True
    return False


def _valid_hafu_selection(selection: str) -> bool:
    """HAFU parlay legs must use home-perspective 半全场主/平/客 labels only."""
    return bool(HAFU_SELECTION_RE.match(selection.strip()))


def _combo_leg_label(selection: str) -> str:
    """Parlay display label: selection text only (never prefix match team name)."""
    return selection.strip()


def _fusion_score(row: Dict[str, Any]) -> float:
    for k in ("fusion_ranking_score", "normalized_fusion_score"):
        if k in row and row[k] not in (None, ""):
            return float(row[k])
    return 0.0


def _v2_prob(row: Dict[str, Any]) -> float:
    for k in ("v2_scoreline_probability", "raw_probability"):
        if k in row and row[k] not in (None, ""):
            return float(row[k])
    return 0.0


def _eventflow_score(row: Dict[str, Any]) -> float:
    for k in ("eventflow_ranking_score", "eventflow_score"):
        if k in row and row[k] not in (None, ""):
            return float(row[k])
    return 0.0


def _norm_map(values: Sequence[float]) -> List[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _normalize_sum(scores: Dict[str, float], keys: Sequence[str]) -> float:
    total = sum(scores.get(k, 0.0) for k in keys)
    denom = sum(scores.values()) or 1.0
    return total / denom


def load_odds(
    summary_path: Path,
    ttg_path: Path,
    hafu_path: Path,
    crs_path: Path,
) -> Tuple[Dict[str, Dict[str, str]], Dict[str, List[Dict[str, str]]]]:
    summary_rows = read_csv(summary_path)
    by_key = {snum(r, "matchNumStr"): r for r in summary_rows}
    detail: Dict[str, List[Dict[str, str]]] = {"ttg": [], "hafu": [], "crs": []}
    for path, market in ((ttg_path, "ttg"), (hafu_path, "hafu"), (crs_path, "crs")):
        for r in read_csv(path):
            detail[market].append(r)
    return by_key, detail


def snum(row: Dict[str, Any], key: str, default: str = "") -> str:
    v = row.get(key, default)
    return "" if v is None else str(v).strip()


def build_market_availability(odds_row: Dict[str, str], match_label: str) -> MarketAvailability:
    home = snum(odds_row, "homeTeam")
    away = snum(odds_row, "awayTeam")
    had_sp = any(_sp_present(odds_row.get(k)) for k in ("had_home", "had_draw", "had_away"))
    had_single_raw = snum(odds_row, "had_single")
    had_avail = had_sp and had_single_raw != "未开售"
    hhad_avail = any(_sp_present(odds_row.get(k)) for k in ("hhad_home", "hhad_draw", "hhad_away"))
    ttg_avail = int(float(snum(odds_row, "ttg_count") or "0")) > 0
    hafu_avail = int(float(snum(odds_row, "hafu_count") or "0")) > 0
    crs_avail = int(float(snum(odds_row, "crs_count") or "0")) > 0

    def _status(available: bool, single_flag: str) -> str:
        if not available:
            return "未开售"
        if _single_yes(single_flag):
            return "可单关"
        return "仅过关"

    had_single = _single_yes(had_single_raw)
    hhad_single = _single_yes(odds_row.get("hhad_single"))
    ttg_single = _single_yes(odds_row.get("ttg_single"))
    hafu_single = _single_yes(odds_row.get("hafu_single"))
    crs_single = _single_yes(odds_row.get("crs_single"))

    note = ""
    if not had_avail and home:
        note = "HAD 市场未开售，禁止推荐胜平负"

    return MarketAvailability(
        match_key=snum(odds_row, "matchNumStr"),
        match=f"{home} vs {away}",
        had=_status(had_avail, had_single_raw),
        hhad=_status(hhad_avail, snum(odds_row, "hhad_single")),
        ttg=_status(ttg_avail, snum(odds_row, "ttg_single")),
        hafu=_status(hafu_avail, snum(odds_row, "hafu_single")),
        crs=_status(crs_avail, snum(odds_row, "crs_single")),
        note=note,
        had_available=had_avail,
        hhad_available=hhad_avail,
        ttg_available=ttg_avail,
        hafu_available=hafu_avail,
        crs_available=crs_avail,
        had_single=had_single,
        hhad_single=hhad_single,
        ttg_single=ttg_single,
        hafu_single=hafu_single,
        crs_single=crs_single,
    )


def load_scoreline_grid(match_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    pe = match_payload.get("probability_engine", {})
    grid = pe.get("scoreline_probability_grid")
    if grid:
        return grid
    match_id = match_payload.get("match_id", "")
    prob_from = pe.get("probabilities_from", "base_lambda")
    diag = pe.get("diagnostics", {}) or {}
    if prob_from == "v36_realized" and diag.get("scoreline_probability_grid"):
        return diag["scoreline_probability_grid"]
    rows = [r for r in read_csv(PROB_SCORES_CSV) if snum(r, "match_id") == match_id]
    if not rows and prob_from == "adjusted_lambda":
        # probability_engine_scores.csv is rewritten by apply_realtime_lambda_adjustment
        pass
    out = []
    for r in rows:
        out.append({
            "home_goals": int(r["home_goals"]),
            "away_goals": int(r["away_goals"]),
            "score": snum(r, "score"),
            "probability": float(r["probability"]),
        })
    return out


def aggregate_had_prob(grid: List[Dict[str, Any]]) -> Dict[str, float]:
    p_h = p_d = p_a = 0.0
    for g in grid:
        h, a = g["home_goals"], g["away_goals"]
        p = float(g["probability"])
        if h > a:
            p_h += p
        elif h == a:
            p_d += p
        else:
            p_a += p
    return {"home": p_h, "draw": p_d, "away": p_a}


def aggregate_hhad_prob(grid: List[Dict[str, Any]], line: float) -> Dict[str, float]:
    p_h = p_d = p_a = 0.0
    for g in grid:
        h, a = g["home_goals"], g["away_goals"]
        adj = h + line - a
        p = float(g["probability"])
        if adj > 0:
            p_h += p
        elif abs(adj) < 1e-12:
            p_d += p
        else:
            p_a += p
    return {"home": p_h, "draw": p_d, "away": p_a}


def aggregate_ttg_prob(grid: List[Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for g in grid:
        tg = g["home_goals"] + g["away_goals"]
        key = "7+" if tg >= 7 else str(tg)
        out[key] = out.get(key, 0.0) + float(g["probability"])
    return out


def aggregate_crs_prob(grid: List[Dict[str, Any]]) -> Dict[str, float]:
    return {g["score"]: float(g["probability"]) for g in grid}


def build_fusion_map(match_payload: Dict[str, Any]) -> Tuple[Dict[str, float], bool]:
    ranking = match_payload.get("final_fusion", {}).get("score_ranking", [])
    return {_score_key(r["score"]): _fusion_score(r) for r in ranking}, len(ranking) <= 10


def build_eventflow_support(match_payload: Dict[str, Any]) -> Dict[str, Any]:
    ef = match_payload.get("eventflow_engine", {})
    top_scores = ef.get("top_scores", [])
    scenarios = ef.get("activated_scenarios", [])
    families: List[str] = []
    scenario_weights: Dict[str, float] = {}
    for sc in scenarios:
        sid = sc.get("scenario_id", "")[:3]
        scenario_weights[sid] = float(sc.get("normalized_weight", sc.get("weight", 0)))
        families.extend(sc.get("affected_score_families", []))
    return {
        "top_scores": top_scores,
        "families": families,
        "scenario_weights": scenario_weights,
        "total_goals": ef.get("total_goals", ""),
        "half_full_time_top3": ef.get("half_full_time_top3", []),
    }


def _score_key(score: str) -> str:
    parsed = _parse_score(score)
    if not parsed:
        return score
    return f"{parsed[0]}-{parsed[1]}"


def covered_scorelines_for_selection(
    market: str, selection: str, hhad_line: float = 0.0
) -> List[str]:
    if market == "CRS":
        if "/" in selection:
            return [s.strip().replace(":", "-") for s in selection.replace("比分", "").split("/") if s.strip()]
        s = selection.replace("比分", "").strip()
        return [s] if s else []
    if market == "TTG":
        goals: List[int] = []
        sel = selection.replace("总进球", "")
        for part in sel.split("/"):
            part = part.strip()
            if part == "7+":
                goals.extend(range(7, 12))
            elif part.isdigit():
                goals.append(int(part))
        scores = []
        for tg in goals:
            for h in range(8):
                for a in range(8):
                    if h + a == tg:
                        scores.append(f"{h}-{a}")
        return scores
    if market == "HAD":
        scores = []
        for h in range(8):
            for a in range(8):
                if selection.endswith("胜") or selection.endswith("主胜"):
                    if h > a:
                        scores.append(f"{h}-{a}")
                elif "平" in selection and "让" not in selection:
                    if h == a:
                        scores.append(f"{h}-{a}")
                elif selection.endswith("负") or selection.endswith("客胜"):
                    if h < a:
                        scores.append(f"{h}-{a}")
        return scores
    if market == "HHAD":
        scores = []
        for h in range(12):
            for a in range(12):
                adj = h + hhad_line - a
                if "让胜" in selection and adj > 0:
                    scores.append(f"{h}-{a}")
                elif "让平" in selection and abs(adj) < 1e-12:
                    scores.append(f"{h}-{a}")
                elif "让负" in selection and adj < 0:
                    scores.append(f"{h}-{a}")
        return scores
    return []


def fusion_alignment(fusion_map: Dict[str, float], covered: Sequence[str]) -> float:
    if not covered:
        return 0.0
    return _normalize_sum(fusion_map, covered)


def eventflow_alignment(ef: Dict[str, Any], covered: Sequence[str], market: str) -> float:
    if not covered:
        return 0.0
    top = set(ef.get("top_scores", []))
    families = set(ef.get("families", []))
    fam_hits = sum(1 for s in covered if s in families or s in top)
    score_family_support = fam_hits / len(covered)
    scenario_hits = set()
    for s in covered:
        if s in families:
            scenario_hits.add(s)
    sw = ef.get("scenario_weights", {})
    scenario_weight_support = min(1.0, sum(sw.values()) * (len(scenario_hits) / max(1, len(covered))))
    market_specific = 0.0
    tg_text = str(ef.get("total_goals", ""))
    if market == "TTG" and tg_text:
        for s in covered:
            tg = sum(int(x) for x in _parse_score(s) or (0, 0))
            if str(tg) in tg_text or f"{tg}球" in tg_text:
                market_specific = max(market_specific, 0.8)
    if market == "HAFU":
        hf = ef.get("half_full_time_top3", [])
        if hf:
            market_specific = 0.7
    return 0.5 * score_family_support + 0.3 * scenario_weight_support + 0.2 * market_specific


def count_conflicts(
    covered: Sequence[str],
    prob_top: str,
    fusion_top: str,
    ef_tops: Sequence[str],
) -> int:
    if not covered:
        return 0
    hits = 0
    if prob_top in covered:
        hits += 1
    if fusion_top in covered:
        hits += 1
    if any(s in covered for s in ef_tops[:3]):
        hits += 1
    return max(0, 3 - hits)


def score_candidate(
    p: Optional[float],
    fusion_a: float,
    ef_a: float,
    value_proxy: Optional[float],
    p_norm: float,
    value_norm: float,
    conflict_count: int,
) -> Tuple[float, float, float]:
    base_p = p_norm if p is not None else 0.35
    vp = value_norm if value_proxy is not None else 0.0
    cons = 0.60 * base_p + 0.25 * fusion_a + 0.10 * ef_a + 0.05 * vp
    bal = 0.40 * base_p + 0.30 * fusion_a + 0.20 * ef_a + 0.10 * vp
    agg = 0.25 * base_p + 0.30 * fusion_a + 0.25 * ef_a + 0.20 * vp
    if conflict_count >= 2:
        cons = 0.0
        bal *= 0.6
    return cons, bal, agg


def build_reason(
    market: str,
    selection: str,
    fusion_top: str,
    ef: Dict[str, Any],
    prob_top: str,
) -> str:
    parts = []
    if fusion_top and fusion_top in covered_scorelines_for_selection(market, selection):
        parts.append(f"融合首选{fusion_top}")
    if ef.get("top_scores") and any(
        s in covered_scorelines_for_selection(market, selection) for s in ef["top_scores"][:5]
    ):
        parts.append("EventFlow开放")
    if prob_top in covered_scorelines_for_selection(market, selection):
        parts.append(f"概率派支持{prob_top}")
    elif prob_top != fusion_top:
        parts.append(f"概率派Top为{prob_top}，玩法转向总进球/比分/半全场")
    return "；".join(parts) or "多引擎综合支持"


def build_candidates_for_match(
    match_payload: Dict[str, Any],
    odds_row: Dict[str, str],
    avail: MarketAvailability,
    odds_detail: Dict[str, List[Dict[str, str]]],
) -> Tuple[List[Candidate], List[Dict[str, Any]]]:
    match_id = match_payload.get("match_id", "")
    match_label = avail.match
    home_cn = snum(odds_row, "homeTeam")
    away_cn = snum(odds_row, "awayTeam")
    grid = load_scoreline_grid(match_payload)
    had_p = aggregate_had_prob(grid)
    hhad_line = float(snum(odds_row, "hhad_line") or "0")
    hhad_p = aggregate_hhad_prob(grid, hhad_line)
    ttg_p = aggregate_ttg_prob(grid)
    crs_p = aggregate_crs_prob(grid)
    fusion_map, fusion_limited = build_fusion_map(match_payload)
    ef = build_eventflow_support(match_payload)
    prob_top = (match_payload.get("probability_engine", {}).get("top_scores") or ["?"])[0]
    fusion_ranking = match_payload.get("final_fusion", {}).get("score_ranking", [])
    fusion_top = fusion_ranking[0]["score"] if fusion_ranking else prob_top

    raw: List[Candidate] = []
    filtered: List[Dict[str, Any]] = []

    def add_raw(
        market: str,
        selection: str,
        sp: float,
        p: Optional[float],
        parlay_ok: bool,
        single_ok: bool,
        hhad_line_local: float = 0.0,
    ) -> None:
        if not parlay_ok or not _sp_present(sp):
            filtered.append({
                "match": match_label,
                "market": market,
                "selection": selection,
                "reason": "未开售或SP为空",
            })
            return
        covered = covered_scorelines_for_selection(market, selection, hhad_line_local)
        fa = fusion_alignment(fusion_map, covered)
        ea = eventflow_alignment(ef, covered, market)
        vp = (sp * p) if p is not None else None
        conflicts = count_conflicts(covered, prob_top, fusion_top, ef.get("top_scores", []))
        supporting = [s for s in covered if s in fusion_map][:4]
        scenarios = list(ef.get("scenario_weights", {}).keys())[:3]
        c = Candidate(
            match_id=match_id,
            match=match_label,
            market=market,
            selection=selection,
            sp=float(sp),
            single_allowed=single_ok,
            parlay_allowed=parlay_ok,
            v2_model_probability=round(p, 4) if p is not None else None,
            eventflow_alignment=round(ea, 4),
            fusion_alignment=round(fa, 4),
            value_proxy=round(vp, 4) if vp is not None else None,
            strategy_score_conservative=0.0,
            strategy_score_balanced=0.0,
            strategy_score_aggressive=0.0,
            supporting_scores=supporting,
            supporting_scenarios=scenarios,
            risk_note="若上半场无早球，高总进球尾部需下调" if market == "TTG" else "",
            reason=build_reason(market, selection, fusion_top, ef, prob_top),
            fusion_topn_limited=fusion_limited,
            conflict_count=conflicts,
        )
        raw.append(c)

    if avail.had_available:
        for side, label, sp_key, p_key in (
            ("home", f"{home_cn}胜", "had_home", "home"),
            ("draw", "平局", "had_draw", "draw"),
            ("away", f"{away_cn}胜", "had_away", "away"),
        ):
            add_raw("HAD", label, float(odds_row[sp_key]), had_p[p_key], True, avail.had_single)
    else:
        filtered.append({
            "match": match_label,
            "market": "HAD",
            "selection": "胜平负",
            "reason": "HAD 市场未开售，不可购买",
        })

    if avail.hhad_available:
        line_disp = f"{hhad_line:+.0f}".replace("+", "")
        for suffix, sp_key, p_key in (
            ("让胜", "hhad_home", "home"),
            ("让平", "hhad_draw", "draw"),
            ("让负", "hhad_away", "away"),
        ):
            sel = f"{home_cn}({line_disp}){suffix}"
            add_raw(
                "HHAD", sel, float(odds_row[sp_key]), hhad_p[p_key],
                True, avail.hhad_single, hhad_line,
            )

    match_key = snum(odds_row, "matchNumStr")
    if avail.ttg_available:
        ttg_rows = _filter_detail_rows(odds_detail["ttg"], match_key, home_cn, away_cn)
        for r in ttg_rows:
            g = snum(r, "goals")
            sel = f"总进球{g}"
            add_raw("TTG", sel, float(r["sp"]), ttg_p.get(g, 0.0), True, avail.ttg_single)
        # composite TTG 2/3 etc.
        for combo in (("2", "3"), ("3", "4"), ("2", "3", "4")):
            p_sum = sum(ttg_p.get(x, 0.0) for x in combo)
            if p_sum < 0.05:
                continue
            sel = "总进球" + "/".join(combo)
            sps = [float(r["sp"]) for r in ttg_rows if snum(r, "goals") in combo]
            if not sps:
                continue
            add_raw("TTG", sel, min(sps), p_sum, True, avail.ttg_single)

    if avail.hafu_available:
        hafu_rows = _filter_detail_rows(odds_detail["hafu"], match_key, home_cn, away_cn)
        fusion_hf = match_payload.get("final_fusion", {}).get("half_full_time_top3", [])
        top_labels = [h.get("label", "") if isinstance(h, dict) else str(h) for h in fusion_hf[:3]]
        for r in hafu_rows:
            label = snum(r, "label") or HAFU_CODE_TO_LABEL.get(snum(r, "code"), "")
            if not label:
                continue
            sel = f"半全场{label}"
            if not _valid_hafu_selection(sel):
                filtered.append({
                    "match": match_label,
                    "market": "HAFU",
                    "selection": sel,
                    "reason": "半全场选项含非本场球队名或格式非法，已剔除",
                })
                continue
            boost = 1.2 if label in top_labels else 1.0
            add_raw("HAFU", sel, float(r["sp"]), None, True, avail.hafu_single)
            raw[-1].eventflow_alignment = min(1.0, raw[-1].eventflow_alignment * boost)
            raw[-1].fusion_alignment = min(1.0, raw[-1].fusion_alignment * boost)

    if avail.crs_available:
        crs_rows = _filter_detail_rows(odds_detail["crs"], match_key, home_cn, away_cn)
        top_crs = [r["score"] for r in fusion_ranking[:3]]
        for r in crs_rows:
            sc = snum(r, "score").replace(":", "-")
            if sc in ("胜其他", "平其他", "负其他"):
                continue
            p = crs_p.get(sc)
            if p is None and "-" in sc:
                p = crs_p.get(sc)
            add_raw("CRS", f"比分{sc}", float(r["sp"]), p, True, avail.crs_single)
        for combo in (top_crs[:2], top_crs[:3]):
            combo = [c for c in combo if c]
            if len(combo) < 2:
                continue
            p_sum = sum(crs_p.get(c, 0.0) for c in combo)
            sps = []
            for c in combo:
                for r in crs_rows:
                    if snum(r, "score").replace(":", "-") == c:
                        sps.append(float(r["sp"]))
            if sps:
                sel = "比分" + "/".join(combo)
                add_raw("CRS", sel, min(sps), p_sum, True, avail.crs_single)

    ps = [c.v2_model_probability for c in raw if c.v2_model_probability is not None]
    p_norms = _norm_map([p or 0 for p in ps])
    vps = [c.value_proxy or 0 for c in raw]
    v_norms = _norm_map(vps)
    pi = 0
    for i, c in enumerate(raw):
        if c.v2_model_probability is not None:
            pn = p_norms[pi]
            pi += 1
        else:
            pn = 0.35
        vn = v_norms[i]
        cons, bal, agg = score_candidate(
            c.v2_model_probability, c.fusion_alignment, c.eventflow_alignment,
            c.value_proxy, pn, vn, c.conflict_count,
        )
        c.strategy_score_conservative = round(cons, 4)
        c.strategy_score_balanced = round(bal, 4)
        c.strategy_score_aggressive = round(agg, 4)
        if cons >= 0.55:
            c.tier = "safe"
        elif agg >= 0.55:
            c.tier = "aggressive"
        else:
            c.tier = "balanced"

    raw.sort(key=lambda x: -x.strategy_score_balanced)
    return raw, filtered


def _v37_from_payload(match_payload: Dict[str, Any]) -> Dict[str, Any]:
    summary = match_payload.get("v37_guard_summary") or {}
    if summary:
        return summary
    if load_v37_features and match_payload.get("match_id"):
        feat = load_v37_features(match_payload["match_id"])
        return {
            "betting_risk_flags": [],
            "active_flags": feat.get("active_flags", []),
            "_features": feat,
        }
    return {}


def apply_v37_betting_guards(
    candidates: List[Candidate],
    match_payload: Dict[str, Any],
    odds_row: Dict[str, str],
) -> Dict[str, Any]:
    """Phase-1 V3.7 betting adjustments — score modifiers only, audit returned."""
    if load_v37_features is None:
        return {"applied": False}
    feat = load_v37_features(match_payload.get("match_id", ""))
    if not feat.get("loaded"):
        return {"applied": False, "reason": "v37_features_not_loaded"}

    audit_flags: List[str] = []
    home_cn = snum(odds_row, "homeTeam")

    for c in candidates:
        if feat.get("deep_handicap_contra_flag"):
            if c.market == "HHAD" and "让负" in c.selection:
                c.strategy_score_conservative *= 1.12
                c.strategy_score_balanced *= 1.15
                c.strategy_score_aggressive *= 1.10
                c.risk_note = (c.risk_note + "; V3.7 deep_handicap_contra boost").strip("; ")
                audit_flags.append("boost_hhad_underdog_plus")
            if c.market == "HHAD" and "让胜" in c.selection:
                c.strategy_score_conservative *= 0.82
                c.strategy_score_balanced *= 0.78
                c.strategy_score_aggressive *= 0.75
                c.risk_note = (c.risk_note + "; V3.7 deep_handicap_contra penalize").strip("; ")
                audit_flags.append("penalize_favorite_deep_handicap")

        if feat.get("must_win_no_convert_home"):
            if c.market == "HAD" and home_cn in c.selection and "胜" in c.selection:
                c.strategy_score_conservative *= 0.85
                c.strategy_score_balanced *= 0.82
                c.risk_note = (c.risk_note + "; must_win_no_convert").strip("; ")
                audit_flags.append("must_win_does_not_equal_conversion")
        if feat.get("must_win_no_convert_away"):
            away_cn = snum(odds_row, "awayTeam")
            if c.market == "HAD" and away_cn in c.selection and "胜" in c.selection:
                c.strategy_score_conservative *= 0.85
                c.strategy_score_balanced *= 0.82
                audit_flags.append("must_win_does_not_equal_conversion_away")

    return {
        "applied": True,
        "risk_flags": list(dict.fromkeys(audit_flags)),
        "phase1_egci_enabled": False,
    }


def pick_top_per_match(candidates: List[Candidate], n: int = 5) -> List[Candidate]:
    by_match: Dict[str, List[Candidate]] = {}
    for c in candidates:
        by_match.setdefault(c.match, []).append(c)
    out = []
    for _, items in by_match.items():
        out.extend(sorted(items, key=lambda x: -x.strategy_score_balanced)[:n])
    return out


def build_combos(
    candidates: List[Candidate],
    tier: str,
    score_key: str,
    match_teams: Optional[Dict[str, Tuple[str, str]]] = None,
    all_jc_teams: Optional[Sequence[str]] = None,
) -> List[ComboRecommendation]:
    by_match: Dict[str, List[Candidate]] = {}
    for c in candidates:
        by_match.setdefault(c.match, []).append(c)
    matches = list(by_match.keys())
    if len(matches) < 2:
        return []

    def score_fn(c: Candidate) -> float:
        return getattr(c, score_key)

    def _leg_ok(c: Candidate) -> bool:
        if c.market == "HAFU" and not _valid_hafu_selection(c.selection):
            return False
        if match_teams and all_jc_teams:
            home_cn, away_cn = match_teams.get(c.match, ("", ""))
            if _contains_foreign_team_name(c.selection, home_cn, away_cn, all_jc_teams):
                return False
        return True

    picks: Dict[str, Candidate] = {}
    for m, items in by_match.items():
        ranked = sorted(items, key=lambda x: -score_fn(x))
        ranked = [x for x in ranked if _leg_ok(x)] or ranked
        if tier == "safe":
            ranked = [
                x for x in ranked
                if x.conflict_count < 2
                and x.v2_model_probability
                and not (x.market == "HHAD" and "让负" in x.selection)
            ] or ranked
        elif tier == "aggressive":
            ranked = sorted([x for x in items if _leg_ok(x)] or items, key=lambda x: -x.strategy_score_aggressive)
        picks[m] = ranked[0]

    legs = [
        ComboLeg(
            match=c.match,
            selection=c.selection,
            market=c.market,
            sp=c.sp,
            single_allowed=c.single_allowed,
            parlay_allowed=c.parlay_allowed,
            v2_model_probability=c.v2_model_probability,
        )
        for c in picks.values()
    ]
    combo_p = 1.0
    has_p = True
    for leg in legs:
        if leg.v2_model_probability is None:
            has_p = False
            break
        combo_p *= leg.v2_model_probability
    sp_prod = math.prod(leg.sp for leg in legs)
    avg_f = sum(c.fusion_alignment for c in picks.values()) / len(picks)
    avg_e = sum(c.eventflow_alignment for c in picks.values()) / len(picks)
    combo_score = 0.45 * (combo_p if has_p else 0.3) + 0.25 * avg_f + 0.15 * avg_e + 0.15 * min(1.0, sp_prod / 20)

    tier_labels = {
        "safe": "稳健收益型",
        "balanced": "均衡进取型",
        "aggressive": "高收益小注型",
    }
    label = " × ".join(_combo_leg_label(leg.selection) for leg in legs[:3])
    risk = "概率低、小注、非保证收益" if tier == "aggressive" else "关注数据缺口与临场变化"
    if tier == "aggressive":
        risk = "概率低、小注、非保证收益；" + risk

    combos = [
        ComboRecommendation(
            tier=tier_labels.get(tier, tier),
            combo_type="二串一" if len(legs) == 2 else "三串一",
            label=label,
            legs=legs[:3],
            combo_probability=round(combo_p, 4) if has_p else None,
            sp_display=f"SP约{sp_prod:.2f}",
            combo_score=round(combo_score, 4),
            rationale="概率派聚合×融合支持×EventFlow路径；非仅看胜负方向",
            risk_note=risk,
            all_parlay_ok=all(l.parlay_allowed for l in legs),
            all_single_ok=all(l.single_allowed for l in legs),
        )
    ]
    if len(legs) >= 3:
        combos.append(
            ComboRecommendation(
                tier=tier_labels.get(tier, tier),
                combo_type="三串四",
                label=label + "（三串四展开）",
                legs=legs[:3],
                combo_probability=round(combo_p, 4) if has_p else None,
                sp_display=f"含3个二串一+1个三串一；SP区间见各关",
                combo_score=round(combo_score * 0.95, 4),
                rationale="三串四：三个二串一 + 一个三串一；每关仅选一场一玩法",
                risk_note=risk,
                all_parlay_ok=all(l.parlay_allowed for l in legs),
                all_single_ok=False,
            )
        )
    return combos


def build_strategy(
    match_glob: str,
    odds_summary: Path,
    odds_ttg: Path,
    odds_hafu: Path,
    odds_crs: Path,
    mode: str = "balanced",
    use_v37: bool = False,
    emit_recommendations: bool = False,
) -> StrategyResult:
    odds_by_key, odds_detail = load_odds(odds_summary, odds_ttg, odds_hafu, odds_crs)
    summary_rows = read_csv(odds_summary)
    all_jc_teams = sorted({
        snum(r, "homeTeam") for r in summary_rows if snum(r, "homeTeam")
    } | {
        snum(r, "awayTeam") for r in summary_rows if snum(r, "awayTeam")
    })
    match_teams: Dict[str, Tuple[str, str]] = {}
    match_files = sorted(glob.glob(match_glob))
    if not match_files:
        match_files = sorted(str(p) for p in Path(match_glob).parent.glob(Path(match_glob).name))

    all_candidates: List[Candidate] = []
    all_filtered: List[Dict[str, Any]] = []
    audit: List[MarketAvailability] = []
    v37_betting_audits: List[Dict[str, Any]] = []

    for mf in match_files:
        payload = read_json(mf, {})
        if not payload:
            continue
        fifa_id = str(payload.get("fifa_match_id", ""))
        odds_row = _resolve_odds_row(payload, odds_by_key, summary_rows)
        if not odds_row:
            all_filtered.append({
                "match": payload.get("match", mf),
                "market": "ALL",
                "selection": "",
                "reason": f"未找到体彩赔率行 (fifa_match_id={fifa_id})",
            })
            continue
        avail = build_market_availability(odds_row, payload.get("match", ""))
        match_teams[avail.match] = (snum(odds_row, "homeTeam"), snum(odds_row, "awayTeam"))
        audit.append(avail)
        cands, filt = build_candidates_for_match(payload, odds_row, avail, odds_detail)
        if use_v37:
            v37_audit = apply_v37_betting_guards(cands, payload, odds_row)
            if v37_audit.get("applied"):
                v37_betting_audits.append({
                    "match_id": payload.get("match_id", ""),
                    "match": payload.get("match", ""),
                    **v37_audit,
                })
        all_candidates.extend(cands)
        all_filtered.extend(filt)

    pool = pick_top_per_match(all_candidates, 6)
    combos: List[ComboRecommendation] = []
    single_banker: List[Candidate] = []
    if emit_recommendations:
        single_banker = [c for c in pool if c.single_allowed and c.strategy_score_conservative >= 0.5]
        single_banker.sort(key=lambda x: -x.strategy_score_conservative)
        for tier, key in (("safe", "strategy_score_conservative"), ("balanced", "strategy_score_balanced"), ("aggressive", "strategy_score_aggressive")):
            combos.extend(build_combos(pool, tier, key, match_teams, all_jc_teams))

    meta = {
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "odds_last_update": "match_odds_summary.csv",
        "semantics_note": SEMANTICS_NOTE,
        "value_proxy_note": VALUE_PROXY_NOTE,
        "probability_source": "adjusted_probability",
        "market_gate_applied": True,
        "v37_betting_guards": use_v37,
        "emit_recommendations": emit_recommendations,
        "report_type": "market_guard" if not emit_recommendations else "betting_recommendations",
    }
    for mf in match_files:
        payload = read_json(mf, {})
        pe = payload.get("probability_engine", {})
        if pe.get("probabilities_from") == "adjusted_lambda":
            meta["probability_source"] = "adjusted_probability"
            break
        if pe.get("probabilities_from") == "base_lambda":
            meta["probability_source"] = "base_probability"
    result = StrategyResult(
        meta=meta,
        availability_audit=audit,
        candidate_pool=pool,
        filtered_out=all_filtered,
        recommended_combos=combos[:12] if emit_recommendations else [],
        emit_recommendations=emit_recommendations,
    )
    if use_v37:
        result.meta["v37_betting_audit"] = v37_betting_audits
    if emit_recommendations:
        result.sections["single_banker"] = "\n".join(
            f"- {c.match} {c.selection}" for c in single_banker[:5]
        )
    return result


def render_markdown(res: StrategyResult) -> str:
    guard_mode = not res.emit_recommendations
    title = "盘口保护审计报告（V3.7）" if guard_mode else "投注策略推荐（V3.5）"
    lines = [
        f"# {title}",
        "",
        f"> {SEMANTICS_NOTE}",
        f"> {VALUE_PROXY_NOTE}",
    ]
    if guard_mode:
        lines.append("> V3.7 默认仅输出保护性审计，不生成自动串关/主推结论。")
    lines.extend([
        "",
        "## 1. 可售性审计",
        "",
        "| 比赛 | HAD | HHAD | TTG | HAFU | CRS | 备注 |",
        "|---|---|---|---|---|---|---|",
    ])
    for a in res.availability_audit:
        lines.append(
            f"| {a.match} | {a.had} | {a.hhad} | {a.ttg} | {a.hafu} | {a.crs} | {a.note} |"
        )

    lines.extend(["", "## 2. 盘口风险项（诊断排序，非推荐）" if guard_mode else "## 2. 候选玩法池", ""])
    lines.append(
        "| 比赛 | 玩法 | SP | 单关 | 过关 | V2概率 | 融合支持 | EventFlow支持 | 风险 |"
    )
    lines.append("|---|---|---:|---|---|---:|---:|---:|---|")
    for c in res.candidate_pool[:24]:
        p = f"{c.v2_model_probability:.2%}" if c.v2_model_probability is not None else "—"
        lines.append(
            f"| {c.match} | {c.selection} | {c.sp:.2f} | "
            f"{'是' if c.single_allowed else '否'} | {'是' if c.parlay_allowed else '否'} | "
            f"{p} | {c.fusion_alignment:.2f} | {c.eventflow_alignment:.2f} | {c.risk_note or c.reason[:30]} |"
        )

    if res.meta.get("v37_betting_audit"):
        lines.extend(["", "## 3. V3.7 保护性标记", ""])
        for item in res.meta.get("v37_betting_audit", []):
            flags = ", ".join(item.get("risk_flags", [])) or "—"
            lines.append(f"- **{item.get('match', '')}**：{flags}")

    if not guard_mode:
        lines.extend(["", "## 3. 组合推荐", ""])
        for section, tier_filter in (
            ("### A. 概率和收益都可观（稳健）", "稳健"),
            ("### B. 兼顾可能性、赌博性、收益性（均衡）", "均衡"),
            ("### C. 高收益小注型（进取）", "高收益"),
        ):
            lines.append(section)
            lines.append("")
            shown = 0
            for combo in res.recommended_combos:
                if tier_filter not in combo.tier:
                    continue
                leg_txt = " × ".join(l.selection for l in combo.legs)
                lines.append(f"- **{combo.combo_type}**：{leg_txt}")
                lines.append(f"  - SP：{combo.sp_display}；组合概率：{combo.combo_probability or '半全场/比分无校准概率'}")
                lines.append(f"  - 过关：{'均可' if combo.all_parlay_ok else '部分仅过关'}；单关：{'均可' if combo.all_single_ok else '不可全单关'}")
                lines.append(f"  - 理由：{combo.rationale}")
                lines.append(f"  - 风险：{combo.risk_note}")
                shown += 1
                if shown >= 3:
                    break
            lines.append("")

        if res.sections.get("single_banker"):
            lines.extend(["## 4. 单关保底（须全部可单关）", "", res.sections["single_banker"], ""])

    filtered_heading = "## 4. 已过滤项" if guard_mode else "## 5. 已过滤项"
    lines.extend([filtered_heading, ""])
    for f in res.filtered_out:
        lines.append(f"- 已过滤：{f.get('selection')} —— {f.get('reason')}")

    return "\n".join(lines)


def result_to_json(res: StrategyResult) -> Dict[str, Any]:
    items_key = "market_guard_items" if not res.emit_recommendations else "candidate_pool"
    out = {
        "meta": res.meta,
        "availability_audit": [asdict(a) for a in res.availability_audit],
        items_key: [asdict(c) for c in res.candidate_pool],
        "filtered_out": res.filtered_out,
        "recommended_combos": [
            {**asdict(c), "legs": [asdict(l) for l in c.legs]} for c in res.recommended_combos
        ],
    }
    if res.meta.get("v37_betting_guards"):
        out["v37_betting_audit"] = res.meta.get("v37_betting_audit", [])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build V3.5 betting strategy from dual-engine outputs + jc-odds.")
    parser.add_argument(
        "--match-outputs",
        default=str(EVENTFLOW_DB / "dual_engine_output_*_balanced_v36.json"),
        help="Glob of dual_engine_output JSON files",
    )
    parser.add_argument("--odds-summary", default=str(ODDS_DB / "match_odds_summary.csv"))
    parser.add_argument("--odds-ttg", default=str(ODDS_DB / "match_odds_ttg.csv"))
    parser.add_argument("--odds-hafu", default=str(ODDS_DB / "match_odds_hafu.csv"))
    parser.add_argument("--odds-crs", default=str(ODDS_DB / "match_odds_crs.csv"))
    parser.add_argument("--mode", default="balanced", choices=["safe", "balanced", "hit_hunting"])
    parser.add_argument("--use-v37-odds-value", action="store_true",
                        help="Apply V3.7 phase-1 betting guard score adjustments")
    parser.add_argument(
        "--emit-recommendations",
        default="false",
        choices=["true", "false"],
        help="Emit combo/single recommendations (default false: guard-only audit)",
    )
    parser.add_argument(
        "--out",
        default=str(EVENTFLOW_DB / "market_guard_report.md"),
    )
    parser.add_argument(
        "--json-out",
        default=str(EVENTFLOW_DB / "market_guard_report.json"),
    )
    args = parser.parse_args()

    emit_recs = args.emit_recommendations == "true"
    res = build_strategy(
        args.match_outputs,
        Path(args.odds_summary),
        Path(args.odds_ttg),
        Path(args.odds_hafu),
        Path(args.odds_crs),
        mode=args.mode,
        use_v37=args.use_v37_odds_value,
        emit_recommendations=emit_recs,
    )
    md = res.to_markdown()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    write_json(args.json_out, result_to_json(res))
    print(f"Wrote {out_path}")
    print(f"Wrote {args.json_out}")


if __name__ == "__main__":
    main()
