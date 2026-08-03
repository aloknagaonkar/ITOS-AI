# Architecture Notes
The flow is `SimilarityRequest → CandidateSelector(SQLite index) → semantic/numeric/context scorers → aggregator → difference analyzer → frozen match → outcomes → ranking/diversity → outcome/pattern summaries → view/export`. Context fingerprints remain separate. The service has no DecisionPipeline dependency.

## Historical composition
`compose_historical_pipeline` is the application boundary for the shared Market Lake, rebuildable index, replay runner, synchronization, similarity, option download, Live capture, and finalization services. Runtime clients and SQLite connections are not session-state values.
