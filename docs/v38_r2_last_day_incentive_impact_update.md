# V3.8 R2 最后一天战意影响补充更新

## 更新背景

在 G41–G44 四场 R2 赛果回填后，I/J 组局势发生变化：法国、挪威、阿根廷锁定前二，阿尔及利亚升至 3 分并进入实时最好第三名池。该变化不会直接改变 K/L 组球队实力，但会抬高跨组第三名参照线，从而影响第二轮最后一天 G45–G48 的战意解释、平局接受度和 EventFlow 场景触发。

## 新增文件

| 文件 | 说明 |
|---|---|
| `scripts/generate_r2_last_day_incentive_impact.py` | 读取 G44 后实时积分榜、最好第三名和 G45–G48 赛程，生成战意补充报告 |
| `database/competition/runtime/r2_last_day_incentive_impact_post_g44.csv` | 机器可读的 G45–G48 战意影响表 |
| `outputs/r2_last_day_incentive_impact_20260623_post_g44.md` | 中文补充分析报告 |

## 关键结论

- **有影响，但主要是间接影响**：G44 后多个 3 分第三名进入安全区/边缘区，导致 0 分、1 分球队对平局的接受度下降。
- **G46 巴拿马 vs 克罗地亚**：双方 0 分，平局接受度极低，应增强末段追分、换人冒险、开放比赛和反击尾部。
- **G47 葡萄牙 vs 乌兹别克斯坦**：葡萄牙 1 分，平局到 2 分不够安全；乌兹别克斯坦 0 分，输球后几乎被推入淘汰边缘。
- **G45 英格兰 vs 加纳**：双方 3 分，平局到 4 分较安全，但仍有 6 分锁定前二和争小组第一动机；不能直接解释成默契平。
- **G48 哥伦比亚 vs 刚果金**：受同日早场 G47 结果影响，必须在临场报告中标注动态依赖。

## 模型纪律

本次补充只进入战意、平局接受度、报告解释和 EventFlow 场景层：

- 不修改 `predict_v2.py` 基础 λ；
- 不重新拟合胜平负概率；
- 不改变投注正期望判断；
- 不把阶段性第三名快照写成最终晋级名单；
- 不将“平局接受度下降”直接写成“必分胜负”。

## 验证

已执行：

```bash
python scripts/generate_r2_last_day_incentive_impact.py
python -m py_compile scripts/generate_r2_last_day_incentive_impact.py
```
