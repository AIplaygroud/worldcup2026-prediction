# V3.8 R2 审计后代码更新摘要

更新时间：2026-06-23

## 输入文件

- README.md：由上传的 `README(3).md` 同步覆盖，并补充 R2 审计后的概率约束说明。
- skill.md：由上传的 `skill(1).md` 同步覆盖，并补充 R2 审计后的低置信度与概率纪律。
- postmatch_audit_R2_four_matches_20260623_revised.md：已归档至 `docs/`，作为本次代码修订依据。

## 主要代码改动

1. 修复 EventFlow 客队优势方比分族镜像：当优势方为客队时，强队比分族会从 `2-0/3-0/2-1` 等镜像为 `0-2/0-3/1-2` 等，避免 J44 类主客语义错误。
2. 取消 85% 固定胜率上限：概率只做 epsilon 开区间保护，避免出现 0 或 100%，不再机械压缩超过 85% 的校准概率。
3. 增加半场 / 半全场独立低置信度门控：默认标记为低置信度参考，不进入稳胆、主仓、保底或串关唯一胆项。
4. 强化 EventFlow 与 V3.7 降级 fail-closed：加载失败、质量降级或 EventFlow 权重归零时，不再把对应特征写成有效参与；融合侧明确转为概率派主导。
5. 拆分数据质量口径：新增 authenticity、coverage、freshness、consistency 与 conflict_count，避免“真实来源”等同于“数据完整”。
6. 增加每场运行目录、预检与 manifest：`run_dual_engine_pipeline.py` 默认输出到 `outputs/runs/<match_id>/<timestamp>/`，并记录输入输出文件哈希。

## 新增测试

- `tests/test_v38_postmatch_audit_rules.py`

覆盖：客队优势比分镜像、EventFlow away-favorite bonus、无 85% cap、降级归零、半场投注禁入、数据质量拆分。

## 验证结果

- `python -m unittest tests.test_v38_postmatch_audit_rules -v`：6/6 通过。
- `python -m unittest tests.test_eventflow_dynamic_weight tests.test_v33_score_semantics tests.test_v37_integration tests.test_v35_betting_strategy_output_semantics -v`：14/14 通过。
- `python -m compileall -q scripts tests`：通过。
- `python -m unittest discover -s tests -v`：181 通过，6 跳过，2 失败。失败集中在历史投注复式展开快照测试：当前解压数据中对应候选组合为空 / G40 总进球复式行缺失，未为了通过测试而改动历史快照数据。
