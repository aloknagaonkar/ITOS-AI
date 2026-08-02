# Trade Opportunity Ranking Rules

## Eligibility gate
Ranking requires `DecisionConfidence.ranking_ready`, `DecisionConfidenceValidation.ranking_eligible`, a non-empty chain, positive spot, and at least one contract passing conservative baseline filters. Failure produces `NOT_ELIGIBLE`, empty top lists, no best contracts, and an explicit reason.

## Normalization and baseline filters
The normalizer accepts pandas/list input, row-per-contract aliases, and combined call/put strike rows. It recognizes strike, side, expiry, symbol, LTP, quotes, OI/change, volume, IV and Greeks. Malformed rows become retained rejections. Duplicate contract identities keep the best deterministic instance. Invalid strike/expiry/LTP, subminimum OI/volume, critical spread, excessive distance/DTE, deep OTM, and severe side-specific manipulation are rejection conditions. Missing optional analytics degrade rather than fabricate data.

## Component models
- **Liquidity (15%)**: 55% activity, 30% spread, 15% two-sided quote availability.
- **Spread quality (10%)**: `ask-bid`; percent uses midpoint, then LTP fallback. Quality declines linearly to the critical threshold.
- **OI/volume (12%)**: 60% OI and 40% volume, scaled against conservative activity reference bands. OI change is retained but not interpreted as buying by itself.
- **Greeks (13%)**: absolute delta rewards the configured directional band; extreme delta, theta and near-expiry gamma are penalized. Vega is retained and not automatically rewarded.
- **IV (10%)**: reasonable IV receives suitability credit; elevated/extreme IV is penalized. Low IV is never labelled cheap. Compression context is upstream evidence and is not counted again here.
- **Moneyness/distance (10%)**: ATM, ITM, OTM, deep ITM and deep OTM use percentage distance so generic logic does not hardcode a NIFTY interval. Deep OTM can reject; deep ITM receives a premium/capital penalty.
- **Expiry (8%)**: low DTE receives theta/gamma-risk penalties; preferred calendar DTE is strongest; excessive or invalid DTE rejects.
- **Direction (12%)**: institutional bias establishes the base side score; dominant positioning adds one capped corroboration adjustment. This deduplication prevents every upstream observation from being counted again.
- **Manipulation safety (5%)**: bull-trap risk applies to CE and bear-trap risk to PE. Severe affected-side risk rejects only that side.
- **Decision confidence (5%)**: confidence is a small global reliability component, not copied into every component. Unstable validation caps A grades.

## Final formula and grades
`score = Σ(component × configured weight) / Σ(weights)`, clamped to 0–100. It is a suitability score, not a probability of profit. Defaults: A_PLUS ≥90, A ≥80, B ≥70, C ≥60, D ≥50; a critical rejection always yields REJECTED.

## Ordering, best overall, and explanations
Each side returns at most five candidates ordered by score descending, liquidity descending, spread quality descending, absolute ATM distance ascending, strike ascending, then expiry/symbol. Best overall must be eligible, meet the configured minimum, lack severe/extreme warning, and follow the preferred side; CONFLICTED/UNAVAILABLE direction returns none. Deterministic templates state strongest factors, the leading warning, rejection causes, and list rank/tie-break context.

## Missing-data and informational-only handling
Missing chain/spot blocks ranking. Missing quotes, OI, volume, IV, or Greeks adds flags, warnings, and conservative scores; nothing is replaced with zero unless zero was actually reported and valid. The result never executes orders and never changes recommendation, confidence, SafetyGatePolicy, legacy ranking, AI Trade Opportunity, or Trade Planner.
