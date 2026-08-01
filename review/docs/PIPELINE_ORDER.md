# Decision Pipeline Order

## Before Sprint 8

1. MarketCycleEngine
2. RecommendationStabilityEngine
3. PhaseTransitionEngine
4. PatternRecognitionEngine
5. TradeReadinessEngine
6. InstitutionalRadarEngine
7. MarketStoryEngine
8. CandleDNAEngine
9. SmartCandlestickEngine
10. InstitutionalStructureEngine
11. InstitutionalFootprintEngine
12. FalseBreakoutEngine
13. InstitutionalConfirmationEngine
14. InstitutionalDecisionMatrixEngine
15. InstitutionalFlowEngine
16. InstitutionalConfidenceEngine
17. SignalValidationEngine
18. EarlyWarningEngine
19. MarketRegimeEngine
20. SmartMoneyIndexEngine
21. MarketEnergyEngine
22. DataHealthEngine

`AITradeEngine.build` ran after the engine sequence and application persistence/history operations.

## After Sprint 8

The order is exactly the same 1–22 sequence above. `DecisionPipeline.ENGINE_ORDER` is the executable characterization, and AI trade packaging remains downstream in `DashboardApplicationService`. **Engine execution order is unchanged.**

## Dependencies

| Stage | Consumes |
|---|---|
| Market Cycle | canonical MarketSnapshot, institutional compatibility |
| Recommendation Stability | shared DecisionContext, cycle result, confidence/phase histories, 70% existing configuration |
| Phase Transition | shared context and prior cycle/stability registry |
| Pattern Recognition | shared context and canonical candle history |
| Trade Readiness | recommendation, cycle, stability, pattern |
| Institutional Radar | shared context and repository histories already loaded by the service |
| Market Story | recommendation, cycle, transition, readiness, radar, pattern |
| Candle DNA / Smart Candlestick / Structure | shared context and earlier registered results |
| Institutional Footprint | option result, intelligence, institutional summary, cycle |
| False Breakout | shared context and structure/candle results |
| Institutional Confirmation | recommendation, footprint, structure, candles, pattern, cycle, false breakout |
| Decision Matrix | shared context and registered confirmation results |
| Institutional Flow / Confidence | shared context and registered earlier results/history |
| Signal Validation | recommendation, flow, confidence, confirmation, false breakout, stability |
| Early Warning | shared context and validation/flow results |
| Regime / Smart Money / Energy | shared context and registered prior results |
| Data Health | the same canonical MarketSnapshot used by Market Cycle |

## Safety-veto points

After Institutional Decision Matrix, the policy applies the existing cycle, stability, false-breakout, and institutional-confirmation vetoes. After Signal Validation and the v8 market-state engines, it applies the existing validation veto. After Data Health, it enforces the engine's existing `trading_allowed` metadata. Every pass is monotonic: only a currently confirmed recommendation can be downgraded, and no policy step restores confirmation.
