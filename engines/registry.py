from __future__ import annotations

from typing import Any

from .base_engine import BaseEngine, EngineResult


class EngineRegistry:
    def __init__(self) -> None:
        self._engines: dict[str, BaseEngine] = {}

    def register(self, engine: BaseEngine) -> None:
        if engine.name in self._engines:
            raise ValueError(f"Engine already registered: {engine.name}")
        self._engines[engine.name] = engine

    def run(self, market_data: dict[str, Any]) -> dict[str, EngineResult]:
        return {name: engine.analyze(market_data) for name, engine in self._engines.items()}

    @property
    def engines(self) -> tuple[BaseEngine, ...]:
        return tuple(self._engines.values())
