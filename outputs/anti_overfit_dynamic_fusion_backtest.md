# Dynamic Fusion Backtest

Eight completed matches using stored prematch artifacts. Coefficients were not retuned from these results.

| Metric | Legacy fixed 50/50 | Auto dynamic |
|---|---:|---:|
| Top-1 result class | 5/8 (62.5%) | 5/8 (62.5%) |
| Top-3 exact score | 3/8 (37.5%) | 3/8 (37.5%) |
| Top-5 exact score | 3/8 (37.5%) | 3/8 (37.5%) |
| Top-1 total-goals MAE | 1.375 | 1.500 |
| Top-1 goal-difference MAE | 1.125 | 1.000 |
| Mean reciprocal rank | 0.167 | 0.229 |

## Match Detail

| Match | Actual | Legacy top-1 / rank | Dynamic top-1 / rank | EventFlow weight |
|---|---:|---:|---:|---:|
| WC2026-C29 Brazil vs Haiti | 3-0 | 2-0 / 2 | 2-0 / 2 | 28.4% |
| WC2026-C30 Scotland vs Morocco | 0-1 | 0-2 / - | 1-2 / 3 | 27.2% |
| WC2026-D31 Turkey vs Paraguay | 0-1 | 2-1 / - | 2-1 / - | 28.0% |
| WC2026-D32 USA vs Australia | 2-0 | 2-1 / 2 | 2-0 / 1 | 26.1% |
| WC2026-G39 Belgium vs Iran | 0-0 | 2-1 / - | 1-1 / - | 25.3% |
| WC2026-G40 New Zealand vs Egypt | 1-3 | 1-2 / 3 | 1-1 / - | 18.6% |
| WC2026-H37 Uruguay vs Cape Verde | 2-2 | 2-1 / - | 2-0 / - | 25.2% |
| WC2026-H38 Spain vs Saudi Arabia | 4-0 | 3-0 / - | 3-0 / - | 23.3% |

## Interpretation

- This comparison tests ranking behavior, not calibrated payout probability.
- Structural anti-overfit gains are reduced user freedom, bounded EventFlow influence, evidence-quality caps, and no duplicate probability injection.
- Performance promotion requires a larger chronological holdout. This eight-match report is diagnostic only.
