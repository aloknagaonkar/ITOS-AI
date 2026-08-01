# Sprint 13 Architecture Notes

The flow remains `MarketSnapshot → InstitutionalMetrics → DecisionContext → DecisionPipeline → PipelineResults → DashboardApplicationResult → app.py`. After Market Location and Volume Structure are available, `PositioningIntelligenceEngine` consumes only the supplied immutable context. It performs no repository or Streamlit access and creates no recommendation. The same frozen result is stored in `DecisionContext.engine_results`, the typed context field, and `PipelineResults`; the dashboard compatibility mapping exposes that object unchanged.
