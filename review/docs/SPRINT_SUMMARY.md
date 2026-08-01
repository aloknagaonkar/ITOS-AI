# Sprint 11 Summary

Implemented the immutable `MarketLocation`, configurable `MarketLocationSettings`, and repository/UI-independent `MarketLocationEngine`. The pipeline computes it after candle and structure evidence and reuses that instance through `DecisionContext`, `PipelineResults`, and dashboard values. A collapsed informational preview and behavioral tests were added. Recommendation and safety logic remain unchanged.
