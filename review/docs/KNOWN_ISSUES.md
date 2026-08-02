# Known Issues
- The relationship graph remains an intentionally preliminary semantic-overlap graph, not Sprint 18.4F similarity scoring.
- Auto-update integration is exposed through failure-isolated persistence hooks; application composition must opt in using the corresponding settings.
- Validation reports corruption and collisions but intentionally performs no implicit repair.
- Manual UI validation remains required; no normal UI files changed.
