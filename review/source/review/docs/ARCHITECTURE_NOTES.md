# Architecture Notes

The order is MarketSnapshot → InstitutionalMetrics → MarketLocation → VolumeStructure → PositioningIntelligence → CompressionIntelligence → ManipulationIntelligence → InstitutionalEvidence → DecisionConfidence → Validation → Ranking. `DecisionPipeline` calculates exactly one compression object and places that object in `DecisionContext.engine_results` and its typed field. Later engines consume that context, and `PipelineResults`/`dashboard_values()` expose the same reference.

The engine has no Streamlit, provider, repository, persistence, safety, or recommendation access. DataFrame work is performed on deep copies and analysis is restricted to timestamps at or before the snapshot cutoff.
