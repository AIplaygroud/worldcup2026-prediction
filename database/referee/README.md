# Referee Decision ΔxG Database

L10 裁判判罚因素模块数据目录（Skill V2.1）。

## 目录

- `raw/` — 抓取原始 JSON/CSV、手工事件标注 `manual_decision_events.csv`
- `processed/` — 模型直接读取的加工表

## 核心表

| 文件 | 用途 |
|---|---|
| `match_officials.csv` | 每场主裁名单与 `status`（confirmed/provisional/unknown） |
| `referee_style_index.csv` | 裁判风格画像（严哨/点球/红牌/流畅度） |
| `team_ref_profile.csv` | 球队判罚暴露度（造点/吃牌/压迫犯规） |
| `decision_events.csv` | 赛后判罚事件与 ΔxG |
| `team_ref_delta_xg.csv` | 球队判罚受益/受损榜 |
| `player_ref_delta_xg.csv` | 球员判罚受益/受损榜 |
| `referee_impact_summary.csv` | 裁判介入影响汇总 |

## 更新流程

```bash
python scripts/fetch_match_officials.py
python scripts/build_referee_style_index.py
python scripts/build_team_ref_profile.py
python scripts/build_decision_events.py
python scripts/build_referee_delta_xg.py
```

`predict_v2.py` 在 L1–L8 之后、Dixon-Coles 之前读取 `referee_style_index.csv` 与 `team_ref_profile.csv` 做小幅 λ 修正。
