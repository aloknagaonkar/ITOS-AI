# Self Review

- **Replay UX architecture:** Framework-neutral control logic is separated from Streamlit presentation.
- **Live-mode preservation:** The legacy live path and its section order are unchanged; selectors are additive.
- **No-look-ahead:** Analysis snapshots remain provider-cutoff filtered; navigation uses completed candle timestamps.
- **Frozen-result:** Frozen objects are replaced per explicit execution and are not mutated by rendering.
- **Outcome separation:** `ReplayOutcome` accepts a distinct future frame and is revealed only on request.
- **Session-state isolation:** New state uses the documented `replay_*` prefix; resets leave live keys untouched.
- **Sample-mode safety:** The banner says NOT FOR TRADING and uses `SampleDataProvider`.
- **Dashboard preservation:** No existing section, card, chart, export, or download was removed or reordered.
- **Test gaps:** Streamlit interaction and authenticated historical integration need local/manual testing; pytest was not run.
- **Known assumptions:** Provider candle timestamps denote candle opens; archive timestamps are normalized to Asia/Kolkata.
- **Temporary technical debt:** Historical option-source wiring remains deployment-specific; outcome sparse-candle interpolation is intentionally absent.
- **Confidence:** 7/10 pending local behavioural and Streamlit validation.
