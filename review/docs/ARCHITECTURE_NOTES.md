# Architecture Notes

The `TradeOpportunityRankingEngine` runs after `DecisionConfidenceValidationEngine`. It receives only `DecisionContext`, performs no repository or Streamlit access, and returns frozen dataclasses. The exact result instance is installed into `DecisionContext.engine_results`, the typed context field, `PipelineResults`, and the dashboard compatibility mapping. The UI only renders fields; it performs no ranking. No recommendation or safety input consumes the ranking.
