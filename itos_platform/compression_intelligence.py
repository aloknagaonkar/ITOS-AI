"""Typed, decision-neutral compression context used by later intelligence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompressionIntelligence:
    """Existing compression evidence supplied to downstream engines.

    The default represents unavailable evidence and deliberately has no decision
    effect.  Sprint 15 consumes this contract but does not make compression alone
    evidence of manipulation.
    """

    state: str = "UNAVAILABLE"
    energy_stored: float = 0.0
    expansion_readiness: float = 0.0
    confidence: float = 0.0
    quality_flags: tuple[str, ...] = ("COMPRESSION_UNAVAILABLE",)
    explanations: tuple[str, ...] = (
        "Compression evidence is unavailable; no manipulation inference is made.",
    )

