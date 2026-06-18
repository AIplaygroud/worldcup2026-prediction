# WC2026 队名 / 数据一致性审计

> 生成日期：2026-06-18。交叉核对四张表 48 队英文队名；**未修改任何源 CSV**。

## 1. 各表球队计数

| 文件 | 球队数 |
|---|---|
| `wc2026_team_xg.csv` | 48 |
| `team_recent_form.csv` | 48 |
| `team_model.csv` | 48 |
| `wc2026_match_xg.csv` | 48 |

## 2. 跨表差异

**未发现拼写不一致或缺失**：四表均为 **48 队**，队名集合完全一致。

## 3. 命名规范（四表统一）

| 规范写法 | 说明 |
|---|---|
| `Bosnia and Herzegovina` | 非 Bosnia-Herzegovina |
| `Czechia` | 非 Czech Republic |
| `DR Congo` | 非 Congo DR |
| `Ivory Coast` | 非 Côte d'Ivoire |
| `South Korea` | 非 Korea Republic |
| `USA` | 非 United States |

## 4. 结论

- 拼写不一致：**无**
- 缺失球队：**无**
- 建议：以 `team_model.csv` 的 `team` 列为 join key。
