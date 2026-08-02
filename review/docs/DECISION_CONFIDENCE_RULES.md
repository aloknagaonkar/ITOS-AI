# Decision Confidence Rules

## Bias, confidence, and readiness
Institutional bias describes directional evidence. Decision Confidence describes analytical reliability without choosing CE or PE. Ranking readiness is a strict eligibility flag for a future ranking engine. None changes live recommendation confidence or safety in Sprint 17A.

## Contracts and pillar inputs
`ConfidencePillar` is frozen and exposes code, label, score, normalized weight, reliability, effective contribution, explanation, and flags. `DecisionConfidence` is frozen and exposes the overall result and all reasoning. The seven pillars are Market Context (location/cycle clarity), Price & Volume (agreement), Positioning (futures/options coherence), Compression (state interpretability), Manipulation Safety (inverse risk), Institutional Evidence (quality/independence/contradictions), and Data Quality (health/freshness/completeness/liquidity).

## Scoring, reliability, contribution, and weights
Every numeric output is clamped to 0–100. Upstream confidence supplies reliability; unavailable input has zero reliability. Configured weights default to 15/15/15/10/15/20/10 and are normalized to 100. Effective contribution is `score × reliability × normalized weight / 10,000`; contributions are summed and deduplicated penalties subtracted before floor and strictest ceiling.

## Contributors, penalties, and deduplication
Clear context, aligned price/volume, coherent positioning, defined compression, low manipulation risk, strong evidence, and healthy data create human-readable contributors. Penalties contain a stable code, explanation, and practical numeric impact. A dictionary keyed by underlying-fact code prevents repeated equivalent observations from stacking. The documented priority is stale data, critical candles, manipulation, trap, contradictions, thin liquidity, proxy evidence, mixed positioning, volume divergence, compression conflict, then missing modules.

## Missing confirmations, ceilings, floor, and blockers
Missing confirmations describe prerequisites and need not independently reduce score. Default ceilings are manipulation unavailable 70, evidence unavailable 55, positioning unavailable 65, stale data 50, critical candles 35, proxy evidence 75, and thin/incomplete evidence 60; the strictest applies and is exposed. The default floor is zero and never rescues missing data. Stale/malformed critical data, excessive manipulation/trap risk, low evidence/data quality, too many contradictions, and insufficient valid pillars block readiness.

## Grades, setup quality, and ranking readiness
Defaults: 95 A_PLUS/INSTITUTIONAL_GRADE; 85 A/HIGH_QUALITY; 70 B/TRADABLE; 55 C/DEVELOPING; 40 D/WEAK; otherwise AVOID. With no valid pillars both values are UNAVAILABLE. Readiness requires score >=70, at least five reliable pillars, available institutional/manipulation evidence, data quality >=60, evidence quality >=55, contradictions <=2, and no blocker.

## Flags, narrative, and missing data
Flags expose unavailable pillars, stale/thin/proxy data, insufficient pillars, high contradictions, blockers, unavailable confidence, and non-readiness. Deterministic narrative names the strongest and weakest pillars, primary penalty, primary missing confirmation, readiness state, and informational-only status. Malformed or missing values safely become low/unavailable; no direction, strike, entry, stop, target, or guaranteed language is generated.
