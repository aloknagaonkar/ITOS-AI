# ITOS v8.1 — Historical Intelligence

## Added

- `HistoricalSimilarityEngine`
- `InstitutionalPlaybookEngine`
- `MarketReplayEngine`
- `ExplainableSessionReportEngine`
- `decision_audit` SQLite table
- `playbook_history` SQLite table
- Historical similarity, replay, playbook and audit dashboard panels
- CSV export for similarity and audit data

## Safety contract

- Historical matches do not produce an independent trade.
- Historical votes cannot bypass live signal validation.
- False-breakout, recommendation-stability, institutional-confirmation and risk controls remain authoritative.
- Similarity remains in warm-up mode until completed prior sessions exist.

## Validation

- Python compilation completed for all project modules.
- Historical engines passed synthetic smoke tests.
- SQLite schema initialization confirmed.

## v8.1.1 Custom Candle DNA Update

- Added **Injection-Pinbar (Bottom)** as a bullish custom Candle DNA pattern.
- Candle colour is intentionally ignored; detection is structure-based.
- Detection requires a large body, small upper wick, lower injection wick, and bottom/downmove context.
- Added live DNA metadata, dashboard alert, structure details, and automatic inclusion in the two-day historical pattern scanner.
