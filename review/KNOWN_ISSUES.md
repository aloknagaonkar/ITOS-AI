# Known Issues

## Unexecuted Validation
The full repository test suite was not run, per the sprint instruction to run
targeted validation only. It remains a manual pre-merge check.

## Environment Limitations
Both targeted pytest files stop during collection because NumPy and pandas are unavailable
in this Python environment. Consequently, zero tests were collected or executed.

## Temporary Compatibility Adapter
`PhaseTransitionEngine._adapt_input` intentionally supports legacy mapping calls,
including the historical inline `cycle` fallback. Removal is deferred until all
callers use `DecisionContext`.

## Deferred Cleanup
Other downstream engines still consume legacy mappings and will be migrated in
future incremental sprints. No unrelated cleanup was included in Sprint 4.
