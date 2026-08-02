# Known Issues

- Expansion readiness is a deterministic heuristic, not a calibrated breakout probability.
- OI availability depends on the provider summary; proxy OI is explicitly flagged and confidence-capped.
- The engine uses completed rows supplied by the caller and cannot independently prove that a provider's last row is closed.
- Return volatility is price-based; option IV is deliberately not blended into it.
- UI and full pytest validation remain local-validation responsibilities.
- The five reported Sprint 14 local failures were fixture/expectation issues: four assumed a one-to-one recent-scale state despite the weighted composite, and one inserted a string into a strict float column before engine execution. The tests now isolate those concerns; pytest has not been rerun by Codex.
