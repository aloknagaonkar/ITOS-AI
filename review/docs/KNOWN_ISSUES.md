# Known Issues
- Compression currently has a deliberately minimal typed upstream contract, so directional lean is consumed only when a compatible provider supplies it.
- Flow and regime metadata remain legacy-shaped and are read conservatively; malformed values become missing evidence.
- Evidence scores are explainable indices, not calibrated probabilities.
- Full pytest and Streamlit validation are intentionally deferred to local validation.
