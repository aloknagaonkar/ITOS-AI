# Known Issues

- Full pytest validation was intentionally not executed in the Codex environment.
- OI velocity and acceleration require valid, ordered history; missing history retains the existing warming-up/safe-degradation behavior.
- Granular gamma-wall and timeline displays still require strike history because aggregate metrics cannot reproduce strike-level rows.
- Metric quality is observational at these engine boundaries; existing safety gates remain authoritative.
