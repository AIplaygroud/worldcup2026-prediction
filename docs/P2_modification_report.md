# P2 修改报告 — EventFlow / Source Fusion 可靠性增强

**日期:** 2026-06-19  
**范围:** 3 场 MVP 闭环验证（未启动 48 队正式预测）

---

## 一、P2 完成项摘要

| 编号 | 要求 | 状态 | 关键改动 |
|------|------|------|----------|
| 1 | 半全场 Top3 主客队/强弱队视角 | ✅ | `scenario_htft_semantics.py` + 重写 `eventflow_htft.py` |
| 2 | 赛前/赛后数据隔离 | ✅ | source 表新增 `kickoff_time/available_before_kickoff/evidence_usage` |
| 3 | B 级 Source Fusion 严格校验 | ✅ | 缺 `source_url`/`published_at` → C；7 项准入 |
| 4 | V2 λ 与比赛类型差异诊断 | ✅ | `v2_engine_diagnostics.json` + merge JSON `diagnostics` |
| 5 | 权重量纲统一 | ✅ | `raw_*` + `normalized_weight` 分列 |
| 6 | 按比赛拆分 source_notes | ✅ | `source_notes/<match_id>.csv` 优先 |
| 7 | 3 场真实数据增强测试 | ✅ | 见下文 |

---

## 二、半全场视角修复（核心）

### 问题（P1）
Brazil vs Haiti 出现 `胜/胜、负/负、平/负` — 剧本 `htft_bias` 写死中文标签，未结合 favorite/home 视角。

### 修复
1. 语义模式：`favorite_leads_ht|favorite_wins_ft`、`underdog_holds_ht|favorite_wins_ft` 等（见 `scenario_htft_semantics.py`）
2. 运行时映射：根据 `lambda_home/away` 判定强队 → 映射为主队视角 `胜/平/负`
3. 强弱悬殊过滤：主队为强队时，抑制 `负/*`、`*/负` 等 upset 组合，除非 S08/S07/S05 权重 ≥0.12 或高置信赛前证据
4. 输出字段：`label, score, perspective_basis, supporting_scenarios, why_not_others`

### 修复后 Top3（Brazil vs Haiti）
| 排名 | 半全场 | perspective_basis |
|------|--------|-------------------|
| 1 | **平/胜** | draw_ht\|favorite_wins_ft；强队=Brazil(主队) |
| 2 | **胜/胜** | favorite_leads_ht\|favorite_wins_ft |
| 3 | **平/平** | underdog_holds_ht\|draw_ft（Haiti 低位上半场） |

**不再出现** `负/负、平/负` 等反向组合。

---

## 三、赛前/赛后证据隔离

### 新增字段
```csv
published_at,kickoff_time,available_before_kickoff,evidence_usage
```

- `available_before_kickoff = published_at < kickoff_time`（自动推断或显式填写）
- `evidence_usage`: `pre_match_prediction` / `post_match_review` / `backtest_only`

### 规则
- 正式赛前预测：**仅** `available_before_kickoff=true` 或 `evidence_usage=pre_match_prediction` 进入 fusion 加权
- 赛后战报（含 `minute` 或 kickoff 后 `published_at`）→ C 级，不参与 `scenario_weights`

### 三场隔离结果

| 比赛 | 赛前证据 | 赛后证据 | 排除赛后 | 加权 B 级 |
|------|----------|----------|----------|-----------|
| WC2026-C29 Brazil–Haiti | 2 | 2 | 2 | 2 |
| WC2026-L22 England–Croatia | 3 | 1 | 1 | 3 |
| WC2026-J43 Argentina–Austria | 3 | 1 | 1 | 3 |

JSON 输出含：`pre_match_evidence_count`, `post_match_evidence_count`, `excluded_post_match_evidence_count`

---

## 四、B 级准入（严格）

B 级需同时满足：
1. `source_url` ✓
2. `source_type` ✓
3. `source_authority >= 0.70` ✓
4. `evidence_snippet` 非空 ✓
5. `tactical_specificity >= 0.20` ✓
6. `single_source_penalty = 0.65` ✓
7. `published_at` 非空 ✓

**Brazil P1 问题：** 4 条全 B → **P2：** 2 条 B（赛前），2 条 C（赛后 R1 战报）

---

## 五、V2 λ 诊断与「模板化」自查

### 三场 λ 与诊断

| 比赛 | 类型 | λ_home | λ_away | xg_source | default_used | degraded | V2 Top3 |
|------|------|--------|--------|-----------|--------------|----------|---------|
| WC2026-C29 | 强弱悬殊 | 2.59 | 0.84 | wc2026_team_xg_adj | false | false | 2-0, 3-0, 2-1 |
| WC2026-L22 | 强强对话 | 2.63 | 0.82 | wc2026_team_xg_adj | false | false | 2-0, 3-0, 2-1 |
| WC2026-J43 | 实力接近 | 1.82 | 1.04 | wc2026_team_xg_adj | false | false | **1-1, 1-0, 2-1** |

### England vs Croatia 为何仍像强弱悬殊？

**非默认参数/template 退化**（`probability_data_degraded=false`）：

1. **V2 结构原因：** Croatia 近期 xGA 经 adj 后 base λ_away=0.73，与 Haiti(0.84) 同属「弱防守 xGA 档位」；England base λ_home=2.45 与 Brazil 2.45 几乎相同 → λ 比 3.20 vs 3.10，Poisson Top3 自然同为 2-0/3-0/2-1
2. **EventFlow 差异已拉开：** England 场 S01 `raw_total_score=0.40` vs Brazil 场 `2.54`；activated 权重更分散（0.16 vs 0.29），反映 matchup 矩阵对强强对话的 imbalance 更低
3. **待 P3：** 为 L 组强强对话补充 `S10_tactical_stalemate` 高权重 + Croatia 控场 source → 压低 S01 大比分剧本

Argentina–Austria **已分化**：V2 Top1 为 1-1，融合 Top3 为 2-1/2-0/3-1，符合中等差距预期。

---

## 六、权重量纲

`eventflow_scenario_weights.csv` 现含：

```csv
raw_base_weight,raw_tactical_delta,raw_player_delta,raw_source_delta,
raw_probability_context_delta,raw_total_score,normalized_weight
```

- `activated_scenarios` 输出 `normalized_weight`
- `weight_composition` 展示 raw 贡献，**禁止** raw delta 与 normalized 混比

示例（Brazil S01）：raw_total=2.54 → normalized=0.289

---

## 七、按比赛 source_notes

路径：`database/eventflow/raw_sources/source_notes/<match_id>.csv`

Pipeline（`run_dual_engine_pipeline.py`）优先读取该文件，不存在则回退总表。

---

## 八、三场增强测试结论

| 指标 | C29 强弱 | L22 强强 | J43 接近 |
|------|----------|----------|----------|
| 使用赛前证据 | ✅ 2/4 加权 | ✅ 3/4 加权 | ✅ 3/4 加权 |
| 真实数据比例 | 31% | 71% | 71% |
| 估算数据比例 | 69% | 29% | 29% |
| V2 degraded | false | false | false |
| EventFlow degraded | false | false | false |
| HTFT 合理 | ✅ 平/胜主导 | ✅ 平/胜+平/平 | ✅ 平/胜+平/平 |
| 模板化残留 | V2 Top3 典型强胜 | **V2 Top3 仍似悬殊**（见第五节） | 已分化 |

---

## 九、修改文件清单

| 文件 | 改动 |
|------|------|
| `scripts/scenario_htft_semantics.py` | 新增语义映射 |
| `scripts/eventflow_htft.py` | HTFT 视角 + 证据计数 + per-match notes 路径 |
| `scripts/extract_source_signals.py` | 时间隔离字段 |
| `scripts/cross_source_validate_signals.py` | 严格 B 级 |
| `scripts/fuse_signals_to_eventflow.py` | 赛前过滤 + match_id |
| `scripts/build_eventflow_scenario_weights.py` | raw/normalized 权重 + htft_semantic |
| `scripts/predict_eventflow.py` | 新 HTFT 入参 + 权重 JSON |
| `scripts/merge_dual_engine_predictions.py` | V2 诊断 + 证据隔离 JSON |
| `scripts/predict_v2.py` | `build_v2_diagnostics` 导出 |
| `scripts/run_source_fusion_pipeline.py` | per-match + append |
| `scripts/run_dual_engine_pipeline.py` | 自动 notes 路径 |
| `database/eventflow/raw_sources/source_notes/WC2026-*.csv` | 三场独立 source |

---

## 十、P3 建议（未实施）

1. **强强对话 xG 校准：** Croatia / 其他强队 recent xGA 与大赛表现分离建模，避免 λ_away 被压至 0.8 档
2. **S10 互锁剧本：** 为 England–Croatia 类比赛在 matchup 矩阵写入 `matchup_imbalance_index < 0.15` + source `tactical_mutual_lock`
3. **England/Croatia 球员层：** 补 `player_style` 真实行（当前 missing player_shift）
4. **A 级多源交叉：** 同一 signal 2+ 独立 source → A 级，降低单源 B 放大风险

---

**结论：** P2 目标「逻辑可靠、数据可信、赛前可用」在三场 MVP 上已达成闭环；半全场视角错误已修复，证据隔离与 B 级门槛生效。**未启动 48 队正式预测。**
