# Architecture Notes

## DecisionPipeline

The pipeline isolates deterministic decision orchestration from application I/O. It receives the one `DecisionContext`, invokes engines in the already-characterized order, registers each result once for downstream legacy adapters, and returns one typed result. It performs no repository, Streamlit, acquisition, persistence, or AI trade packaging work. `DashboardApplicationService` remains the transaction/application boundary.

## Typed PipelineResults

A frozen dataclass gives callers stable, named access to all 22 engine outputs and the final safety decision. This prevents a mutable dictionary from becoming the public pipeline API, makes wiring errors visible, and leaves calculations inside their original engines.

## SafetyGatePolicy

The policy consolidates the pre-existing cycle, 70% stability, false-breakout, institutional-confirmation, and signal-validation gates in their original order and wording. It additionally enforces the existing Data Health engine's `trading_allowed` safety metadata so missing/unhealthy critical data cannot produce BUY. Enforcement is monotonic: every gate is conditional on the recommendation still being confirmed, and later passes never set confirmation back to true. No new numeric threshold was introduced.

## Temporary compatibility mapping

`DecisionContext.engine_results` remains a mutable compatibility registry because downstream migrated engines still read those historical keys. `PipelineResults` is authoritative. `PipelineResults.dashboard_values()` maps named fields into the existing dynamic dashboard result, and supplies `ice_result` and `smi_result` aliases. A future sprint may migrate every consumer to named results and then remove mutable `engine_results`; that removal is explicitly out of scope here.

## Failure contract, risk, and rollback

Critical engine exceptions continue to propagate, matching the prior orchestration. Consequently persistence and `AITradeEngine.build` after the failed stage do not run and no BUY package is emitted. The main risk is an undiscovered legacy dependency on mutation timing; characterization tests cover known dependencies. Rollback consists of reverting the service delegation and the three new platform contracts; engine implementations and persistence schemas require no rollback.

## Import boundary correction

The package root deliberately exports only low-level provider and decision-context contracts. It does not initialize `DecisionPipeline` or `SafetyGatePolicy`, because the pipeline imports concrete engine modules and therefore belongs above both the platform-contract and engine package initialization boundaries. Application and test consumers import orchestration and policy types directly from their defining modules. The pipeline likewise imports engines from their concrete modules rather than the `engines` barrel. This keeps dependency direction acyclic without lazy imports, exception suppression, or runtime import tricks.
