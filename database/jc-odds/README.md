# 竞彩足球赔率库 (jc-odds)

中国体彩竞彩足球世界杯 SP 值，供 `prediction-skill` 娱乐模拟盘价值分析使用。

## 目录

| 路径 | 说明 |
|---|---|
| `processed/match_odds_top8.json` | **主文件**：在售前 8 场完整赔率及 `pools` 单关/开售状态 |
| `processed/match_odds_summary.csv` | 胜平负 / 让球一览表；含各玩法是否可单关 |
| `processed/match_odds_ttg.csv` | 总进球 SP |
| `processed/match_odds_hafu.csv` | 半全场 SP |
| `processed/match_odds_crs.csv` | 比分 SP |
| `processed/odds_board.md` | 人类可读的赔率看板 |
| `raw/api_snapshot_*.json` | 原始 API 快照（按次拉取） |

## 更新

```bash
python prediction-skill/scripts/fetch_jc_odds.py --limit 8
```

- 数据来源：体彩官方 `webapi.sporttery.cn`
- SP 值会变动；做价值判断前请重新拉取
- 需关闭 VPN，否则可能被 WAF 拦截
- 若接口返回 567/WAF 且没有可用场次，脚本只保存 raw 错误快照，不覆盖现有 `processed/`
- 可用 `--from-raw raw/api_snapshot_*.json` 从成功快照重建 `processed/`

## 队名与匹配键

体彩接口中的中文可能是简称（如 `阿尔及利`、`乌兹别克`），不应作为跨数据库主键。`processed` 表中提供以下稳定字段：

| 字段 | 说明 |
|---|---|
| `matchKey` | 推荐主键，格式如 `ARG-ALG`、`UZB-COL` |
| `homeTeam` / `awayTeam` | 项目标准中文全称，用于展示 |
| `homeTeamEn` / `awayTeamEn` | 与球队数据库一致的英文名 |
| `homeTeamCode` / `awayTeamCode` | 项目标准球队代码，用于匹配 |
| `homeTeamOddsName` / `awayTeamOddsName` | 体彩原始中文简称，仅用于追溯 |
| `homeTeamApiCode` / `awayTeamApiCode` | 体彩 API 原始代码，可能与项目代码不同（如 `NOW`/`NOR`、`COM`/`COL`） |

## Agent 用法

1. 读取 `processed/match_odds_top8.json` 获取目标场次赔率
2. 优先用 `matchKey`、`homeTeamCode/awayTeamCode` 或 `homeTeamEn/awayTeamEn` 匹配模型输出，不依赖中文简称
3. 读取 `matches[].pools` 获取各玩法开售状态与**是否可单关**（`single: true` = 可单关）
4. 结合 `skill.md` 预测概率，计算隐含概率与价值
5. 禁止编造赔率；若文件过期，先运行拉取脚本
