# Historical Similarity Rules — Sprint 18.4F

## Contract and versions
`SimilarityRequest` accepts exactly one frozen fingerprint or stable Historical Trade ID. It validates dates, limits, a 0–1 threshold, and non-negative weights with a non-zero total. Results expose `similarity-v1`, `context-v1`, `weights-v1`, and `patterns-v1`; exact fingerprint-version comparison is the conservative default.

## Candidate selection
`CandidateSelector` issues a parameterized `HistoricalIndexQuery` against SQLite before scoring. Instrument, dates, recommendation, engine, and fingerprint version can constrain candidates. The source and optionally its trading date are excluded. Ordering and caps are deterministic. It never scans Market Lake and never calls DecisionPipeline. Missing, stale, invalid, or incompatible indexes fail safely through diagnostics/quality flags.

## Scoring
Semantic similarity compares registered token families, with configured family weights. Unknown/missing values reduce coverage and never match. Numeric similarity uses only registry features, clamps `1 - absolute distance` to 0–1, excludes missing values, and reports weighted feature coverage. Context similarity combines frozen context tokens and normalized time/calendar values.

Aggregation normalizes requested weights. If a component is unavailable, its weight is redistributed proportionally across available components, effective weights are exposed, and total coverage remains reduced. Bands are configurable and describe **Similarity Strength**, never prediction confidence.

## Explanation and outcomes
The difference analyzer emits only traceable semantic, numeric, and context comparisons with stable analysis targets. Similarity is frozen before outcome classification and movements are attached. Outcome frequencies are factual historical frequencies with sample/evaluable counts and coverage; NOT_EVALUABLE rows are excluded from the denominator.

## Ranking and diversity
Ranking uses overall score, coverage, semantic score, context score, newest timestamp, then Trade ID. Optional per-date caps, time separation, and semantic-key deduplication are transparent through `SAME_DAY_DUPLICATES_REDUCED`. Explicit opposite-registry matches are returned separately.

## Advisory, performance, and security
Similarity never changes BUY CE, BUY PE, WAIT, confidence, validation, ranking, or safety policy. Queries are bounded and parameterized; scoring is sequential and deterministic. No broker calls, external similarity services, vector database, ML, secrets, runtime clients, or arbitrary SQL are used. Cache keys, if enabled later, must include source identity and all algorithm versions.

## Quality flags
Supported diagnostics include source/context unavailable, index unavailable/stale/version mismatch, insufficient candidates/matches, component incompleteness, low coverage/sample/outcome coverage, low pattern support, option incompleteness, cross-version blocking, source exclusion, and same-day duplicate reduction.
