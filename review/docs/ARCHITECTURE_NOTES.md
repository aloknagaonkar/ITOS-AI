# Architecture Notes
The flow is `SimilarityRequest → CandidateSelector(SQLite index) → semantic/numeric/context scorers → aggregator → difference analyzer → frozen match → outcomes → ranking/diversity → outcome/pattern summaries → view/export`. Context fingerprints remain separate. The service has no DecisionPipeline dependency.
