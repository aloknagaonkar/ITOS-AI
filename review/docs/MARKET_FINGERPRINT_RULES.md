# Market Fingerprint Rules — Sprint 18.4E

## Semantic registry
Tokens always follow: `MS, REGIME, CYCLE, LOC, PV, POS, OPTPOS, COMP, RELEASE, MANIP, TRAP, INST, CONF, VALID, RANK, REC, TRIG, DATA`. Values are uppercase, whitespace becomes underscores, bounded to 64 safe characters, and missing values follow configured `INCLUDE_UNKNOWN`. The semantic key joins this fixed ordering with `|`.

## Numeric feature registry
The immutable registry documents stable name, source, divisor normalization, `[0,1]` clamp, `None` missing behavior, and introduced fingerprint version. It includes decision/recommendation confidence; compression, energy, readiness, volume, institutional, manipulation, positioning, validation and ranking measures; PCR, IV, OI, support/resistance distance, ATR, relative volume, location, trigger pass ratio, blocker count and missing-confirmation count. Invalid/non-finite values remain `None` and add flags; missing is never zero.

## Time and outcome boundary
Only persisted fields available at the frozen analysis timestamp enter semantic/numeric fingerprints. Outcome classifications, horizon results, MFE/MAE, and future success/failure reasons are excluded. Those values may be indexed as separate filter metadata and never affect semantic-neighbor scores. Thus rebuilding uses raw intelligence without future candles and preserves replay no-look-ahead behavior.

## Versioning and migration
Each fingerprint stores fingerprint, feature-registry, semantic-registry, engine, and Market Lake schema versions. Old versions coexist under the index composite key; outdated records are detectable and rebuilding is controlled rather than silent. Raw Market Lake records are unchanged. `FINGERPRINT_INCOMPLETE`, `FEATURE_SOURCE_MISSING`, and `FEATURE_VALUE_INVALID` explain degraded legacy inputs. Sprint 18.4F may consume these immutable vectors and tokens in a Similarity Engine, but similarity scoring is not part of this sprint.

## Nested extraction aliases
A single deterministic dotted-path resolver uses explicit aliases for current nested `market_structure`, `market_regime`, `market_cycle`, `market_location`, `volume_structure`, `positioning_intelligence`, `compression_intelligence`, `manipulation_intelligence`, `institutional_evidence`, `decision_confidence`, `decision_confidence_validation`, `trade_opportunity_ranking`, and trigger-review layouts, followed by documented legacy flat keys. It does not perform fuzzy recursive searches, so outcome branches cannot leak into decision-state fingerprints.
