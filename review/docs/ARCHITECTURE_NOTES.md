# Architecture Notes

`VolumeStructureEngine` is repository- and UI-free. It consumes the canonical `DecisionContext` only after `MarketLocationEngine`, and its one immutable result is attached to the replaced context and `PipelineResults`. Recommendation and safety paths do not consume the result.
