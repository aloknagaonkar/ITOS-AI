# Sprint 13 Architecture Notes

The data path remains `MarketSnapshot → InstitutionalMetrics → DecisionContext → DecisionPipeline → PipelineResults → DashboardApplicationResult → app.py`. `PositioningIntelligenceEngine` runs after `VolumeStructureEngine`, performs no repository or Streamlit access, and returns one frozen `PositioningIntelligence` composed of frozen `PositioningState` values. The exact instance is placed in the context engine-result mapping and named context field, then passed into PipelineResults and its existing dashboard compatibility mapping. The dashboard only renders the supplied result.

The engine reads validated multi-candle price direction from VolumeStructure, explicitly labelled futures OI from the option-result summary, and options evidence from the normalized InstitutionalMetrics plus the supplied chain. Options OI is used as a futures proxy only when `futures_oi_proxy` explicitly opts in.
