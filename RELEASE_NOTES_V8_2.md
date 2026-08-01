# ITOS v8.2 — Decision Intelligence

Built on v8.1.2 and preserves the Injection-Pinbar Bottom and Small-Tip Candle DNA variants.

## Added
- AI Consensus Engine with confidence-weighted CE, PE and WAIT votes
- Trade Probability Engine with separate CE, PE and WAIT probabilities
- Enhanced Risk Validation with critical veto controls
- Conflict detection and missing-evidence penalties
- Decision Reasoning Trace
- Invalidation Engine
- Structured Decision Package consumed by the dashboard
- Decision Intelligence Center with vote, risk and probability tables

## Safety contract
- Critical risk checks override directional consensus.
- Historical similarity and custom candles remain supporting evidence only.
- The system returns WAIT when evidence is weak, conflicting or incomplete.
- Outputs are analytical decision support, not guaranteed trading outcomes.
