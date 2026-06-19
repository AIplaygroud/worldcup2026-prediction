# EventFlow V3.0 数据字典

## 1. `player_foot_position_profile.csv`

| 字段 | 含义 |
|---|---|
| player_id | 球员唯一 ID，缺失时可用球员名 |
| player | 球员名 |
| team | 国家队 |
| club | 俱乐部 |
| primary_position | 常规主位置 |
| secondary_positions | 可胜任副位置 |
| preferred_foot | 惯用脚：left/right/both/unknown |
| weak_foot_note | 弱足说明，缺失时 manual_required |
| role_tags | 球员风格标签 |
| role_family | forward / wide_attacker / midfielder / defender / goalkeeper |
| same_foot_side | 是否顺足侧使用，unknown 需要结合本场站位 |
| inverted_role_possible | 是否具备逆足内切可能 |
| two_footed_score | 双足能力估计，0~1 |
| position_flexibility_score | 位置灵活度，0~1 |
| profile_confidence | 资料置信度 |
| source_urls | 来源 URL 列表 |

## 2. `player_worldcup_position_shift.csv`

| 字段 | 含义 |
|---|---|
| listed_position | 官方/阵容显示位置 |
| actual_role | 观察到的实际职责 |
| league_primary_position | 联赛/常规主位置 |
| side | left / center / right |
| role_shift_type | role_or_position_changed / inverted_side_usage / same_lane_usage / stable_or_unknown |
| x_shift / y_shift | 平均站位相对中点偏移 |
| touch_side_bias | 触球侧重 |
| inverted_usage | 是否逆足使用 |
| position_shift_score | 位置偏移强度 |
| tactical_meaning | 对本场推演的战术含义 |

## 3. `team_tactical_profile.csv`

| 字段 | 含义 |
|---|---|
| pressing_height | 高位压迫 / 中位压迫 / 低位被动 |
| build_up_style | 控球推进 / 混合推进 / 直接打法 |
| attack_width | 边路宽度能力 |
| central_progression | 中路/肋部推进能力 |
| transition_attack | 转换进攻能力 |
| set_piece_attack | 定位球进攻 |
| set_piece_defense | 定位球防守 |
| low_block_quality | 低位防守质量 |
| high_line_risk | 高位防线身后风险 |
| rest_defense_quality | 防反保护能力 |
| late_game_aggression | 末段压上倾向 |
| comeback_tendency | 落后追分倾向 |
| collapse_risk | 崩盘风险 |
| chaos_index | 比赛混沌倾向 |
| break_low_block_score | 破低位能力 |
| defend_pressure_score | 抗压防守能力 |

## 4. `tactical_matchup_matrix.csv`

| 字段 | 含义 |
|---|---|
| home_breakthrough_score / away_breakthrough_score | 主/客破阵分 |
| home_control_score / away_control_score | 主/客控制比赛能力 |
| home_transition_edge / away_transition_edge | 转换进攻优势 |
| home_set_piece_edge / away_set_piece_edge | 定位球优势 |
| home_flank_edge / away_flank_edge | 边路错位优势 |
| home_central_edge / away_central_edge | 中路推进优势 |
| home_press_trap_edge / away_press_trap_edge | 高压陷阱优势 |
| home_shape_countered_by_away | 主队阵型是否被客队克制 |
| away_shape_countered_by_home | 客队阵型是否被主队克制 |
| likely_breakthrough_path_* | 可能破阵路径 |
| likely_defensive_survival_path_* | 可能守住路径 |

## 5. `eventflow_scenario_weights.csv`

| 字段 | 含义 |
|---|---|
| scenario_id | 剧本 ID |
| scenario_name | 剧本名称 |
| weight | 本场剧本权重，所有剧本归一化 |
| score_family | 该剧本支持的比分族 |
| htft_bias | 半全场倾向 |
| triggered_by | 触发来源 |
| data_confidence | 数据置信度 |

### V3.2 新增剧本 S11–S16

| scenario_id | 名称 | 主要信号来源 |
|---|---|---|
| S11_group_state_draw_control | 小组积分/接受平局/控节奏 | `group_draw_control`、积分榜 R2/R3 |
| S12_rotation_tempo_drop | 轮换/保主力节奏下降 | `rotation_risk`、`starter_rest_signal` |
| S13_must_win_early_aggression | 必须抢分开局冒进 | `group_table_pressure`、积分榜 |
| S14_buildup_gk_error_chain | 门将/后场出球失误链 | `buildup_gk_error`、`buildup_press_risk` |
| S15_weather_travel_pitch_adaptation | 天气/旅行/场地适应 | `weather_heat_humidity`、`travel_fatigue`、`pitch_adaptation` |
| S16_var_penalty_momentum_swing | VAR/点球/争议判罚 | `var_penalty_swing`、`box_defending_risk`、裁判层 |

`goalkeeper_error` 信号映射至 S14（不再默认进 S01）。`card_or_referee_chaos` 保留给 S08；VAR/点球类信号映射 S16。

| 字段 | 含义 |
|---|---|
| weight_gates | JSON：gate 状态（如 `s13_group_pressure_gate`、`duplicate_press_cap_applied`） |
| evidence_refs | 分号分隔的证据引用（signal_type 或 `structured_buildup_risk`） |

`weight_composition.gates`（JSON 输出）示例：

```json
{
  "specific_buildup_evidence": true,
  "duplicate_press_cap_applied": false,
  "evidence_refs": ["buildup_press_risk"]
}
```

Gate 触发时写入 `gate_applied: true` 与 `gate_reason`。

### V3.2 新增 signal_type

| signal_type | 映射剧本 |
|---|---|
| group_draw_control | S11 |
| group_table_pressure | S13 |
| rotation_risk / starter_rest_signal | S12 |
| buildup_gk_error / buildup_press_risk | S14 |
| weather_heat_humidity / travel_fatigue / pitch_adaptation | S15 |
| var_penalty_swing / box_defending_risk | S16 |

## 6. `dual_engine_predictions.csv`

| 字段 | 含义 |
|---|---|
| probability_engine_prob | 概率派比分概率 |
| eventflow_prob | 事件流比分权重 |
| final_weight | 双引擎融合权重 |
| total_goals_bucket | 总进球桶 |
| htft | 半全场胜负 |
| main_reason | 主要事件流原因 |
| risk_note | 风险提示 |
