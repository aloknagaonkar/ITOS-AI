# Sprint 10 Summary

Sprint 10 routes the single Sprint 9 `InstitutionalMetrics` value in `DecisionContext` to Institutional Radar, Flow, Confidence, and Decision Matrix. Each engine retains one private legacy adapter. Existing recommendation, threshold, weight, engine-order, and safety logic remains in place.

Typed execution consumes OI-change totals in Radar; OI velocity/acceleration in Flow; the canonical liquidity score as a missing-component fallback in Confidence and Decision Matrix. Quality flags prevent absent OI columns from becoming directional evidence. Pipeline construction supports injection of the metrics engine for deterministic once-only verification.
