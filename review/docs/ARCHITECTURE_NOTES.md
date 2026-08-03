# Architecture Notes
The flow is `SimilarityRequest → CandidateSelector(SQLite index) → semantic/numeric/context scorers → aggregator → difference analyzer → frozen match → outcomes → ranking/diversity → outcome/pattern summaries → view/export`. Context fingerprints remain separate. The service has no DecisionPipeline dependency.

## Historical composition
`compose_historical_pipeline` is the application boundary for the shared Market Lake, rebuildable index, replay runner, synchronization, similarity, option download, Live capture, and finalization services. Runtime clients and SQLite connections are not session-state values.

## 18.4F.2 orchestration
The guided UI depends on an immutable orchestration boundary. Service dependencies stay process-scoped, while Streamlit stores only immutable progress/results. Token-free atomic JSON checkpoints live under the Market Lake run metadata directory. The three-database operating model remains unchanged.

### 18.4F.2 hardening
Orchestration is per eligible date and maps service-returned facts into immutable checkpointed rows. Explicit prerequisite gates isolate failures, cadence is propagated, schema-v2 checkpoints load across process instances, and index-only/failed-only retries preserve completed source work.
