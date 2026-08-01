# Sprint 13 Known Issues

- True futures OI is not guaranteed by every provider payload. Explicitly labelled option/total OI fallback is marked `FUTURES_OI_PROXY_ONLY` and confidence-capped.
- Option premium changes, IV, Greeks, quotes, and historical OI can be absent; classifications then remain neutral/unavailable or confidence-capped.
- Put buying can represent protection, and call buying can represent hedging; the UI deliberately uses conditional language.
- Strike rotation, rollover, historical learning, and automated execution are outside this sprint.
- Streamlit rendering and the full pytest suite require local validation.
