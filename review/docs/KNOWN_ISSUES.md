# Known Issues

- Historical option snapshots remain dependent on a configured backend option source; absence is displayed as unavailable and never replaced by live data.
- The replay workspace freezes and displays its point-in-time snapshot. Full Analyst Dashboard replay rendering requires a successful existing application-pipeline result with sufficient provider inputs.
- Upstox historical availability, holidays, retention, and authentication are external constraints.
- Outcome horizons resolve to the first available candle at or after a horizon, so sparse archives may not represent the exact requested minute.
- pytest was intentionally not run; local validation is required.
