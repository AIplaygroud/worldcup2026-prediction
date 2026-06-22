# V3.8 Anti-Overfit Dynamic Fusion

## Objective

Reduce discretionary parameters and prevent EventFlow from dominating the
calibrated probability engine when prematch evidence is weak.

## Fixed Policy

`scripts/eventflow_dynamic_weight.py` computes a reliability score from:

- structured data coverage and estimated-row penalty;
- prematch A/B evidence and fused-evidence counts;
- evidence conflict ratio;
- scenario specificity and concentration;
- fallback and engine-degradation status.

The base EventFlow weight is:

```text
clip(0.06 + 0.30 * reliability, 0.06, 0.35)
```

Additional caps apply when A/B evidence is absent, fused evidence is absent,
conflict is high, fallback rows are material, or either engine is degraded.
Probability weight is the remainder. Legacy user modes are ignored.

## Ranking Controls

1. EventFlow candidates contain EventFlow evidence only. Probability is added
   once, in the final merge.
2. Overlapping scenarios use the strongest contribution plus 20% of the
   remainder.
3. EventFlow bonuses are regularized as scoreline total goals rise.
4. The previous unconditional score-family bonus for `3-1` and `4-1` is not
   used.
5. Active scenario count and tail strength depend on reliability.

## Betting Controls

Composite total-goals and correct-score selections retain every option's SP
and model probability. Reports show line count, payout-SP range, and
equal-stake expected gross return. A composite selection is never represented
by its minimum SP alone.

## Change Gate

Do not change coefficients after reviewing a small set of recent outcomes.
Run:

```bash
python scripts/backtest_dynamic_fusion.py
```

The included eight-match comparison is diagnostic only. Promotion of further
coefficient changes requires a larger chronological holdout, frozen prematch
artifacts, and evaluation of result class, exact-score rank, total-goals error,
goal-difference error, and probability calibration where true probabilities
are available.
