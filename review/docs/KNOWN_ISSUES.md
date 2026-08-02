# Known Issues

- Expansion readiness is a deterministic heuristic, not a calibrated breakout probability.
- OI availability depends on the provider summary; proxy OI is explicitly flagged and confidence-capped.
- The engine uses completed rows supplied by the caller and cannot independently prove that a provider's last row is closed.
- Return volatility is price-based; option IV is deliberately not blended into it.
- UI and full pytest validation remain local-validation responsibilities.
