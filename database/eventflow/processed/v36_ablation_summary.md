# V3.6 Ablation Summary

## Aggregate metrics

| version | n | 1X2 acc | top1 | top3 | BTTS LL | BTTS Brier | O2.5 LL | bucket LL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v35_baseline | 4 | 0.75 | 0.00 | 0.25 | 0.8047 | 0.3051 | 0.7831 | 1.6489 |
| full_v36 | 4 | 0.75 | 0.00 | 0.50 | 0.7995 | 0.3026 | 0.7788 | 1.6450 |

## Match details

- **WC2026-D32** `v35_baseline` actual=2-0 top1=1-1 hit1=0 hit3=0 BTTS pred=0.523 actual=0
- **WC2026-D32** `full_v36` actual=2-0 top1=1-1 hit1=0 hit3=1 BTTS pred=0.513 actual=0
- **WC2026-C29** `v35_baseline` actual=3-0 top1=2-0 hit1=0 hit3=1 BTTS pred=0.511 actual=0
- **WC2026-C29** `full_v36` actual=3-0 top1=2-0 hit1=0 hit3=1 BTTS pred=0.511 actual=0
- **WC2026-C30** `v35_baseline` actual=0-1 top1=0-2 hit1=0 hit3=0 BTTS pred=0.558 actual=0
- **WC2026-C30** `full_v36` actual=0-1 top1=0-2 hit1=0 hit3=0 BTTS pred=0.558 actual=0
- **WC2026-D31** `v35_baseline` actual=0-1 top1=1-1 hit1=0 hit3=0 BTTS pred=0.612 actual=0
- **WC2026-D31** `full_v36` actual=0-1 top1=1-1 hit1=0 hit3=0 BTTS pred=0.612 actual=0
