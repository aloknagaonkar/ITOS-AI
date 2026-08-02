# Institutional Evidence Rules
## Source map and contract
`EvidenceItem` requires a unique code, label, BULLISH/BEARISH/NEUTRAL direction, clamped strength and reliability, source, and explanation. Sources are MarketLocation, VolumeStructure, PositioningIntelligence, CompressionIntelligence, ManipulationIntelligence, InstitutionalMetrics, InstitutionalFlow and descriptive MarketRegime/cycle context.

## Deduplication
Codes are unique and first observation wins. Classified positioning owns the price/OI fact; raw InstitutionalMetrics OI is not added when it merely repeats that classification. Metrics contribute only distinct PCR/liquidity/IV/Greeks facts. One fact therefore cannot inflate multiple groups.

## Directional evidence
Bullish examples include lower-range upward rotation, accumulation, confirmed bullish behaviour, long build-up, discounted short covering, put writing, hedging-caveated call buying, bullish release, false breakdown/bear trap, supportive PCR and bullish flow. Bearish rules mirror these for upper range, distribution, short build-up, discounted long unwinding, call writing, protection-caveated put buying, false breakout/bull trap and bearish flow. Balanced location/PCR, flat behaviour, mixed positioning, unconfirmed compression and weak flow are neutral, never silently missing.

## Contradictions and missing evidence
Simultaneously active bullish/bearish evidence and insufficient follow-through are retained as contradictions. Missing modules, liquidity, PCR, IV and Greeks are missing confirmations—not neutral items. Missing modules add explicit quality flags.

## Score formula
For a direction, each contribution is `source weight × strength × reliability / 100`; the sum is divided by participating source weights and clamped to 0–100. Scores are indices and need not sum to 100. Defaults live only in `InstitutionalEvidenceSettings`.

## Evidence quality and confidence
Quality starts at 85 and subtracts configured missing, thin-liquidity, proxy and stale penalties; no items yields zero. Confidence is `0.65 × quality + 0.35 × bullish/bearish separation`, less contradiction and missing penalties. It is capped for unresolved contradiction, thin/proxy evidence, or missing manipulation/positioning.

## Bias thresholds
No evidence/critical quality is UNAVAILABLE. Both directional scores at 45 or multiple contradictions are CONFLICTED. Difference below 6 is NEUTRAL; 6–17 is SLIGHTLY directional; 18–34 is directional; 35+ with quality 65+ is STRONGLY directional. All thresholds are configurable.

## Theme selection
Candidate effective contributions are sorted descending, then by configured theme priority, then lexical name. First is dominant and the first distinct remainder is secondary. With no candidate, DATA_INSUFFICIENT or RANGE_BALANCE is used deterministically.

## Narrative templates
The template reports location, price-volume behaviour, positioning, compression, manipulation, strongest metric/PCR, conclusion, primary contradiction and first critical missing confirmation. Wording remains conditional and never proposes an entry, stop, target or strike.

## Quality flags and malformed data
Flags include source `_UNAVAILABLE`, LIQUIDITY_THIN, PROXY_EVIDENCE_PRESENT, STALE_DATA, EVIDENCE_CONFLICTED, INDEPENDENT_EVIDENCE_INSUFFICIENT and EVIDENCE_QUALITY_LOW. Missing/malformed inputs safely return UNAVAILABLE/NEUTRAL/CONFLICTED with low confidence. Institutional Evidence is informational only and cannot create, promote or modify BUY CE, BUY PE or WAIT.
