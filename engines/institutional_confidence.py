from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base_engine import BaseEngine, EngineResult


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(float(value), high))


def _first(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


@dataclass(frozen=True)
class ConfidenceWeights:
    oi_structure: float = 0.24
    pcr: float = 0.14
    volume: float = 0.10
    vwap: float = 0.12
    greeks: float = 0.14
    max_pain: float = 0.08
    trend: float = 0.12
    futures: float = 0.06

    def as_dict(self) -> dict[str, float]:
        return {
            "oi_structure": self.oi_structure,
            "pcr": self.pcr,
            "volume": self.volume,
            "vwap": self.vwap,
            "greeks": self.greeks,
            "max_pain": self.max_pain,
            "trend": self.trend,
            "futures": self.futures,
        }


class InstitutionalConfidenceEngine(BaseEngine):
    """Combines institutional option-chain evidence into a directional score.

    Expected fields are deliberately flexible because the existing dashboard uses
    several payload shapes. Missing evidence is treated as neutral and reduces
    data completeness instead of forcing a false directional signal.
    """

    name = "Institutional Confidence"

    def __init__(self, weights: ConfidenceWeights | None = None) -> None:
        self.weights = weights or ConfidenceWeights()

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        parts: dict[str, float] = {}
        reasons: list[str] = []
        available: set[str] = set()

        ce_change = _num(_first(market_data, "ce_change_oi", "call_change_oi", "total_ce_change_oi"))
        pe_change = _num(_first(market_data, "pe_change_oi", "put_change_oi", "total_pe_change_oi"))
        if ce_change or pe_change:
            available.add("oi_structure")
            denominator = abs(ce_change) + abs(pe_change) or 1.0
            oi_bias = (pe_change - ce_change) / denominator
            parts["oi_structure"] = 50.0 + 50.0 * oi_bias
            if oi_bias >= 0.15:
                reasons.append("Put-side OI addition is stronger than call-side OI addition.")
            elif oi_bias <= -0.15:
                reasons.append("Call-side OI addition is stronger than put-side OI addition.")

        pcr = _num(_first(market_data, "pcr", "oi_pcr", "put_call_ratio"), 0.0)
        pcr_change = _num(_first(market_data, "pcr_change", "pcr_delta"), 0.0)
        if pcr > 0:
            available.add("pcr")
            pcr_score = 50.0 + (pcr - 1.0) * 80.0 + pcr_change * 25.0
            parts["pcr"] = _clamp(pcr_score)
            reasons.append(f"PCR is {pcr:.2f}{' and rising' if pcr_change > 0 else ''}.")

        call_volume = _num(_first(market_data, "call_volume", "ce_volume", "total_ce_volume"))
        put_volume = _num(_first(market_data, "put_volume", "pe_volume", "total_pe_volume"))
        if call_volume or put_volume:
            available.add("volume")
            denominator = call_volume + put_volume or 1.0
            parts["volume"] = _clamp(50.0 + ((put_volume - call_volume) / denominator) * 50.0)
            if put_volume > call_volume * 1.1:
                reasons.append("Put volume is dominating call volume.")
            elif call_volume > put_volume * 1.1:
                reasons.append("Call volume is dominating put volume.")

        spot = _num(_first(market_data, "spot", "spot_price", "underlying_price"))
        vwap = _num(_first(market_data, "vwap", "spot_vwap"))
        if spot > 0 and vwap > 0:
            available.add("vwap")
            distance_pct = (spot - vwap) / vwap * 100.0
            parts["vwap"] = _clamp(50.0 + distance_pct * 25.0)
            reasons.append("Spot is above VWAP." if spot > vwap else "Spot is below VWAP.")

        delta = _num(_first(market_data, "delta", "selected_delta", "option_delta"))
        gamma = _num(_first(market_data, "gamma", "selected_gamma", "option_gamma"))
        if delta or gamma:
            available.add("greeks")
            # Positive delta is CE-friendly; negative delta is PE-friendly.
            greek_score = 50.0 + delta * 45.0 + max(min(gamma, 0.20), -0.20) * 50.0
            parts["greeks"] = _clamp(greek_score)
            reasons.append(f"Greeks directional score is {parts['greeks']:.0f}/100.")

        max_pain = _num(_first(market_data, "max_pain", "maxpain"))
        if spot > 0 and max_pain > 0:
            available.add("max_pain")
            distance_pct = (spot - max_pain) / max_pain * 100.0
            # Far above max pain mildly favours PE mean reversion; below favours CE.
            parts["max_pain"] = _clamp(50.0 - distance_pct * 15.0)
            reasons.append(f"Spot is {abs(spot - max_pain):.1f} points from max pain.")

        trend = str(_first(market_data, "trend", "market_trend", "bias", default="")).upper()
        if trend:
            available.add("trend")
            parts["trend"] = 72.0 if any(x in trend for x in ("BULL", "UP")) else 28.0 if any(
                x in trend for x in ("BEAR", "DOWN")
            ) else 50.0
            reasons.append(f"Price trend is {trend.title()}.")

        futures_price = _num(_first(market_data, "future_price", "futures_price"))
        if spot > 0 and futures_price > 0:
            available.add("futures")
            premium_pct = (futures_price - spot) / spot * 100.0
            parts["futures"] = _clamp(50.0 + premium_pct * 35.0)
            reasons.append(
                f"Futures trade at a {'premium' if futures_price >= spot else 'discount'} of {abs(futures_price - spot):.1f}."
            )

        weights = self.weights.as_dict()
        used_weight = sum(weights[name] for name in available)
        if used_weight <= 0:
            return EngineResult(
                self.name,
                50.0,
                "WAIT",
                ["Institutional confidence cannot be calculated because required market evidence is unavailable."],
                {"components": {}, "data_completeness": 0.0, "grade": "AVOID"},
                confidence=0.0,
                weight=1.0,
            )

        weighted = sum(parts[name] * weights[name] for name in available) / used_weight
        completeness = _clamp(used_weight / sum(weights.values()) * 100.0)
        confidence = _clamp(50.0 + abs(weighted - 50.0) * 1.15)
        vote = "CE" if weighted >= 58.0 else "PE" if weighted <= 42.0 else "WAIT"
        grade = "A+" if confidence >= 88 and completeness >= 70 else "A" if confidence >= 78 else "B" if confidence >= 66 else "C" if vote != "WAIT" else "AVOID"

        if vote == "WAIT":
            reasons.append("Institutional evidence is not sufficiently directional.")
        else:
            reasons.append(f"Institutional evidence favours {vote} with {confidence:.1f}% conviction.")

        return EngineResult(
            engine=self.name,
            score=round(weighted, 2),
            vote=vote,
            explanation=reasons[:8],
            metadata={
                "components": {name: round(parts[name], 2) for name in sorted(parts)},
                "weights": weights,
                "used_weight": round(used_weight, 4),
                "data_completeness": round(completeness, 1),
                "grade": grade,
                "directional_score": round(weighted, 2),
            },
            confidence=round(confidence, 2),
            weight=1.0,
        )


def score(parts: dict[str, float]) -> float:
    """Backward-compatible helper retained for callers of the original scaffold."""
    weights = ConfidenceWeights().as_dict()
    available = [name for name in weights if name in parts]
    denominator = sum(weights[name] for name in available) or 1.0
    return round(sum(_clamp(parts[name]) * weights[name] for name in available) / denominator, 2)
