# WC2026 R2 赛前回测（MD2 前四场）

> 生成日期：2026-06-19。数据截断：**开赛日前一天**（含该日已完赛正赛 xG）。
> 脚本：`python scripts/backtest_r2_prematch.py --write-report`

## 1. 样本

| Fixture | 场次 | 开赛日 | 数据截止 | 截止前正赛场次 |
|---|---|---|---|---|
| 25 | Czechia vs South Africa | 2026-06-18 | 2026-06-17 | 20 |
| 26 | Switzerland vs Bosnia and Herzegovina | 2026-06-18 | 2026-06-17 | 20 |
| 27 | Canada vs Qatar | 2026-06-18 | 2026-06-17 | 20 |
| 28 | Mexico vs South Korea | 2026-06-18 | 2026-06-17 | 20 |

## 2. 汇总

- 胜平负方向命中：**2/4**（50.0%）
- 赛果 ∈ Top-5 比分带：**2/4**（50.0%）
- 实际 BTTS 是：**2/4**

## 3. 逐场

| 场次 | base λ | 最终 λ | modal | 赛果 | P(主/平/客) | BTTS% | 方向 | Top5 | 裁判层 |
|---|---|---|---|---|---|---|---|---|---|
| Czechia vs South Africa | 0.88/1.22 | 0.96/1.27 | 1-1 | 1-1 | 27/30/43 | 45% | ✗ | ✓ | 未确认/晚于截止 |
| Switzerland vs Bosnia and Herzegovina | 2.74/1.08 | 2.92/1.08 | 2-1 | 4-1 | 75/15/11 | 63% | ✓ | · | 未确认/晚于截止 |
| Canada vs Qatar | 1.70/1.10 | 2.18/1.08 | 2-1 | 6-0 | 62/21/17 | 59% | ✓ | · | 未确认/晚于截止 |
| Mexico vs South Korea | 1.12/1.51 | 1.28/1.44 | 1-1 | 1-0 | 33/27/40 | 56% | ✗ | ✓ | 未确认/晚于截止 |

## 4. 说明

- **时间隔离**：`wc2026_match_xg.csv` 仅保留 `match_date <= cutoff`；2026-06-18 的 R2 四场 cutoff 均为 **2026-06-17**（当时 R1 已赛 20 场，K/L 组末两场 R1 尚未踢完）。
- **裁判层**：`match_officials.csv` 的 `fetched_at` 若晚于 cutoff，赛前回测**不启用**主裁方向修正（符合「仅前一天及以前数据」）。
- **东道主**：加拿大、墨西哥场次启用 `host_side=home`；其余为中立场。
- 赛果来源：ESPN MD8 报道（2026-06-18）；正赛 xG 待 FotMob 入库后补全 `actual_xg` 列。
