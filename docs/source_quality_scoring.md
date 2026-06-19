# Source Quality Scoring

Each source claim receives a confidence score from 0 to 1.

## Score components

```text
confidence =
  0.35 * source_authority
+ 0.25 * cross_source_agreement
+ 0.15 * timestamp_precision
+ 0.15 * tactical_specificity
+ 0.10 * data_consistency
```

## Component definitions

- `source_authority`: official FIFA / open event data > major professional media > fan blogs.
- `cross_source_agreement`: number of independent sources supporting the same event/tactical claim.
- `timestamp_precision`: exact minute/event time is better than vague narrative.
- `tactical_specificity`: claims that mention formation, pressing, wide overload, build-up, defensive block, transition route score higher.
- `data_consistency`: agrees with scoreline, cards, substitutions, shot/possession/event data.

## Confidence interpretation

- >= 0.80: strong signal, can directly affect EventFlow scenario weight.
- 0.60-0.79: usable signal, moderate scenario adjustment.
- 0.40-0.59: weak signal, use only as explanation.
- < 0.40: do not use for prediction.

