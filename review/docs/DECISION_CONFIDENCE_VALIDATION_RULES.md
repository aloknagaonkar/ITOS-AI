# Decision Confidence Validation Rules

## Purpose and status
Decision Confidence is the existing point-in-time setup-quality score. **Validation confidence** instead describes how reliable the validation conclusion is given history completeness and quality; it is not a market score. Validation is informational and shadow-only. It never changes BUY CE, BUY PE, WAIT, recommendation confidence, safety gates, planning, strikes, or execution.

## History contract and normalization
The engine accepts an injected ordered sequence, mapping, dataclass-like values, or DataFrame records. A point carries timestamp, score, grade, setup quality, ranking readiness, seven pillar scores, penalties, critical blockers, contradiction count, and evidence quality. The current typed result is appended once. Valid timestamps are sorted; missing timestamps preserve input order. Duplicate timestamp points are ignored. Missing/invalid/NaN scores discard a point rather than becoming zero. Malformed optional collections become empty and receive quality flags. No future point is requested or synthesized.

## Formulas and defaults
- **Trend:** up to six recent points. Interval changes use a ±1 neutral band. Improving/weakening requires majority movement and endpoint slope of at least ±1.5 points per period. A 12-point change combined with alternating signs is volatile; otherwise the neutral result is stable. Three valid points are required.
- **Stability:** `100 - (2.2×population standard deviation + 1.2×maximum interval change + 5×grade transitions + 8×readiness transitions + normalized penalty/blocker transition costs)`, clamped to 0–100. States are very stable ≥90, stable ≥75, moderate ≥55, unstable ≥30, otherwise highly unstable.
- **Pillar agreement:** combines pillar-score dispersion, proportion at/above 60, seven-pillar completeness, weakest-pillar deficit, and a 15-point outlier penalty when the range is at least 30. It is clamped to 0–100 and measures quality coherence, not direction.
- **Readiness persistence:** recency-weighted true readiness weight divided by total weight ×100. Default incremental recent weighting is 1.0. Persistent readiness requires 80.
- **Eligibility:** current `ranking_ready`, score ≥70, stability ≥75, agreement ≥70, persistence ≥80, at least three valid points, evidence quality ≥55, at most two contradictions, and no current/new critical blocker. A current setup that passes but lacks history is `INSUFFICIENT_HISTORY`; one missing persistence/stability requirement is `CONDITIONALLY_ELIGIBLE`; critical failure is `NOT_ELIGIBLE`.
- **Change drivers:** current versus most recent valid prior point. Pillar changes under four points are ignored. Readiness and contradiction transitions are explicit.
- **Penalties/blockers:** canonical keys use text before `:`, uppercase, and normalized non-alphanumeric separators. Wording-only changes with the same key are deduplicated.
- **Shadow comparison:** BUY CE/BULLISH and BUY PE/BEARISH are aligned; opposite evidence is conflicted; neutral/mixed evidence is directionally aligned; WAIT remains a non-error shadow observation.
- **Validation confidence:** starts at 25 plus ten per valid point (maximum six), then applies ceilings of 55 for short history, 65 for missing timestamps, and 70 for absent pillar history; malformed/stale history subtracts ten. Final value is clamped.

## Quality and missing-data rules
Flags include `DECISION_CONFIDENCE_UNAVAILABLE`, `HISTORY_UNAVAILABLE`, `HISTORY_INSUFFICIENT`, `HISTORY_PARTIALLY_INVALID`, `TIMESTAMPS_UNAVAILABLE`, `DUPLICATE_HISTORY_POINTS`, `HISTORY_STALE`, `PILLAR_HISTORY_UNAVAILABLE`, `PENALTY_HISTORY_UNAVAILABLE`, `BLOCKER_HISTORY_UNAVAILABLE`, `RECOMMENDATION_UNAVAILABLE`, `INSTITUTIONAL_EVIDENCE_UNAVAILABLE`, `RANKING_NOT_ELIGIBLE`, and `VALIDATION_CONFIDENCE_LOW`. Missing confidence produces unavailable states, zero conservative validation metrics, and false eligibility. Short history never infers a trend or full eligibility.
