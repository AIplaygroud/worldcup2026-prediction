from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Dict, Any, Optional

PHASES = [
    (0, 15, "0-15"),
    (16, 30, "16-30"),
    (31, 45, "31-45+"),
    (46, 60, "46-60"),
    (61, 75, "61-75"),
    (76, 130, "76-90+"),
]

SIGNAL_KEYWORDS = {
    "pressing_success": ["press", "pressed", "pressure", "gegenpress", "won it high", "forced error"],
    "pressing_broken": ["played through", "broke the press", "escaped pressure", "beat the press"],
    "low_block_success": ["low block", "deep block", "sat deep", "compact", "frustrated"],
    "low_block_failure": ["opened up", "stretched", "space between", "pulled apart", "overload"],
    "transition_threat": ["counter", "break", "transition", "space in behind", "ran behind"],
    "set_piece_edge": ["corner", "free kick", "set-piece", "set piece", "aerial"],
    "goalkeeper_error": ["goalkeeper error", "goalkeeper claim error", "failed goalkeeper", "failed collection", "howler", "spilled", "dropped", "failed to claim"],
    "card_or_referee_chaos": ["red card", "second yellow", "sent off", "strict referee", "physical contact", "reckless challenge"],
    "injury_or_forced_substitution": ["injury", "forced off", "stretcher", "limped off"],
    "late_game_opening": ["late", "stoppage", "added time", "equaliser", "winner"],
    "position_shift": ["switched", "moved to", "shifted", "inverted", "false nine", "wing-back"],
    "strong_side_attack": ["right flank", "left flank", "wide", "overlap", "underlap"],
    "tactical_mutual_lock": ["cagey", "stalemate", "cancelled", "neutralised", "few chances"],
    "group_draw_control": [
        "draw is enough", "point is enough", "control the game",
        "qualification scenario", "can qualify with a draw",
        "accept a draw", "manage the result", "late draw control",
    ],
    "group_table_pressure": [
        "must win", "need three points", "cannot afford to lose",
        "bottom of the group", "goal difference pressure",
        "qualification pressure",
    ],
    "rotation_risk": [
        "rotate", "rotation", "rest players", "fresh legs",
        "manage minutes", "squad rotation",
    ],
    "starter_rest_signal": [
        "benched", "rested", "not risked", "limited minutes",
        "load management",
    ],
    "buildup_gk_error": [
        "goalkeeper error", "poor pass from the goalkeeper",
        "spilled", "dropped", "failed to claim", "build-up mistake",
    ],
    "buildup_press_risk": [
        "played out from the back", "build-up under pressure",
        "pressed the goalkeeper", "forced a mistake in build-up",
    ],
    "weather_heat_humidity": [
        "heat", "humidity", "hot conditions", "cooling break",
        "high temperature",
    ],
    "travel_fatigue": [
        "travel", "long flight", "time zone", "short turnaround",
        "fatigue", "recovery",
    ],
    "pitch_adaptation": [
        "pitch", "surface", "turf", "grass", "stadium conditions",
        "ball speed",
    ],
    "var_penalty_swing": [
        "VAR", "penalty", "handball", "spot kick",
        "penalty check", "reviewed by VAR",
    ],
    "box_defending_risk": [
        "late tackle in the box", "clumsy challenge",
        "defending inside the box", "contact in the area",
    ],
}

@dataclass
class SourceSignal:
    match_id: str
    source_id: str
    source_url: str
    source_title: str = ""
    published_at: str = ""
    minute: str = ""
    team: str = ""
    player: str = ""
    signal_type: str = ""
    summary: str = ""
    evidence_snippet: str = ""
    scenario_tags: str = ""
    source_authority: float = 0.5
    timestamp_precision: float = 0.0
    tactical_specificity: float = 0.0
    data_consistency: float = 0.5
    raw_confidence: float = 0.0


def stable_id(*parts: str) -> str:
    text = "|".join(p or "" for p in parts)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def minute_to_bucket(minute: str) -> str:
    if not minute:
        return "unknown"
    m = re.search(r"(\d+)", str(minute))
    if not m:
        return "unknown"
    val = int(m.group(1))
    for lo, hi, name in PHASES:
        if lo <= val <= hi:
            return name
    return "unknown"


def detect_signal_type(text: str) -> str:
    low = text.lower()
    best_type = "general_observation"
    best_hits = 0
    for signal_type, kws in SIGNAL_KEYWORDS.items():
        hits = sum(1 for kw in kws if kw in low)
        if hits > best_hits:
            best_hits = hits
            best_type = signal_type
    return best_type


def tactical_specificity_score(text: str) -> float:
    tactical_terms = [
        "formation", "press", "block", "transition", "overload", "half-space", "flank", "line",
        "full-back", "wing-back", "counter", "set-piece", "build-up", "compact", "inverted",
        "false nine", "pivot", "switch", "rest defence", "marking", "space in behind",
    ]
    low = text.lower()
    hits = sum(1 for t in tactical_terms if t in low)
    return min(1.0, hits / 5.0)


def timestamp_precision_score(minute: str) -> float:
    if not minute:
        return 0.0
    return 1.0 if re.search(r"\d+", str(minute)) else 0.3


def compute_raw_confidence(source_authority: float, timestamp_precision: float, tactical_specificity: float, data_consistency: float) -> float:
    return round(0.45 * source_authority + 0.20 * timestamp_precision + 0.20 * tactical_specificity + 0.15 * data_consistency, 4)


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
