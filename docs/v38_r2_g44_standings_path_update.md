# V3.8 R2-G44 积分榜与晋级路径更新说明

## 更新范围

本次更新基于 `postmatch_audit_R2_four_matches_20260623_revised.md` 中的四场第二轮赛果，将 G41–G44 回填进正赛结果表，并刷新积分榜、最好第三名、晋级路径和末轮比赛激励特征。

已回填赛果：

- G41：Norway 3-2 Senegal
- G42：France 3-0 Iraq
- G43：Argentina 2-0 Austria
- G44：Jordan 1-2 Algeria

## 数据文件变更

- `database/xGdatabase/processed/wc2026_match_xg.csv`：新增四条 score-only R2 赛果，`quality_flag=score_only_postmatch_audit`，xG/射门指标待后续回填。
- `database/competition/wc2026_group_fixtures.csv`：G41–G44 状态改为 `finished`，来源指向 R2 赛后审计文档。
- `database/competition/group_standings.csv`：重算小组积分榜。
- `database/competition/live_group_standings.csv`：生成 `WC2026_GROUP_20260623_POST_G44` 快照。
- `database/competition/third_place_rankings.csv`：刷新最好第三名实时排名。
- `database/competition/advancement_path_snapshot.csv`：刷新每队晋级路径结构概率。
- `database/competition/runtime/match_incentive_runtime_R3.csv`：刷新末轮每场比赛的晋级压力与路线激励特征。
- `database/competition/runtime/bracket_route_runtime_R3.csv`：刷新末轮路线难度与潜在控分/路线选择特征。
- `outputs/standings_update_20260623_post_g44.md`：新增中文积分局势与晋级路径分析报告。
- `outputs/phase06_group_state/group_situation_report.md`：同版稳定报告，供 agent/前端读取。

## 关键局势变化

- I 组：法国与挪威均 6 分，已锁定小组前二；末轮法国 vs 挪威直接争小组第一。
- I 组：塞内加尔和伊拉克均 0 分，前二路径关闭，只能通过末轮胜负和最好第三名路径争取出线，净胜球压力较大。
- J 组：阿根廷 6 分锁定前二；常规比分情景下基本锁定第一。
- J 组：奥地利 3 分、阿尔及利亚 3 分，末轮阿尔及利亚 vs 奥地利直接决定第二名归属；阿尔及利亚当前处于最好第三名安全区边缘。
- J 组：约旦 0 分，必须击败阿根廷并争取净胜球，晋级路径较窄。

## 概率口径

`p_advance`、`p_top2`、`p_best8_third` 为结构性情景概率，由小组剩余赛程枚举、当前积分/净胜球和 Annex C 第三名落位模型生成。它们不是赔率概率，不代表投注价值，也不应直接替代 V2 概率派胜平负模型。

## 复现命令

```bash
python scripts/build_group_standings.py
python scripts/build_live_group_standings.py --source-cutoff-time 2026-06-23T04:00:00Z --out-snapshot-id WC2026_GROUP_20260623_POST_G44
python scripts/build_advancement_path_snapshot.py --snapshot-id WC2026_GROUP_20260623_POST_G44 --source-cutoff-time 2026-06-23T04:00:00Z
python scripts/build_match_incentive_features.py --snapshot-id WC2026_GROUP_20260623_POST_G44 --source-cutoff-time 2026-06-23T04:00:00Z --round 3
python scripts/run_phase06B_bracket_route_analysis.py --source-cutoff-time 2026-06-23T04:00:00Z --snapshot-id WC2026_GROUP_20260623_POST_G44 --round 3 --skip-phase06 --skip-integrity-check
python scripts/generate_standings_situation_report.py --snapshot-id WC2026_GROUP_20260623_POST_G44 --out outputs/standings_update_20260623_post_g44.md
```
