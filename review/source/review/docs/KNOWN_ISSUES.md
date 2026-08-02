# Known Issues

- OI build scoring requires typed OI velocity; explicitly marked proxy OI receives a confidence ceiling. Many live snapshots may therefore report `OI_UNAVAILABLE` until sufficient history exists.
- Release classification is deliberately conservative and uses only completed-candle follow-through; intrabar release is not inferred.
- Provider timestamp aliases are normalized, but a feed without timestamps cannot be cutoff-filtered and is analyzed in supplied order.
- Pytest and interactive Streamlit validation remain developer-local requirements.
