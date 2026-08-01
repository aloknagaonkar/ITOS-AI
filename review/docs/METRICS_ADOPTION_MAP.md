# Institutional Metrics Adoption Map

| Engine | Typed metric consumed | Previous raw source | Fallback | Calculation eliminated in typed path | Quality handling | Decision logic |
|---|---|---|---|---|---|---|
| InstitutionalRadarEngine | call/put change in OI | `option_result.summary` | summary totals | Yes, totals are not recalculated | missing-column flags retain raw fallback; absent evidence stays neutral | Unchanged |
| InstitutionalFlowEngine | call/put OI velocity and acceleration | slopes/acceleration over decision history | existing historical functions | Yes when complete typed motion exists | `None` motion retains characterized safe fallback; missing history remains WAIT | Unchanged |
| InstitutionalConfidenceEngine | liquidity score / total volume evidence via Flow and missing Volume component fallback | recommendation component scores and Flow result | existing component/default 50 | Yes for typed liquidity fallback | missing component uses score (zero for unhealthy/missing volume), never directionalizes missing evidence | Unchanged |
| InstitutionalDecisionMatrixEngine | liquidity score when the legacy Liquidity component is absent | recommendation `component_scores.Liquidity` | existing component/default 50 | Yes for typed fallback | typed zero remains weak/risk evidence and cannot promote BUY | Unchanged |

The shared typed object also carries OI totals, PCR family, Max Pain, ATM IV/skew, Greeks/gamma exposure, volume, thin-market, writing/positioning, and futures premium. Metrics not mathematically equivalent to a current engine input remain available on `DecisionContext` but are not substituted for a different formula.
