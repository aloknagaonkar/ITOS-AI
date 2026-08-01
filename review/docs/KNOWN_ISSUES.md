# Sprint 13 Known Issues

- Many live providers do not currently supply explicit futures OI change, so futures positioning can remain unavailable unless that field is present or an explicit proxy is enabled.
- Option premium change aliases must be present for writing/buying confirmation; otherwise the engine intentionally stays neutral or unavailable with a quality flag.
- Strike-level dominant activity is described only by aggregate evidence in v1; rotation and rollover logic remain deferred.
- UI and pytest validation are intentionally reserved for local validation.
