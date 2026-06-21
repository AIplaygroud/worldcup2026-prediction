# V3.7-P4 Tail Calibration Report

- **Version**: v37_p4_tail_calibration (v3.7-p4.1-tail-signal-improvement)
- **Generated**: 2026-06-21T09:58:57.724753+00:00

## Sample
- Sample size: **51**
- Large-score cases: **25**
- Minimum for performance pass: 20

## Performance
- Baseline large-score Top5 recall: 0.08
- Rerank large-score Top5 recall: 0.08
- Recall delta: 0.0
- Tail false positive delta: 0.0
- Avg rank improvement: -0.098

## Guard safety
- cold_guard false boost: 0
- must_win_no_convert false boost: 0
- deep_handicap false boost: 0
- 5-0/5-1 Top3 violations: 0

## Gates
- safety_pass: **True**
- performance_pass: **False**
- rerank_only_allowed: **False**
- rerank_default_allowed: **False**

## Decision
- Reason: performance_thresholds_not_met
- Allowed modes: audit_only

This stage does **not** mutate λ, V2 probabilities, adjusted probabilities, or betting outputs.
Rerank remains **audit_only** by default unless `rerank_only_allowed=true`.
