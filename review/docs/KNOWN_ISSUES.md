# Sprint 13 Known Issues

- True futures OI is not guaranteed by every provider payload. Explicitly labelled option/total OI fallback is marked `FUTURES_OI_PROXY_ONLY` and confidence-capped.
- Option premium changes, IV, Greeks, quotes, and historical OI can be absent; classifications then remain neutral/unavailable or confidence-capped.
- Put buying can represent protection, and call buying can represent hedging; the UI deliberately uses conditional language.
- Strike rotation, rollover, historical learning, and automated execution are outside this sprint.
- Streamlit rendering and the full pytest suite require local validation.

## Corrective note
Premium availability is evaluated per option side. An unavailable opposite-side premium remains visible as a quality flag but does not cap an otherwise valid selected state.

Legacy mapping input may use snapshot price fields when typed Volume Structure is absent. This compatibility behavior is isolated from canonical `DecisionContext` input and carries `VOLUME_STRUCTURE_UNAVAILABLE`.

The review/source positioning module is a review copy only; runtime imports must use `itos_platform/positioning_intelligence.py`.
