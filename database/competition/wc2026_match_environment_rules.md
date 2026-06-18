# 2026 FIFA World Cup Match Environment and Law Changes

> **Scope**: 本文件只收录会影响**比赛预测、比分分布、投注模拟**的场上规则与赛程环境变量。晋级规则、32 强 Annex C 落位与控分挑对手见 `wc2026_advancement_rules.md`; 竞彩/模拟盘 90 分钟彩果与玩法结算见 `reference/jingcai-football-simulation-rules.md`。

---

## Prediction-Relevant Variables

| Variable | Rule / condition | Prediction impact | Model handling |
|---|---|---|---|
| **强制补水休息** | 每半场约第 22 分钟(第二半场约第 67 分钟)附近于自然死球暂停, 持续 3 分钟; 每场固定执行, 不再仅由高温触发; 补时仍会回补 | 比赛节奏更像四段; 教练有固定战术窗口; 压低「仅因极端高温」导致的非对称体能风险, 但增强后段战术调整空间 | 在事件流/半全场叙事中考虑, **不**直接机械加减 xG; 高温仍保留在 L7 环境层, 但避免与补水休息重复惩罚 |
| **界外球/球门球 5 秒倒计时** | 裁判认为拖延时启动视觉 5 秒倒计时; 界外球超时判给对方界外球, 球门球超时判给对方角球 | 领先方消耗时间更难; 末段深防/弱队拖延时, 死球送角球风险上升 | 领先守胜、深防弱队、门将/后卫拖延倾向场景下, 略微提高对手末段定位球/角球压力; 勿把领先方控时能力估得过稳 |
| **换人 10 秒离场** | 换人牌出示后 10 秒内须离场; 超时则替补至少须等重开后 1 分钟(跑表)后的下一死球才能进场, 球队短暂少打一人 | 战术性慢换成本升高; 末段少打一人可能制造 xG 尾部风险 | 不作为常规 xG 输入; 仅在明确慢换/纪律差/裁判严执法场景作风险备注 |
| **场内治疗后离场 1 分钟** | 外场球员接受治疗后, 于开球后须离场 1 分钟; 门将、头部/严重伤、因对手犯规吃牌、点球主罚等例外 | 身体对抗强队、频繁倒地球队可能出现短时人数劣势; 同时抑制拖延治疗 | 只作情境风险, 不凭空假设发生 |
| **门将伤停战术暂停限制** | 门将接受治疗时, 其他球员不得去技术区开小会; FIFA 赛事指令, 尚无黄牌等正式处罚 | 减少非正式暂停; 但因固定补水存在, 强队仍有两次计划性战术窗口 | 勿把「门将假伤暂停」当作稳定战术优势; 补水窗口优先 |
| **VAR 扩容** | 角球明显误判(须即时、不拖重启); 第二黄明显错误; 认错人; 开球前进攻方犯规导致进球/点球/纪律可回看 | 定位球前抢位犯规进球更易被取消; 角球误判可能减少 | 对依赖角球/任意球冲撞的球队, 定位球进球尾部略保守; 勿大幅下调定位球强队 |
| **升级半自动越位与出界/触球技术** | >10cm 清晰越位可更快提示边裁, 延迟举旗减少; 极近越位与主观干扰(未触球但影响对手)仍靠人工 | 单刀延迟进攻的虚假 xG/伤病风险下降; 反越位球队的明显越位机会更难形成连续进攻 | 更多影响事件流与观赛体感, 不单独调 lambda; 对极依赖身后冲刺的球队可在叙事中提示 |
| **跨国赛程/旅行/气候** | 48 队、104 场、美加墨 16 城; 长距离旅行、热湿/海拔/时区差异; 规程要求场次间至少 3 天休息(半决赛至三四名赛除外) | 轮换、体能、压迫持续性、下半场崩盘风险; 三东道主有主场/旅行优势 | 与 `skill.md` L6 旅行疲劳、L7 环境层相连; **只用双方差值**, 不用绝对路程机械扣分; 美/加/墨主场与旅行优势单独说明 |
| **26 人名单、5 换人、加时额外换人、脑震荡换人** | 与 2022 相近, 但在 2026 超长赛程中更重要; 脑震荡换人不占用常规 5 换名额 | 阵容深度与板凳冲击更重要; 小组第三轮与淘汰赛后段轮换价值上升 | 连接 `team_model.csv` 的 `squad_depth_ratio`、`bench_impact`; 小组第三轮和淘汰赛后段权重更高 |

---

## Do Not Overfit

以下边界用于防止子代理机械套用:

1. **不是每场固定提高进球**: 补水休息、反拖延规则改变的是节奏与尾部风险, 不等于总进球 lambda 上调。
2. **补水休息不等于篮球暂停**: 球员仍在场内, 教练沟通窗口有限; 勿假设每次补水都带来大幅战术翻盘。
3. **5 秒倒计时由裁判判断启动**: 只有裁判认定拖延时才倒数; 正常节奏比赛影响可能很小。
4. **VAR 扩容不等于所有定位球进球都变少**: 仅覆盖明显误判与开球前犯规; 快速开出角球则无法改判。
5. **技术变化不替代越位主观判断**: >10cm 清晰越位才加速; 体毛级与干扰型越位仍靠边裁/VAR 人工。
6. **旅行/气候勿双重惩罚**: L6 差值化旅途 + L7 环境已分层; 补水休息已覆盖固定体能窗口, 高温层勿再叠加强惩罚。
7. **门将战术暂停限制无正式处罚**: 属于 FIFA 赛事指令, 执行力度因裁判而异; 勿当作可量化的稳定系数。
8. **换人/治疗少打一人**: 为尾部情境风险, 非默认每场发生。

---

## Prediction Checklist

子代理在输出单场预测前, 除 `wc2026_advancement_rules.md` 与实时伤停外, 建议核对:

1. **比赛城市**: 温湿度、海拔、是否顶棚/空调; 对照 L7 环境层, 并与补水休息去重。
2. **旅行差值**: 双方距上场比赛基地/上一场的飞行距离与时区变化; 用 L6 差值, 非绝对扣分。
3. **赛程密度**: 距上场是否满 3 天; 小组第三轮或连续淘汰赛是否暗示轮换。
4. **连续首发/轮换信号**: 深板凳球队在第三轮与后段淘汰赛是否更可能上强度。
5. **阵容深度**: 查 `team_model.csv` 的 `squad_depth_ratio`、`bench_impact`; 长赛程末段加权。
6. **定位球依赖**: 教练/球队是否角球、任意球、禁区内争抢型; 结合 VAR 扩容略保守定位球进球尾部。
7. **领先守胜情境**: 深防、拖延倾向、门将控时风格; 结合 5 秒倒计时与末段角球风险。
8. **身后冲刺/反越位打法**: 明显越位机会可能更早被吹停; 事件流叙事中提示, 勿单独大幅调 lambda。

---

## Sources

### 官方 / 立法机构

- FIFA 补水休息官方说明: https://inside.fifa.com/organisation/news/hydration-breaks-world-cup-2026-player-welfare
- FIFA 2026 赛事规程 (Regulations): https://digitalhub.fifa.com/m/636f5c9c6f29771f/original/FWC2026_regulations_EN.pdf
- FIFA 赛制与分组说明: https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/groups-how-teams-qualify-tie-breakers
- IFAB 2026/27 规则变更总览: https://www.theifab.com/law-changes/latest/
- IFAB 比赛流畅与球员行为措施: https://theifab.com/news/the-ifab-introduces-further-measures-to-improve-match-flow-and-player-behaviour/
- IFAB Circular 32 (AGM 决议摘要): https://downloads.theifab.com/downloads/circular-32?l=en
- FIFA 升级半自动越位与技术创新: https://inside.fifa.com/news/offside-decisions-referee-body-cams-innovation-world-cup-2026

### 权威媒体解读

- BBC — 补水与门将战术暂停: https://www.bbc.com/sport/football/articles/c9v39x2v8yxo
- BBC — 半自动越位技术: https://www.bbc.com/sport/football/articles/c232d34kkyzo
- Sky Sports — IFAB 世界杯规则变更: https://www.skysports.com/football/news/12040/13549645/world-cup-ifab-confirm-new-var-powers-10-second-substitutions-and-tactical-timeout-ban-in-major-rule-changes
- Sky Sports — 5 秒界外球/球门球: https://www.skysports.com/football/news/12040/13512688/ifab-agm-the-end-for-long-throws-new-five-second-time-limit-proposal-on-agenda-as-footballs-lawmakers-set-to-meet
- ESPN — 界外球/球门球倒计时: https://www.espn.com/soccer/story/_/id/48014733/fifa-world-cup-countdown-throw-ins-goal-kicks-feature
- ESPN — 补水休息与赛程: https://www.espn.com/soccer/story/_/id/49080670/are-world-cup-hydration-breaks-actually-commercial-breaks-momentum-breaks
- Fox Sports (OutKick) — 强制补水: https://www.foxnews.com/outkick-sports/fifa-implements-mandatory-water-breaks-2026-world-cup
- Sportstar — 规则变更一览: https://sportstar.thehindu.com/football/fifa-world-cup/fifa-world-cup-2026-rules-law-changes-explained-var-offside-technology-substitutions/article71090636.ece
- Sportstar — IFAB 法则详解: https://sportstar.thehindu.com/football/fifa-world-cup-2026-new-law-changes-explained-ifab/article71047027.ece
