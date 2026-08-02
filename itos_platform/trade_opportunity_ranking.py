"""Explainable, deterministic and informational option-contract ranking.

The engine consumes only the immutable decision context.  Its output is a
shadow decision-support result: it cannot place an order or alter the existing
recommendation/strike-selection path.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from .decision_context import DecisionContext


def _clamp(value: Any) -> float:
    try:
        return round(max(0.0, min(100.0, float(value))), 2)
    except (TypeError, ValueError, OverflowError):
        return 0.0


@dataclass(frozen=True)
class OptionOpportunity:
    option_type: str
    strike: float
    expiry: object | None
    symbol: str | None
    opportunity_score: float
    grade: str
    risk_level: str
    eligible: bool
    ltp: float | None
    bid: float | None
    ask: float | None
    spread: float | None
    spread_percent: float | None
    oi: float | None
    oi_change: float | None
    volume: float | None
    iv: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    moneyness: str
    distance_from_spot: float | None
    distance_percent: float | None
    dte: int | None
    liquidity_score: float
    spread_quality_score: float
    oi_volume_score: float
    greeks_score: float
    iv_score: float
    moneyness_score: float
    direction_compatibility_score: float
    expiry_score: float
    risk_score: float
    positive_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    rejection_reasons: tuple[str, ...]
    quality_flags: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class TradeOpportunityRanking:
    ranking_state: str
    ranking_eligible: bool
    eligibility_reason: str
    preferred_direction: str
    institutional_bias: str
    decision_confidence: float
    validation_state: str
    top_ce: tuple[OptionOpportunity, ...]
    top_pe: tuple[OptionOpportunity, ...]
    rejected_count: int
    evaluated_count: int
    best_ce: OptionOpportunity | None
    best_pe: OptionOpportunity | None
    best_overall: OptionOpportunity | None
    quality_flags: tuple[str, ...]
    explanations: tuple[str, ...]
    narrative: str
    rejected: tuple[OptionOpportunity, ...] = ()
    rejection_reason_counts: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class TradeOpportunityRankingSettings:
    minimum_oi: float = 100.0
    minimum_volume: float = 10.0
    maximum_spread_percent: float = 20.0
    critical_spread_percent: float = 35.0
    maximum_distance_percent: float = 5.0
    deep_otm_percent: float = 3.0
    deep_itm_percent: float = 4.0
    preferred_delta_minimum: float = 0.35
    preferred_delta_maximum: float = 0.70
    gamma_risk_threshold: float = 0.08
    theta_risk_threshold: float = 20.0
    elevated_iv_threshold: float = 35.0
    extreme_iv_threshold: float = 60.0
    minimum_dte: int = 0
    preferred_dte_minimum: int = 2
    preferred_dte_maximum: int = 21
    maximum_dte: int = 60
    severe_manipulation_threshold: float = 85.0
    minimum_eligible_per_chain: int = 1
    minimum_best_overall_score: float = 60.0
    unstable_grade_ceiling: str = "B"
    weights: tuple[tuple[str, float], ...] = (
        ("liquidity", 15), ("spread", 10), ("oi_volume", 12),
        ("greeks", 13), ("iv", 10), ("moneyness", 10),
        ("expiry", 8), ("direction", 12), ("risk", 5),
        ("confidence", 5),
    )
    grade_thresholds: tuple[tuple[float, str], ...] = (
        (90, "A_PLUS"), (80, "A"), (70, "B"), (60, "C"), (50, "D"),
    )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "TradeOpportunityRankingSettings":
        raw = (value or {}).get("trade_opportunity_ranking", value or {})
        allowed = {item.name for item in fields(cls)}
        try:
            return cls(**{key: raw[key] for key in allowed if key in raw})
        except (TypeError, ValueError):
            return cls()


class TradeOpportunityRankingEngine:
    """Rank normalized contracts without querying data sources or changing decisions."""

    _ALIASES = {
        "strike": ("strike", "strike_price"), "option_type": ("option_type", "type", "right"),
        "expiry": ("expiry", "expiry_date"), "symbol": ("symbol", "trading_symbol", "instrument_key"),
        "ltp": ("ltp", "last_price", "last_traded_price"), "bid": ("bid", "bid_price"),
        "ask": ("ask", "ask_price"), "oi": ("oi", "open_interest"),
        "oi_change": ("oi_change", "change_in_oi", "oi_change_percentage"),
        "volume": ("volume", "traded_volume"), "iv": ("iv", "implied_volatility"),
        "delta": ("delta",), "gamma": ("gamma",), "theta": ("theta",), "vega": ("vega",),
    }

    def __init__(self, settings: TradeOpportunityRankingSettings | None = None) -> None:
        self.settings = settings

    def analyze(self, context: DecisionContext) -> TradeOpportunityRanking:
        cfg = self.settings or TradeOpportunityRankingSettings.from_mapping(
            context.configuration or context.runtime_configuration
        )
        confidence = context.decision_confidence
        validation = context.decision_confidence_validation
        evidence = context.institutional_evidence
        bias = str(getattr(evidence, "bias", "UNAVAILABLE")).upper()
        preferred = self._preferred_direction(bias)
        score = _clamp(getattr(confidence, "score", 0))
        validation_state = str(getattr(validation, "ranking_eligibility_state", "UNAVAILABLE"))

        if confidence is None or not bool(getattr(confidence, "ranking_ready", False)):
            return self._blocked("Decision Confidence is not ready for ranking.", preferred, bias, score, validation_state)
        if validation is None or not bool(getattr(validation, "ranking_eligible", False)):
            return self._blocked("Decision Confidence Validation is not eligible for ranking.", preferred, bias, score, validation_state)

        option_result = context.market_snapshot.option_result
        chain = option_result.get("chain") if isinstance(option_result, Mapping) else None
        if chain is None:
            return self._blocked("The option chain is unavailable.", preferred, bias, score, validation_state, "OPTION_CHAIN_UNAVAILABLE")
        rows = self._rows(chain)
        if not rows:
            return self._blocked("The option chain is empty.", preferred, bias, score, validation_state, "OPTION_CHAIN_EMPTY")
        spot = self._number((option_result.get("summary") or {}).get("spot"))
        if spot is None or spot <= 0:
            spot = next((self._number(row.get("spot")) for row in rows if self._number(row.get("spot"))), None)
        if spot is None or spot <= 0:
            return self._blocked("Spot is unavailable; strike distance cannot be evaluated.", preferred, bias, score, validation_state, "SPOT_UNAVAILABLE")

        normalized, malformed = self._normalize(rows, context.market_snapshot.expiry)
        candidates = [self._score(row, spot, context, cfg) for row in normalized]
        # Duplicate identity uses side/strike/expiry/symbol; keep the highest-quality copy.
        unique: dict[tuple[Any, ...], OptionOpportunity] = {}
        for item in candidates:
            key = (item.option_type, item.strike, str(item.expiry), item.symbol or "")
            previous = unique.get(key)
            if previous is None or self._sort_key(item) < self._sort_key(previous):
                unique[key] = item
        candidates = list(unique.values())
        eligible = [item for item in candidates if item.eligible]
        rejected = [item for item in candidates if not item.eligible]
        if malformed:
            rejected.extend(self._malformed_rejection() for _ in range(malformed))
        if len(eligible) < cfg.minimum_eligible_per_chain:
            counts = self._reason_counts(rejected)
            return TradeOpportunityRanking(
                "NOT_ELIGIBLE", False, "No sufficiently liquid, scorable contracts passed the baseline filters.",
                preferred, bias, score, validation_state, (), (), len(rejected), len(candidates) + malformed,
                None, None, None, ("LIQUIDITY_THIN", "RANKING_GATE_FAILED"),
                ("All normalized contracts failed baseline eligibility.",),
                "Trade opportunity ranking is not eligible because no contract passed the conservative liquidity and quality filters.",
                tuple(rejected), counts,
            )
        top_ce = tuple(sorted((x for x in eligible if x.option_type == "CE"), key=self._sort_key)[:5])
        top_pe = tuple(sorted((x for x in eligible if x.option_type == "PE"), key=self._sort_key)[:5])
        top_ce = self._rank_explanations(top_ce)
        top_pe = self._rank_explanations(top_pe)
        best_ce, best_pe = next(iter(top_ce), None), next(iter(top_pe), None)
        best_overall = self._best_overall(top_ce, top_pe, preferred, cfg)
        flags = []
        if malformed: flags.append("OPTION_ROWS_INVALID")
        if not top_ce: flags.append("INSUFFICIENT_ELIGIBLE_CE")
        if not top_pe: flags.append("INSUFFICIENT_ELIGIBLE_PE")
        state = "RANKED" if top_ce or top_pe else "INSUFFICIENT_CANDIDATES"
        return TradeOpportunityRanking(
            state, True, "Ranking eligibility and contract-quality gates passed.", preferred, bias,
            score, validation_state, top_ce, top_pe, len(rejected), len(candidates) + malformed,
            best_ce, best_pe, best_overall, tuple(flags),
            (f"Evaluated {len(candidates) + malformed} contracts; {len(eligible)} passed baseline filters.",
             "Scores are suitability measures, not probabilities of profit."),
            "Eligible contracts are ranked independently on both sides for informational decision support only.",
            tuple(rejected), self._reason_counts(rejected),
        )

    @staticmethod
    def _rows(chain: Any) -> list[dict[str, Any]]:
        if isinstance(chain, pd.DataFrame): return chain.to_dict("records")
        if isinstance(chain, Sequence) and not isinstance(chain, (str, bytes)):
            return [dict(row) for row in chain if isinstance(row, Mapping)]
        return []

    def _normalize(self, rows: list[dict[str, Any]], default_expiry: str) -> tuple[list[dict[str, Any]], int]:
        output: list[dict[str, Any]] = []; malformed = 0
        for raw in rows:
            lower = {str(k).lower(): v for k, v in raw.items()}
            strike = self._pick(lower, self._ALIASES["strike"])
            if self._number(strike) is None:
                malformed += 1; continue
            option_type = str(self._pick(lower, self._ALIASES["option_type"]) or "").upper()
            if option_type in {"CALL", "C"}: option_type = "CE"
            if option_type in {"PUT", "P"}: option_type = "PE"
            if option_type in {"CE", "PE"}:
                output.append(self._single(lower, option_type, default_expiry))
                continue
            combined = False
            for side, prefix in (("CE", "call"), ("PE", "put")):
                if any(f"{prefix}_{name}" in lower or f"{'ce' if side == 'CE' else 'pe'}_{name}" in lower for name in ("ltp", "oi", "volume", "delta")):
                    output.append(self._combined(lower, side, prefix, default_expiry)); combined = True
            if not combined: malformed += 1
        return output, malformed

    def _single(self, row: Mapping[str, Any], side: str, default_expiry: str) -> dict[str, Any]:
        return {name: self._pick(row, aliases) for name, aliases in self._ALIASES.items()} | {"option_type": side, "expiry": self._pick(row, self._ALIASES["expiry"]) or default_expiry}

    def _combined(self, row: Mapping[str, Any], side: str, prefix: str, default_expiry: str) -> dict[str, Any]:
        short = "ce" if side == "CE" else "pe"
        result = {"strike": self._pick(row, self._ALIASES["strike"]), "option_type": side,
                  "expiry": self._pick(row, self._ALIASES["expiry"]) or default_expiry}
        for name in ("symbol", "ltp", "bid", "ask", "oi", "oi_change", "volume", "iv", "delta", "gamma", "theta", "vega"):
            result[name] = self._pick(row, tuple(f"{p}_{a}" for p in (prefix, short) for a in self._ALIASES[name]))
        return result

    def _score(self, row: dict[str, Any], spot: float, context: DecisionContext, cfg: TradeOpportunityRankingSettings) -> OptionOpportunity:
        side = row["option_type"]; strike = self._number(row.get("strike")) or 0.0
        values = {key: self._number(row.get(key)) for key in ("ltp", "bid", "ask", "oi", "oi_change", "volume", "iv", "delta", "gamma", "theta", "vega")}
        expiry, dte = self._expiry(row.get("expiry")); distance = strike - spot; distance_pct = abs(distance) / spot * 100
        spread = values["ask"] - values["bid"] if values["ask"] is not None and values["bid"] is not None else None
        midpoint = (values["ask"] + values["bid"]) / 2 if spread is not None else None
        denominator = midpoint if midpoint and midpoint > 0 else values["ltp"]
        spread_pct = spread / denominator * 100 if spread is not None and denominator and denominator > 0 else None
        moneyness = self._moneyness(side, distance_pct, distance, cfg)
        flags: list[str] = []; warnings: list[str] = []; reject: list[str] = []; positives: list[str] = []
        if strike <= 0: reject.append("Missing or invalid strike")
        if values["ltp"] is None or values["ltp"] < 0: reject.append("No LTP")
        if expiry is None: reject.append("Invalid expiry"); flags.append("EXPIRY_UNAVAILABLE")
        if values["bid"] is None or values["ask"] is None:
            warnings.append("Bid/ask is unavailable"); flags.append("BID_ASK_UNAVAILABLE")
        elif spread is not None and spread < 0: reject.append("Invalid bid/ask spread")
        elif spread_pct is not None and spread_pct > cfg.critical_spread_percent: reject.append("Spread is critically wide")
        elif spread_pct is not None and spread_pct > cfg.maximum_spread_percent: warnings.append("Bid/ask spread is wide")
        if values["oi"] is None: warnings.append("OI is unavailable"); flags.append("OI_UNAVAILABLE")
        elif values["oi"] < cfg.minimum_oi: reject.append("OI below minimum")
        if values["volume"] is None: warnings.append("Volume is unavailable"); flags.append("VOLUME_UNAVAILABLE")
        elif values["volume"] < cfg.minimum_volume: reject.append("Volume below minimum")
        if distance_pct > cfg.maximum_distance_percent: reject.append("Strike exceeds allowed distance from spot")
        if moneyness == "DEEP_OTM": reject.append("Deep OTM beyond allowed distance")
        if dte is not None and (dte < cfg.minimum_dte or dte > cfg.maximum_dte): reject.append("Unacceptable DTE")
        manipulation = context.manipulation_intelligence
        side_risk = _clamp(getattr(manipulation, "bull_trap_risk" if side == "CE" else "bear_trap_risk", 0))
        if side_risk >= cfg.severe_manipulation_threshold: reject.append(f"Severe manipulation risk on {side} side")

        spread_score = 30.0 if spread_pct is None else _clamp(100 - spread_pct / cfg.critical_spread_percent * 100)
        oi_score = 30.0 if values["oi"] is None else _clamp(values["oi"] / max(cfg.minimum_oi * 10, 1) * 100)
        volume_score = 30.0 if values["volume"] is None else _clamp(values["volume"] / max(cfg.minimum_volume * 10, 1) * 100)
        oi_volume = _clamp(oi_score * .6 + volume_score * .4)
        quote_score = 100 if values["bid"] is not None and values["ask"] is not None else 25
        liquidity = _clamp(oi_volume * .55 + spread_score * .3 + quote_score * .15)
        if liquidity >= 70: positives.append("liquidity is strong")
        elif liquidity < 45: warnings.append("Liquidity is thin"); flags.append("LIQUIDITY_THIN")

        greeks = 50.0
        delta = abs(values["delta"]) if values["delta"] is not None else None
        if delta is None: warnings.append("Greeks are incomplete"); flags.append("GREEKS_UNAVAILABLE"); greeks -= 15
        elif cfg.preferred_delta_minimum <= delta <= cfg.preferred_delta_maximum: greeks += 30; positives.append("delta is inside the preferred range")
        elif delta < .15 or delta > .90: greeks -= 30; warnings.append("Delta is outside the directional suitability range")
        else: greeks -= 5
        if values["theta"] is not None and abs(values["theta"]) > cfg.theta_risk_threshold:
            greeks -= 20 if dte is None or dte > 1 else 30; warnings.append("Theta decay is elevated")
        if values["gamma"] is not None and dte is not None and dte <= 1 and abs(values["gamma"]) > cfg.gamma_risk_threshold:
            greeks -= 25; warnings.append("Near-expiry gamma risk is elevated")
        greeks = _clamp(greeks)
        iv = values["iv"]
        if iv is None: iv_score = 40.0; warnings.append("IV is unavailable"); flags.append("IV_UNAVAILABLE")
        elif iv > cfg.extreme_iv_threshold: iv_score = 20.0; warnings.append("IV is extremely elevated")
        elif iv > cfg.elevated_iv_threshold: iv_score = 55.0; warnings.append("IV is moderately elevated")
        elif 10 <= iv <= cfg.elevated_iv_threshold: iv_score = 85.0; positives.append("IV is within a reasonable chain context")
        else: iv_score = 55.0; warnings.append("Low IV is not treated as cheap without context")
        m_score = {"ATM": 100, "ITM": 85, "OTM": 75, "DEEP_ITM": 45, "DEEP_OTM": 10}.get(moneyness, 30)
        if moneyness == "ATM": positives.append("the strike is near ATM")
        if moneyness == "DEEP_ITM": warnings.append("Deep ITM premium/capital risk is elevated")
        expiry_score = 30.0 if dte is None else (50.0 if dte <= 1 else 90.0 if dte <= cfg.preferred_dte_maximum else 65.0)
        if dte is not None and dte <= 1: warnings.append("Low DTE increases theta and gamma risk")
        direction = self._direction_score(side, context)
        if direction >= 70: positives.append("institutional direction is compatible")
        elif direction <= 35: warnings.append("Institutional direction favours the opposite side")
        risk = _clamp(100 - side_risk)
        if side_risk >= 50: warnings.append(f"{side} manipulation/trap risk is elevated")
        confidence_score = _clamp(getattr(context.decision_confidence, "score", 0))
        components = {"liquidity": liquidity, "spread": spread_score, "oi_volume": oi_volume,
                      "greeks": greeks, "iv": iv_score, "moneyness": m_score, "expiry": expiry_score,
                      "direction": direction, "risk": risk, "confidence": confidence_score}
        weights = dict(cfg.weights); total = sum(max(0.0, x) for x in weights.values()) or 100
        opportunity = _clamp(sum(components[k] * max(0.0, weights.get(k, 0)) for k in components) / total)
        eligible = not reject
        grade = self._grade(opportunity, cfg) if eligible else "REJECTED"
        if eligible and "UNSTABLE" in str(getattr(context.decision_confidence_validation, "stability_state", "")) and grade in {"A_PLUS", "A"}:
            grade = cfg.unstable_grade_ceiling; warnings.append("Unstable confidence history caps the grade")
        risk_level = "UNAVAILABLE" if not eligible else "LOW" if opportunity >= 80 and not warnings else "MODERATE" if opportunity >= 65 else "HIGH" if opportunity >= 50 else "VERY_HIGH"
        explanation = self._explanation(strike, side, positives, warnings, eligible, reject)
        return OptionOpportunity(side, strike, expiry, self._text(row.get("symbol")), opportunity, grade, risk_level,
            eligible, values["ltp"], values["bid"], values["ask"], spread, spread_pct, values["oi"],
            values["oi_change"], values["volume"], iv, values["delta"], values["gamma"], values["theta"],
            values["vega"], moneyness, distance, distance_pct, dte, liquidity, spread_score, oi_volume,
            greeks, iv_score, _clamp(m_score), direction, expiry_score, risk, tuple(dict.fromkeys(positives)),
            tuple(dict.fromkeys(warnings)), tuple(dict.fromkeys(reject)), tuple(dict.fromkeys(flags)), explanation)

    def _direction_score(self, side: str, context: DecisionContext) -> float:
        preferred = self._preferred_direction(str(getattr(context.institutional_evidence, "bias", "UNAVAILABLE")).upper())
        score = 50.0 if preferred in {"NEUTRAL", "CONFLICTED", "UNAVAILABLE"} else (85.0 if preferred == side else 25.0)
        state = str(getattr(context.positioning_intelligence, "dominant_state", "")).upper()
        bullish = state in {"LONG_BUILDUP", "SHORT_COVERING", "CALL_BUYING", "PUT_WRITING"}
        bearish = state in {"SHORT_BUILDUP", "LONG_UNWINDING", "PUT_BUYING", "CALL_WRITING"}
        if (side == "CE" and bullish) or (side == "PE" and bearish): score += 10
        elif bullish or bearish: score -= 10
        return _clamp(score)

    @staticmethod
    def _moneyness(side: str, pct: float, distance: float, cfg: TradeOpportunityRankingSettings) -> str:
        if pct <= .35: return "ATM"
        itm = (side == "CE" and distance < 0) or (side == "PE" and distance > 0)
        if itm: return "DEEP_ITM" if pct >= cfg.deep_itm_percent else "ITM"
        return "DEEP_OTM" if pct >= cfg.deep_otm_percent else "OTM"

    @staticmethod
    def _expiry(value: Any) -> tuple[object | None, int | None]:
        if value is None or str(value).strip() == "": return None, None
        try:
            parsed = pd.to_datetime(value, errors="raise").date()
            return value, (parsed - datetime.now(timezone.utc).date()).days
        except (TypeError, ValueError, OverflowError): return None, None

    @staticmethod
    def _preferred_direction(bias: str) -> str:
        if bias in {"BULLISH", "CE", "UP"}: return "CE"
        if bias in {"BEARISH", "PE", "DOWN"}: return "PE"
        if bias in {"NEUTRAL", "BALANCED"}: return "NEUTRAL"
        if bias in {"CONFLICTED", "MIXED"}: return "CONFLICTED"
        return "UNAVAILABLE"

    def _best_overall(self, ce: tuple[OptionOpportunity, ...], pe: tuple[OptionOpportunity, ...], preferred: str, cfg: TradeOpportunityRankingSettings) -> OptionOpportunity | None:
        if preferred in {"CONFLICTED", "UNAVAILABLE"}: return None
        pool = ce if preferred == "CE" else pe if preferred == "PE" else ce + pe
        eligible = [x for x in pool if x.opportunity_score >= cfg.minimum_best_overall_score and not any("extreme" in w.lower() or "severe" in w.lower() for w in x.warnings)]
        return min(eligible, key=self._sort_key) if eligible else None

    @staticmethod
    def _sort_key(item: OptionOpportunity) -> tuple[Any, ...]:
        return (-item.opportunity_score, -item.liquidity_score, -item.spread_quality_score,
                abs(item.distance_from_spot or 0), item.strike, str(item.expiry), item.symbol or "")

    def _rank_explanations(self, items: tuple[OptionOpportunity, ...]) -> tuple[OptionOpportunity, ...]:
        return tuple(replace(item, explanation=item.explanation + f" It ranks #{rank} on the {item.option_type} list after deterministic liquidity, spread and ATM-distance tie-breakers.") for rank, item in enumerate(items, 1))

    @staticmethod
    def _explanation(strike: float, side: str, positives: list[str], warnings: list[str], eligible: bool, reject: list[str]) -> str:
        if not eligible: return f"{strike:g} {side} is rejected because " + "; ".join(reject) + "."
        strengths = ", ".join(positives[:4]) or "available inputs provide only moderate support"
        warning = warnings[0] if warnings else "No material contract-level warning is present"
        return f"{strike:g} {side} is ranked because {strengths}. {warning}."

    def _grade(self, score: float, cfg: TradeOpportunityRankingSettings) -> str:
        return next((grade for threshold, grade in cfg.grade_thresholds if score >= threshold), "REJECTED")

    @staticmethod
    def _pick(row: Mapping[str, Any], aliases: tuple[str, ...]) -> Any:
        return next((row[key] for key in aliases if key in row and not pd.isna(row[key])), None)

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None or isinstance(value, bool): return None
        try:
            number = float(value)
            return number if pd.notna(number) else None
        except (TypeError, ValueError, OverflowError): return None

    @staticmethod
    def _text(value: Any) -> str | None:
        return None if value is None or pd.isna(value) or not str(value).strip() else str(value)

    @staticmethod
    def _reason_counts(rejected: list[OptionOpportunity]) -> tuple[tuple[str, int], ...]:
        counts = Counter(reason for item in rejected for reason in item.rejection_reasons)
        return tuple(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))

    @staticmethod
    def _malformed_rejection() -> OptionOpportunity:
        return OptionOpportunity("UNAVAILABLE", 0, None, None, 0, "REJECTED", "UNAVAILABLE", False,
            None, None, None, None, None, None, None, None, None, None, None, None, None,
            "UNKNOWN", None, None, None, 0, 0, 0, 0, 0, 0, 0, 0, 0, (), (), ("Malformed option row",),
            ("OPTION_ROWS_INVALID",), "The option row is rejected because its contract identity is malformed.")

    @staticmethod
    def _blocked(reason: str, preferred: str, bias: str, score: float, validation_state: str, flag: str = "RANKING_GATE_FAILED") -> TradeOpportunityRanking:
        return TradeOpportunityRanking("NOT_ELIGIBLE", False, reason, preferred, bias, score, validation_state,
            (), (), 0, 0, None, None, None, (flag, "RANKING_GATE_FAILED"), (reason,),
            f"Trade opportunity ranking is unavailable. {reason}")
