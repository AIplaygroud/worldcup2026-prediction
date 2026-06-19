# P4 数据补全报告 — C/D 组第二轮（R2）

**执行时间**: 2026-06-19  
**模式**: EventFlow 数据补全（未运行 `predict_v2` / 双引擎正式预测）  
**脚本**: `scripts/eventflow_cd_r2_data_completion.py`

---

## 已补全比赛

| match_id | 对阵 | 开球 (ET) |
|----------|------|-----------|
| WC2026-C29 | Brazil vs Haiti | 2026-06-19 21:00 |
| WC2026-C30 | Scotland vs Morocco | 2026-06-19 18:00 |
| WC2026-D31 | Turkey vs Paraguay | 2026-06-19 20:00 |
| WC2026-D32 | USA vs Australia | 2026-06-19 12:00 |

---

## 真实来源数量

| 场次 | source_notes 条数 | 赛前可用 (pre_match) | 赛后/回测 | example.com |
|------|-------------------|----------------------|-----------|-------------|
| C29 | 8 | 8 | 0 | 0 |
| C30 | 8 | 8 | 0 | 0 |
| D31 | 8 | 8 | 0 | 0 |
| D32 | 8 | 8 | 0 | 0 |

**来源类型分布（A/B/C 证据等级，融合后）**  
- **A 级**（官方/高权威单源或双源确认）: FIFA Match Centre、FotMob R1 xG  
- **B 级**（专业媒体/预览，单源降权）: Yahoo、SI、Socceroos、Opta Analyst、Covers  
- **C 级**（仅摘要、不参与加权）: 部分 general_observation、内部策略备注  

每场上融合流水线产出约 **3–6 条 B/A 加权证据** → `eventflow_fused_evidence.csv`。

---

## 替换掉的 demo / example.com

已归档至 `database/_archive/demo_seed_backup/`：

| 原文件 | 说明 |
|--------|------|
| `eventflow/raw_sources/source_notes.csv` | 10 条 example.com demo |
| `player_style/raw/raw_player_master.csv` | 6 人 manual/example.com |
| `team_style/raw/raw_team_phase_metrics.csv` | 6 队 example.com + is_estimated |
| `team_style/processed/team_formation_matchups.csv` | L22/J43 demo 预览 |
| `eventflow/processed/dual_engine_output.json` | 含 demo source_url 的旧预测输出 |
| `eventflow/processed/mvp_mismatch_output.json` | 旧 demo 运行产物 |
| `source_notes/WC2026-L22.csv`, `WC2026-J43.csv` | 非本轮 demo 文件 |

**活跃路径中 example.com 计数: 0**（source_notes 子目录已验证）。

---

## 球员真实数据比例

| 场次 | 双方球员行 | is_estimated=false 比例 | 说明 |
|------|------------|-------------------------|------|
| C29 | 26 | 92.3% | 2 人 Haiti 替补样本标记 estimated |
| C30 | 23 | 95.7% | 1 人 Morocco estimated |
| D31 | 22 | 100% | Transfermarkt + FIFA 名单 |
| D32 | 18 | 95.5% | 1 人 Okon-Engstler estimated |

**数据源**: Transfermarkt 球员页 + FIFA 官方名单 PDF + FotMob R1 实际站位。

---

## 球队真实数据比例

| 指标 | 值 |
|------|-----|
| R1 阶段指标 (8 队) | **100%** 来自 FotMob/Opta（`wc2026_match_xg.csv`），`is_estimated=false` |
| 高级字段 (ppda/ turnovers 等) | 部分为空或 USA 来自 Opta Analyst 单点 |
| 阵型预览 (4 场) | `is_estimated=true`（预览合成，非赛后追踪） |
| team_profile_degraded | 四场均为 **false** |

---

## source_notes A/B/C 分布（按设计意图）

- **官方**: FIFA Match Centre、FotMob R1、Socceroos 官方、FIFA 名单 PDF  
- **专业媒体**: Yahoo、SI、Opta Analyst  
- **市场参考**: Covers odds（弱权重）  
- **内部上下文**: `wc2026_r2_strategy_notes.md`（`is_estimated=true`，Roadtrips 赛程 URL 作锚点）  

**无** `post_match_review` / `backtest_only` 条目进入 C/D R2 赛前加权（R1 FotMob 证据作为 **pre_match_team_intel**，开球前可用）。

---

## 是否允许进入预测

| match_id | eligible_for_prediction |
|----------|-------------------------|
| WC2026-C29 | **true** |
| WC2026-C30 | **true** |
| WC2026-D31 | **true** |
| WC2026-D32 | **true** |

质量 JSON: `database/eventflow/processed/cd_r2_data_quality_reports.json`

**未运行正式预测** — 等你确认后再执行 `run_dual_engine_pipeline.py`。

---

## 仍需人工确认的数据

1. **阵型预览** (`team_formation_matchups.csv`): 四场均为预览级 `is_estimated=true`，开赛前应以 FIFA 首发名单更新。  
2. **Transfermarkt URL**: 部分 ID 为规范路径，开赛前建议点开验证惯用脚/位置。  
3. **伤停**: Paraguay Caballero（SI 源）、USA Pulisic（Socceroos 源）— 开赛前需再查一次。  
4. **逐分钟时间线**: `raw_match_commentary_signals.csv` 仍空 → `match_timeline_events.csv` 为 0 行（不影响当前 scenario 权重，但无分钟级进程）。  
5. **概率派**: 未改动 `predict_v2.py` / `xGdatabase` — 与本次补全隔离。  
6. **旧预测产物**: `eventflow_predictions.csv` 等可能仍含历史 5 行 demo 输出，正式预测前应覆盖。

---

## 复现命令

```bash
python scripts/eventflow_cd_r2_data_completion.py
# 或分步：
python scripts/update_eventflow_daily.py
python scripts/run_source_fusion_pipeline.py --match-id WC2026-C29 --home Brazil --away Haiti
python scripts/validate_eventflow_data.py
```

---

## 新增/更新文件清单

- `database/eventflow/raw_sources/source_notes/WC2026-{C29,C30,D31,D32}.csv`  
- `database/player_style/raw/raw_player_master.csv` (95 行)  
- `database/team_style/raw/raw_team_phase_metrics.csv` (8 队 FotMob)  
- `database/team_style/processed/team_formation_matchups.csv` (4 场 R2)  
- `database/competition/wc2026_match_id_mapping.csv` (R2 FIFA URL)  
- `database/source_registry/free_source_registry.csv` (+9 来源类型)  
- `scripts/eventflow_cd_r2_data_completion.py`
