# `skill.md` 增量补丁：V3.0 EventFlow 双引擎

把以下内容加入现有 `skill.md` 的预测方法论部分。

```markdown
## V3.0 双引擎预测原则

本 Skill 在 V2.0 `xG + 多层修正 + Dixon-Coles` 概率引擎基础上，新增 EventFlow 事件流引擎。

- 概率引擎负责稳态概率、校准、赔率/竞彩规则、基础比分分布；
- EventFlow 引擎负责战术对弈、球员惯用脚/位置偏移、比赛阶段连锁反应、大比分尾部分布；
- 最终必须同时给出 Probability Engine、EventFlow Engine、Dual Merge 三类结果。

### EventFlow 必查数据

每场赛前必须读取：

1. `database/player_style/processed/player_foot_position_profile.csv`
2. `database/player_style/processed/player_league_style_profile.csv`
3. `database/player_style/processed/player_worldcup_position_shift.csv`
4. `database/team_style/processed/team_tactical_profile.csv`
5. `database/team_style/processed/team_match_state_response.csv`
6. `database/team_style/processed/tactical_matchup_matrix.csv`
7. `database/eventflow/processed/scenario_library.json`
8. `database/eventflow/processed/eventflow_scenario_weights.csv`
9. 如存在裁判模块，读取 `database/referee/processed/*` 作为 L10 辅助信号。

### EventFlow 必须判断

- 关键球员惯用脚与实际站位是否匹配；
- 世界杯第一轮实际位置是否偏离联赛常规位置；
- 双方阵型是否存在克制或牵制；
- 主队/客队是否有明确破阵路径；
- 主队/客队是否有能力守住对方攻势；
- 比赛是否可能进入早球、严哨、红牌、末段追分、崩盘、大比分尾部。

### 输出要求

每场必须输出：

- 至少三种比分，按 fusion_ranking_score 从高到低排序（排序分，非概率）；
- 总进球数倾向；
- 半全场胜负，使用：胜/胜、胜/平、胜/负、平/胜、平/平、平/负、负/胜、负/平、负/负；
- 事件流主剧本；
- 战术破阵/守阵解释；
- 球员惯用脚、位置、实际站位解释；
- 数据置信度和风险提示。

### 融合模式

- safe：概率派 65%，事件流 35%；
- balanced：概率派 50%，事件流 50%；
- hit_hunting：概率派 35%，事件流 65%。

默认使用 `balanced`。只有在用户明确要求提高赛果命中/覆盖大比分时，使用 `hit_hunting`。
```
