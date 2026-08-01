# Known Issues

- The full pytest suite has not been run in the Codex environment and requires local validation before merge.
- `DecisionContext.engine_results` is intentionally a mutable mapping inside a frozen dataclass so the ordered pipeline can publish results without replacing the canonical context instance. This preserves the established migration architecture.
