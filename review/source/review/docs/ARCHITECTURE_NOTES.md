# Architecture Notes

`DecisionPipeline.execute` obtains metrics once, stores that exact immutable instance on a replaced `DecisionContext`, and passes the context through the migrated engines. A caller-supplied instance bypasses calculation. The optional constructor dependency exists for deterministic counting and does not change default behavior.

Each migrated engine owns one `_adapt_input` boundary. Typed contexts preserve the metrics object by identity. Legacy mappings remain accepted and may contain `institutional_metrics`; otherwise pre-Sprint-10 raw calculations remain the fallback. No engine constructs `InstitutionalMetrics`.
