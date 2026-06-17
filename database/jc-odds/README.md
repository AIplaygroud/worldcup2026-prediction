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

## Agent 用法

1. 读取 `processed/match_odds_top8.json` 获取目标场次赔率
2. 读取 `matches[].pools` 获取各玩法开售状态与**是否可单关**（`single: true` = 可单关）
3. 结合 `skill.md` 预测概率，计算隐含概率与价值
3. 禁止编造赔率；若文件过期，先运行拉取脚本
