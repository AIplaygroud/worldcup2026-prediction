# WorldCup2026 Prediction Skill V3.0：EventFlow 事件流赛果派 Agent 执行指南

适用项目：`AIplaygroud/worldcup2026-prediction` / `prediction-skill` 体系  
目标：在现有 V2.0 `xG + 修正层 + Dixon-Coles` 概率派预测链路之外，新增 **EventFlow 事件流推演分支**。  
生成日期：2026-06-19

---

## 0. 版本定位

V3.0 不推翻 `scripts/predict_v2.py`，而是新增一个并行引擎：

```text
Probability Engine：负责 xG、Dixon-Coles、赔率/竞彩规则、稳态比分分布
EventFlow Engine：负责战术对弈、球员惯用脚/位置偏移、比赛阶段、早球/红牌/追分/崩盘、大比分尾部
Dual Merge：负责把两套结果按 safe / balanced / hit_hunting 三种模式融合
```

现有裁判层可继续作为 L10 小幅 ΔxG 修正层，EventFlow 读取它的结论，但不直接把“裁判偏某队”作为强结论。

---

## 1. 本次新增能力

### 1.1 球员层

必须新增并读取：

- 惯用脚：左脚 / 右脚 / 双足 / 未知；
- 擅长位置：主位置、副位置、世界杯实际位置；
- 世界杯第一轮体现出来的位置偏移：是否从俱乐部常规位置改打边路、中路、翼卫、伪九、双前锋；
- 实际站位侧：left / center / right；
- 是否逆足使用：例如右脚左边锋、左脚右边锋；
- 角色标签：爆点边锋、肋部组织者、支点中锋、反击跑手、出球中卫、容易吃牌型边后卫等。

重点：

```text
不要只看球员名气，要看“他在本场可能被如何使用”。
```

例如：

```text
同一个右脚边锋：
- 打右路：更偏传中、下底、拉宽；
- 打左路：更偏内切射门、肋部直塞、牵制边后卫内收。
```

这会影响：

- 能不能突破对方阵型；
- 是传中型破阵还是肋部渗透；
- 是否容易造犯规/造点；
- 大比分尾部是否上升。

---

### 1.2 球队风格层

必须新增并读取：

- 基础阵型；
- 有球阵型；
- 无球阵型；
- 高压/中压/低位；
- 控球推进/直接打法；
- 边路宽度；
- 中路推进；
- 转换进攻；
- 定位球攻防；
- 低位防守质量；
- 高位防线风险；
- rest defense 反击保护；
- late_game_aggression 末段压上倾向；
- comeback_tendency 落后追分倾向；
- collapse_risk 被打崩风险；
- chaos_index 比赛变乱倾向。

---

### 1.3 战术对弈层

必须判断：

```text
A 队是否克制 B 队？
B 队是否能牵制 A 队？
A 队有没有明确破阵路径？
B 队有没有能力守住 A 队攻势？
```

输出字段：

- `home_breakthrough_score`
- `away_breakthrough_score`
- `home_shape_countered_by_away`
- `away_shape_countered_by_home`
- `likely_breakthrough_path_home`
- `likely_breakthrough_path_away`
- `likely_defensive_survival_path_home`
- `likely_defensive_survival_path_away`

破阵路径必须写清楚，例如：

```text
边路套上 + 逆足边锋内切 + 弱侧后点包抄
高压断球 + 前场二次进攻
中路吸引后转移弱侧
定位球身高优势
反击冲身后
```

不能只写“实力更强”。

---

### 1.4 半全场胜负

上一版“半场胜平负”改为 **半全场胜负**。

标准枚举：

```text
胜/胜
胜/平
胜/负
平/胜
平/平
平/负
负/胜
负/平
负/负
```

注意：这是从主队视角输出。

EventFlow 必须根据剧本判断半全场，而不是从全场比分机械反推。例子：

```text
S02 低位守住上半场：偏 平/胜、平/平、平/负
S01 强队早球打开：偏 胜/胜 或 负/负
S07 末段追分开放：偏 平/胜、平/负、胜/平、负/平、胜/负、负/胜
S08 红牌/点球混沌：允许 胜/负、负/胜 这种反转型结果出现
```

---

## 2. 新增目录

把本增量包复制到仓库根目录后，应形成：

```text
database/
  source_registry/
    raw/
    processed/source_registry.csv
  player_style/
    raw/
      raw_player_master.csv
      raw_player_league_stats.csv
      raw_worldcup_lineups_positions.csv
    processed/
      player_foot_position_profile.csv
      player_league_style_profile.csv
      player_worldcup_position_shift.csv
  team_style/
    raw/
      raw_team_phase_metrics.csv
      raw_match_state_response.csv
    processed/
      team_tactical_profile.csv
      team_match_state_response.csv
      team_formation_matchups.csv
      tactical_matchup_matrix.csv
  eventflow/
    raw/
      raw_match_commentary_signals.csv
      manual_tactical_observations.csv
      probability_engine_scores.csv
      actual_results.csv
    processed/
      scenario_library.json
      match_timeline_events.csv
      match_phase_profile.csv
      commentary_signals.jsonl
      tactical_observations.jsonl
      match_state_transitions.csv
      eventflow_scenario_weights.csv
      eventflow_predictions.csv
      dual_engine_predictions.csv
      eventflow_backtest.csv
      eventflow_data_quality.csv
scripts/
  eventflow_common.py
  build_player_foot_position_profile.py
  build_worldcup_position_shift.py
  build_team_tactical_profile.py
  build_tactical_matchup_matrix.py
  build_match_timeline_events.py
  build_eventflow_scenario_weights.py
  predict_eventflow.py
  merge_dual_engine_predictions.py
  validate_eventflow_data.py
  backtest_eventflow.py
  update_eventflow_daily.py
```

---

## 3. 数据获取原则

### 3.1 官方数据优先

优先级：

1. FIFA 官方比赛中心 / FIFA Match Centre；
2. FIFA Training Centre Match Report Hub；
3. 官方赛后技术报告；
4. Reuters / AP / BBC / ESPN 等可靠媒体；
5. FBref / StatsBomb Open Data / football-data.co.uk 等结构化足球数据源；
6. Transfermarkt / FotMob / SofaScore 等只作为人工整理或合规导出来源；
7. 社交媒体只作为线索，不直接入模。

### 3.2 版权与合规

禁止把完整文字直播、完整战术文章、付费报告原文复制进数据库。

正确做法：

```text
保存：source_url、来源、时间、短摘要、结构化标签、置信度
不保存：大段原文、付费全文、未经授权的完整解说过程
```

Agent 只需要读取结构化信号，不需要全文。

---

## 4. 每日执行流程

### Step 1：更新原始数据

人工或合规脚本填入：

```text
database/player_style/raw/raw_player_master.csv
database/player_style/raw/raw_player_league_stats.csv
database/player_style/raw/raw_worldcup_lineups_positions.csv
database/team_style/raw/raw_team_phase_metrics.csv
database/team_style/raw/raw_match_state_response.csv
database/team_style/processed/team_formation_matchups.csv
database/eventflow/raw/raw_match_commentary_signals.csv
database/eventflow/raw/manual_tactical_observations.csv
```

其中 `team_formation_matchups.csv` 可以先手工维护，因为阵型对弈需要人工判断。

### Step 2：运行事件流构建流水线

```bash
python scripts/update_eventflow_daily.py
```

它会依次运行：

```bash
python scripts/build_player_foot_position_profile.py
python scripts/build_worldcup_position_shift.py
python scripts/build_team_tactical_profile.py
python scripts/build_tactical_matchup_matrix.py
python scripts/build_match_timeline_events.py
python scripts/build_eventflow_scenario_weights.py
python scripts/validate_eventflow_data.py
```

### Step 3：运行概率派 V2.0

先运行原来的：

```bash
python scripts/predict_v2.py --home Brazil --away Haiti
```

如果原脚本不能直接导出 `probability_engine_scores.csv`，Agent 需要新增一个导出选项：

```bash
python scripts/predict_v2.py --home Brazil --away Haiti --export-score-csv database/eventflow/raw/probability_engine_scores.csv
```

CSV 字段必须是：

```csv
match_id,home,away,score,probability
```

### Step 4：运行事件流预测

```bash
python scripts/predict_eventflow.py \
  --match-id 66456932 \
  --home Brazil \
  --away Haiti \
  --lam-home 2.35 \
  --lam-away 0.45 \
  --mode balanced
```

模式：

```text
safe：概率派 65%，事件流 35%，适合稳健输出
balanced：概率派 50%，事件流 50%，默认
hit_hunting：概率派 35%，事件流 65%，适合赛果命中/大比分覆盖
```

### Step 5：融合双引擎

```bash
python scripts/merge_dual_engine_predictions.py \
  --match-id 66456932 \
  --home Brazil \
  --away Haiti \
  --mode balanced \
  --topn 5
```

输出：

```text
database/eventflow/processed/dual_engine_predictions.csv
```

---

## 5. Agent 预测时必须输出

每场比赛至少输出：

```json
{
  "match": "Brazil vs Haiti",
  "mode": "balanced",
  "probabilityEngine": {
    "topScores": [
      {"score": "2-0", "probability": 0.13},
      {"score": "1-0", "probability": 0.11},
      {"score": "2-1", "probability": 0.09}
    ]
  },
  "eventFlowEngine": {
    "dominantScenarios": [
      {
        "scenario": "强队早球后比赛被打开",
        "weight": 0.28,
        "scoreFamily": ["3-0", "3-1", "4-1"]
      }
    ],
    "tacticalMatchup": {
      "homeBreakthroughPath": "边路宽度 + 肋部内切 + 定位球后点",
      "awaySurvivalPath": "低位密度 + 限制中路推进",
      "countered": "Haiti 的低位若能压缩中路，会降低 Brazil 常规渗透效率；但边路一旦被打穿，大比分尾部上升"
    }
  },
  "finalRecommendation": {
    "scoreRank": ["3-0", "2-0", "3-1"],
    "totalGoals": "2/3/4球，防5+球",
    "halfFullTime": ["胜/胜", "平/胜"],
    "riskNote": "如果上半场没有早球且弱队低位稳定，3球以上概率下调"
  }
}
```

---

## 6. 严格禁止

- 禁止直接复制大段解说/战术文章全文；
- 禁止因为“名气大”就判定能破阵；
- 禁止只输出一个比分；
- 禁止把半全场写成半场胜平负；
- 禁止忽略球员惯用脚和实际站位；
- 禁止忽略世界杯第一轮实际位置与联赛常规位置的差异；
- 禁止让事件流完全覆盖概率派；
- 禁止在数据置信度低时给确定性语气。

---

## 7. skill.md 建议新增段落

```markdown
## V3.0 EventFlow 事件流赛果派分支

在 V2.0 `xG + 多层修正 + Dixon-Coles` 概率预测框架外，新增 EventFlow 事件流推演分支。该分支用于处理概率模型容易低估的比赛状态连锁变化，包括早球、红牌、点球、追分压上、阵型克制、边路错位、定位球破局、体能断电、强队久攻不下等。

EventFlow 必须读取：
- `database/player_style/processed/player_foot_position_profile.csv`
- `database/player_style/processed/player_worldcup_position_shift.csv`
- `database/team_style/processed/team_tactical_profile.csv`
- `database/team_style/processed/tactical_matchup_matrix.csv`
- `database/eventflow/processed/scenario_library.json`
- `database/eventflow/processed/eventflow_scenario_weights.csv`

EventFlow 输出必须包含：
1. 至少三种比分结果，按事件流权重从高到低排序；
2. 总进球数倾向；
3. 半全场胜负，枚举为胜/胜、胜/平、胜/负、平/胜、平/平、平/负、负/胜、负/平、负/负；
4. 战术对弈解释：谁克制谁、谁被牵制、哪条路径能破阵、哪条路径能守住；
5. 球员层解释：惯用脚、擅长位置、实际站位、世界杯第一轮是否发生位置偏移；
6. 数据置信度与风险提示。

最终推荐使用双引擎融合：
- safe：概率派 65%，事件流 35%；
- balanced：概率派 50%，事件流 50%；
- hit_hunting：概率派 35%，事件流 65%。
```

---

## 8. 回测指标

不要只看比分命中。必须记录：

```text
Top1 比分命中
Top3 比分命中
胜平负命中
总进球桶命中
半全场命中
大比分覆盖率
事件剧本命中率
相对 V2.0 的 Brier / LogLoss 变化
```

运行：

```bash
python scripts/backtest_eventflow.py
```

输出：

```text
database/eventflow/processed/eventflow_backtest.csv
```
