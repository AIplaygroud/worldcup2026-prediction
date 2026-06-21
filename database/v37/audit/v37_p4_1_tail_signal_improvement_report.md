# V3.7-P4.1 Tail Signal Improvement Report

**Version:** v37_p4_1_tail_diagnostics_clean (v3.7-p4.1-tail-diagnostics-clean)

## Sample
- Total: 51 (target 50)
- Large-score cases: 23
- Event timeline available: 19

## Missed large scores
- Missed count (rank > 5): 21
- Top miss reasons: [('acg_quality_insufficient', 11), ('guard_suppressed', 8), ('egci_quality_insufficient', 2)]
- Candidate pool coverage: 0.6522

## Gate attribution
- Top blocking gates: ['acg_threshold', 'egci_quality', 'egci_threshold', 'underdog_fragility', 'cold_guard']
- Potential overblocking: ['acg_quality', 'cold_guard', 'deep_handicap_contra']

## Gates
- safety_pass: **True**
- performance_pass: **False**
- rerank_only_allowed: **False**

## Recommendations
- improve_egci_v2_real_coverage
- review_guard_attribution_not_threshold_tuning

**Do not tune thresholds on F35 alone.** Rerank remains audit_only.
No λ mutation. No auto-betting.
