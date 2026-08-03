# Pattern Discovery Rules — Sprint 18.4F

Patterns are deterministic groups of approved semantic token families and frozen context signatures. `patterns-v1` uses stable SHA-256-derived short IDs; absent an approved display name it renders `Pattern <short ID>`. The registry includes structure, positioning/options, compression/release, manipulation/trap, institutional/validation, recommendation, and trigger families.

A recurring pattern must satisfy configured minimum occurrence count, evaluable count, average similarity, and coverage. Unsupported groups are omitted when singular; retained low-support groups carry `LOW_SAMPLE_PATTERN` and `PATTERN_SUPPORT_INSUFFICIENT`. Occurrence and evaluable counts are always distinct.

Recommendation/outcome modes use deterministic count then lexical tie-breaking. Changes, MFE, and MAE are factual averages over available values. Supporting Trade IDs are sorted. Ordering uses occurrence count, average similarity, then ID.

Patterns are observed co-occurrences, not causal, proven, or predictive claims. One or two records are not presented as meaningful recurrence. Learning, validation research, and adaptive strategy behavior remain deferred to Sprint 20 and 20.5.
