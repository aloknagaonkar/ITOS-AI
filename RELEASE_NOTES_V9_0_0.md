# ITOS v9.0.0 — AI Decision Engine

## Added
- Normalized Directional Confidence (`0–100`) while preserving the legacy `2.60` confirmation gate.
- Independent CE and PE opportunity-strength scores.
- Stronger-side selection with strength-advantage protection.
- Trade Readiness score and explicit `READY — BUY CE`, `READY — BUY PE`, or `WAIT` decision.
- Informational Early Move Detector for CE/PE buildup monitoring.
- Expanded Trigger Checklist with Directional Confidence, Trade Readiness, Recommended Side, and Recommendation Confidence.
- AI Decision card now displays CE vs PE strength and the early buildup state.

## Decision safeguards
A confirmed trade requires directional confidence, trade readiness, side strength, strength advantage, recommendation confidence, participation, regime, contract quality, and no hard blocker.
The Early Move Detector cannot authorize a trade.
