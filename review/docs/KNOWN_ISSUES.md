# Known Issues

- Ranking calibration has not yet been validated against historical outcomes.
- Relative nearby-strike participation uses absolute conservative activity bands in v1; adaptive/index-specific calibration remains future work.
- Expiry uses calendar DTE rather than exchange-session DTE.
- Missing optional values lower component scores and grades, but are never fabricated.
- UI runtime validation and pytest are intentionally deferred to local validation.
