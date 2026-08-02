# Known Issues
- Expired candles cannot reconstruct historical bid/ask, IV, Greeks, or a complete exchange option-chain snapshot.
- Official documentation pages could not be fetched through the environment proxy; production enablement requires manual reconfirmation of current Upstox limits/rates.
- No background scheduler is included; live capture/finalization are scheduler-ready service contracts.
- Manual interactive Streamlit validation remains required.
