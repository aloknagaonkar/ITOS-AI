from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 100.0))


@dataclass(frozen=True)
class RankedStrike:
    rank: int
    strike: float
    option_type: str
    score: float
    ltp: float
    spread_pct: float
    delta: float
    oi: float
    change_oi: float
    volume: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrikeRanker:
    """Ranks option strikes by tradability, directional fit and liquidity."""

    def __init__(self, max_spread_pct: float = 4.0) -> None:
        self.max_spread_pct = max_spread_pct

    def score_strike(self, strike: dict[str, Any], side: str, spot: float | None = None) -> tuple[float, list[str]]:
        side = str(side).upper().replace("BUY ", "")
        option_type = str(strike.get("option_type") or strike.get("type") or strike.get("instrument_type") or "").upper()
        reasons: list[str] = []

        bid = _num(strike.get("bid") or strike.get("bid_price"))
        ask = _num(strike.get("ask") or strike.get("ask_price"))
        ltp = _num(strike.get("ltp") or strike.get("last_price") or strike.get("close"))
        midpoint = (bid + ask) / 2 if bid > 0 and ask > 0 else ltp
        spread_pct = ((ask - bid) / midpoint * 100.0) if midpoint > 0 and ask >= bid > 0 else 99.0
        liquidity_score = _clamp(100.0 - spread_pct * 18.0)
        if spread_pct <= 1.5:
            reasons.append("Tight bid-ask spread.")
        elif spread_pct > self.max_spread_pct:
            reasons.append("Wide bid-ask spread reduces execution quality.")

        oi = max(_num(strike.get("oi") or strike.get("open_interest")), 0.0)
        change_oi = _num(strike.get("change_oi") or strike.get("oi_change"))
        volume = max(_num(strike.get("volume")), 0.0)
        activity_score = _clamp((min(oi / 100000.0, 1.0) * 45.0) + (min(volume / 50000.0, 1.0) * 35.0) + (20.0 if change_oi > 0 else 8.0))
        if oi > 0:
            reasons.append("Open interest supports liquidity.")
        if volume > 0:
            reasons.append("Contract has active traded volume.")

        delta = _num(strike.get("delta") or strike.get("option_delta"))
        delta_abs = abs(delta)
        preferred_delta = 0.55
        delta_score = _clamp(100.0 - abs(delta_abs - preferred_delta) * 180.0) if delta_abs > 0 else 45.0
        if 0.35 <= delta_abs <= 0.70:
            reasons.append("Delta is in the preferred directional range.")

        iv = max(_num(strike.get("iv") or strike.get("implied_volatility")), 0.0)
        iv_score = 75.0 if 8.0 <= iv <= 35.0 else 55.0 if iv > 0 else 45.0

        strike_price = _num(strike.get("strike") or strike.get("strike_price"))
        moneyness_score = 60.0
        if spot and strike_price:
            distance_pct = abs(strike_price - spot) / spot * 100.0
            moneyness_score = _clamp(100.0 - distance_pct * 35.0)
            if distance_pct <= 0.6:
                reasons.append("Strike is near ATM.")

        side_match = option_type.endswith(side) or option_type == side or not option_type
        side_score = 100.0 if side_match else 0.0
        if not side_match:
            reasons.append(f"Contract type does not match requested {side} direction.")

        total = (
            liquidity_score * 0.26
            + activity_score * 0.24
            + delta_score * 0.20
            + moneyness_score * 0.15
            + iv_score * 0.08
            + side_score * 0.07
        )
        if spread_pct > self.max_spread_pct:
            total -= min((spread_pct - self.max_spread_pct) * 3.0, 25.0)
        if ltp <= 0:
            total -= 20.0
            reasons.append("No reliable last traded price.")

        return round(_clamp(total), 2), reasons[:6]

    def rank(self, strikes: Iterable[dict[str, Any]], side: str, spot: float | None = None, limit: int = 5) -> list[dict[str, Any]]:
        ranked: list[tuple[float, dict[str, Any], list[str]]] = []
        for item in strikes:
            score, reasons = self.score_strike(item, side=side, spot=spot)
            ranked.append((score, item, reasons))
        ranked.sort(key=lambda row: row[0], reverse=True)

        output: list[dict[str, Any]] = []
        for index, (score, item, reasons) in enumerate(ranked[: max(limit, 0)], start=1):
            bid = _num(item.get("bid") or item.get("bid_price"))
            ask = _num(item.get("ask") or item.get("ask_price"))
            ltp = _num(item.get("ltp") or item.get("last_price") or item.get("close"))
            midpoint = (bid + ask) / 2 if bid > 0 and ask > 0 else ltp
            spread_pct = ((ask - bid) / midpoint * 100.0) if midpoint > 0 and ask >= bid > 0 else 99.0
            ranked_strike = RankedStrike(
                rank=index,
                strike=_num(item.get("strike") or item.get("strike_price")),
                option_type=str(item.get("option_type") or item.get("type") or side).upper(),
                score=score,
                ltp=ltp,
                spread_pct=round(spread_pct, 2),
                delta=_num(item.get("delta") or item.get("option_delta")),
                oi=_num(item.get("oi") or item.get("open_interest")),
                change_oi=_num(item.get("change_oi") or item.get("oi_change")),
                volume=_num(item.get("volume")),
                reasons=tuple(reasons),
            )
            output.append(ranked_strike.to_dict())
        return output


def rank(strikes: Iterable[dict[str, Any]], side: str = "CE", spot: float | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Backward-compatible function retained for callers of the scaffold."""
    return StrikeRanker().rank(strikes, side=side, spot=spot, limit=limit)
