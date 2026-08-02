"""Trader-facing review models built only from frozen Market Lake records.

Factual future movement is joined after the stored decision has been loaded.  It
never changes that decision and is deliberately not described as trade P&L.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Sequence
import csv
import io
import json

from .market_lake import DatasetManifest, HistoricalIntelligenceRecord, HistoricalOutcomeRecord

TRIGGER_STATUSES = ("PASS", "PARTIAL", "FAIL", "UNAVAILABLE")
RESULT_CLASSIFICATIONS = ("FAVOURABLE", "UNFAVOURABLE", "INCONCLUSIVE", "NOT_EVALUABLE", "AVOIDED", "MISSED_OPPORTUNITY")
NAVIGATION_REGISTRY: Mapping[str, str] = {key: label for key, label in (
    ("market-structure", "Market Structure"), ("price-volume", "Price & Volume"),
    ("positioning", "Positioning"), ("compression", "Compression / Release"),
    ("manipulation", "Manipulation Safety"), ("manipulation.false-breakout", "False Breakout"),
    ("manipulation.false-breakdown", "False Breakdown"), ("manipulation.bull-trap", "Bull Trap"),
    ("manipulation.bear-trap", "Bear Trap"), ("institutional-evidence", "Institutional Evidence"),
    ("decision-confidence", "Decision Confidence"), ("decision-validation", "Validation"),
    ("trade-ranking", "Trade Ranking"), ("option-data-coverage", "Option Data Coverage"),
    ("historical-outcome", "Historical Outcome"),
)}


@dataclass(frozen=True)
class HistoricalTradeReviewSettings:
    historical_trade_review_enabled: bool = True
    historical_outcome_default_horizon: int = 15
    favourable_move_threshold_points: float = 20.0
    unfavourable_move_threshold_points: float = 20.0
    inconclusive_band_points: float = 10.0
    wait_avoided_threshold_points: float = 10.0
    wait_missed_opportunity_threshold_points: float = 20.0
    trigger_registry: tuple[str, ...] = ("market-structure", "price-volume", "positioning", "compression", "manipulation", "institutional-evidence", "decision-confidence", "decision-validation", "trade-ranking", "option-data-coverage")
    navigation_registry: tuple[str, ...] = tuple(NAVIGATION_REGISTRY)
    historical_trade_page_size: int = 50
    historical_trade_export_enabled: bool = True
    historical_option_download_enabled: bool = True
    derived_option_chain_enabled: bool = True
    live_market_lake_capture_enabled: bool = True
    live_capture_cadence_minutes: int = 5
    after_market_finalization_enabled: bool = True
    normal_ui_json_disabled: bool = True
    advanced_diagnostics_enabled: bool = True


@dataclass(frozen=True)
class TriggerCheckResult:
    trigger_id: str
    display_name: str
    status: str
    evidence: tuple[str, ...]
    impact: str
    missing_requirement: str | None
    fix_required: str | None
    analysis_target: str
    quality_flags: tuple[str, ...] = ()
    stored_value: str = "unavailable"
    rule_applied: str = "No rule could be evaluated"


@dataclass(frozen=True)
class HistoricalTradeReview:
    record_id: str; analysis_timestamp: datetime; trading_date: date
    recommendation: str; recommended_side: str; best_contract: str | None
    decision_confidence: float | None; confidence_grade: str | None
    trigger_results: tuple[TriggerCheckResult, ...]; trigger_pass_count: int; trigger_total_count: int; trigger_summary: str
    outcome_classification: str; outcome_reason: str
    change_5m: float | None; change_15m: float | None; change_30m: float | None; change_eod: float | None
    mfe: float | None; mae: float | None
    primary_success_reason: str | None; primary_failure_reason: str | None
    blockers: tuple[str, ...]; missing_confirmations: tuple[str, ...]
    replay_completeness: str; option_data_status: str; quality_flags: tuple[str, ...]
    analysis_targets: tuple[str, ...]
    positioning_state: str | None = None; compression_state: str | None = None
    manipulation_state: str | None = None; institutional_bias: str | None = None
    ranking_eligibility: bool = False; frozen_values: Mapping[str, Any] = field(default_factory=dict, compare=True)


def _get(values: Mapping[str, Any], path: str, default: Any = None) -> Any:
    current: Any = values
    for name in path.split("."):
        current = current.get(name) if isinstance(current, Mapping) else None
        if current is None: return default
    return current


def _truth(values: Mapping[str, Any], *paths: str) -> bool:
    return any(_get(values, path) is True or str(_get(values, path)).upper() in {"TRUE", "PASS", "ELIGIBLE", "CONFIRMED", "BULLISH", "BEARISH", "RELEASING"} for path in paths)


def classify_result(recommendation: str, outcome: HistoricalOutcomeRecord | None,
                    settings: HistoricalTradeReviewSettings = HistoricalTradeReviewSettings(), *,
                    adverse_or_manipulative: bool = False) -> tuple[str, str]:
    if outcome is None or not outcome.future_data_available:
        return "NOT_EVALUABLE", "Required future candles are unavailable."
    changes = [value for _, value in outcome.horizon_point_changes if value is not None]
    if not changes:
        return "NOT_EVALUABLE", "Required factual horizon movement is unavailable."
    move = dict(outcome.horizon_point_changes).get(settings.historical_outcome_default_horizon)
    move = move if move is not None else changes[-1]
    if recommendation == "WAIT":
        material = max(map(abs, changes))
        if material >= settings.wait_missed_opportunity_threshold_points and not adverse_or_manipulative:
            return "MISSED_OPPORTUNITY", "A material clean directional movement followed WAIT."
        return "AVOIDED", "WAIT avoided an unconfirmed or adverse setup without clean follow-through."
    direction = 1 if recommendation == "BUY CE" else -1 if recommendation == "BUY PE" else 0
    if not direction: return "NOT_EVALUABLE", "Stored recommendation is not evaluable."
    directed = direction * move
    if directed >= settings.favourable_move_threshold_points:
        return "FAVOURABLE", "Factual underlying movement met the configured favourable directional threshold."
    if directed <= -settings.unfavourable_move_threshold_points:
        return "UNFAVOURABLE", "Factual underlying movement met the configured adverse directional threshold."
    return "INCONCLUSIVE", "Factual movement was small, mixed, or below configured directional thresholds."


def build_trigger_checklist(record: HistoricalIntelligenceRecord, option_complete: bool) -> tuple[TriggerCheckResult, ...]:
    v = record.values
    direction = 1 if record.recommendation == "BUY CE" else -1 if record.recommendation == "BUY PE" else 0
    def directional(value: Any, *, positive: tuple[str, ...], negative: tuple[str, ...]) -> str:
        text = str(value or "").upper().replace("-", "_").replace(" ", "_")
        if not text: return "UNAVAILABLE"
        aligned = any(token in text for token in (positive if direction > 0 else negative))
        opposed = any(token in text for token in (negative if direction > 0 else positive))
        if direction == 0: return "PARTIAL"
        return "PASS" if aligned and not opposed else "FAIL" if opposed else "PARTIAL"
    structure_value = _get(v, "market_regime.regime", record.market_bias)
    positioning_value = record.positioning_state or _get(v, "positioning_intelligence.state")
    institution_value = _get(v, "institutional_evidence.bias", record.market_bias)
    structure_status = directional(structure_value, positive=("BULL",), negative=("BEAR",))
    positioning_status = directional(positioning_value, positive=("LONG_BUILDUP", "LONG_BUILD_UP", "PUT_WRITING"), negative=("SHORT_BUILDUP", "SHORT_BUILD_UP", "CALL_WRITING"))
    institution_status = directional(institution_value, positive=("BULL",), negative=("BEAR",))
    compression = _get(v, "compression_intelligence")
    releasing = _truth(v, "compression_intelligence.releasing", "compression_intelligence.release_ready")
    expanding = _truth(v, "compression_intelligence.expansion", "compression_intelligence.expanding")
    release_direction = _get(v, "compression_intelligence.release_direction", _get(v, "compression_intelligence.direction"))
    compression_status = "UNAVAILABLE" if compression is None else directional(release_direction, positive=("UP", "BULL", "CE"), negative=("DOWN", "BEAR", "PE")) if (releasing or expanding) else "PARTIAL"
    unavailable = lambda key: _get(v, key) is None
    manipulation = any(_truth(v, f"manipulation_intelligence.{name}") for name in ("false_breakout", "false_breakdown", "bull_trap", "bear_trap", "liquidity_sweep"))
    target = "manipulation.false-breakout" if _truth(v, "manipulation_intelligence.false_breakout") else "manipulation"
    rows = [
        ("market-structure", "Market Structure", structure_status, (f"Stored structure: {structure_value or 'unavailable'}",), "Supports frozen direction" if structure_status == "PASS" else "Does not support frozen direction", "Stored market structure", "Require structure aligned with the frozen recommendation"),
        ("price-volume", "Price & Volume", "UNAVAILABLE" if unavailable("volume_structure") else ("PASS" if _truth(v, "volume_structure.confirmed_expansion", "volume_structure.price_up_volume_up") else "PARTIAL"), (f"Volume behaviour: {_get(v, 'volume_structure.behaviour', 'unavailable')}",), "Confirms price participation", "Confirmed volume", "Wait for volume confirmation"),
        ("positioning", "Positioning", positioning_status, (f"Stored state: {positioning_value or 'unavailable'}",), "Supports frozen direction" if positioning_status == "PASS" else "Contradicts or does not confirm frozen direction", "Stored positioning", "Require aligned positioning"),
        ("compression", "Compression / Release", compression_status, (f"Compression: {record.compression_state or 'present' if compression is not None else 'unavailable'}; release ready: {releasing}; expansion: {expanding}; release direction: {release_direction or 'unavailable'}",), "Release direction supports frozen direction" if compression_status == "PASS" else "Compression alone does not confirm a directional release", "Directional release evidence", "Require release readiness and a stored aligned direction"),
        (target, "Manipulation Safety", "FAIL" if manipulation else ("UNAVAILABLE" if unavailable("manipulation_intelligence") else "PASS"), tuple(name.replace('_',' ').title()+" detected" for name in ("false_breakout", "false_breakdown", "bull_trap", "bear_trap", "liquidity_sweep") if _truth(v, f"manipulation_intelligence.{name}")) or ("No stored manipulation flag",), "Directional entry blocked" if manipulation else "Checks trap risk", None, "Wait for genuine acceptance with confirming volume" if manipulation else None),
        ("institutional-evidence", "Institutional Evidence", institution_status, (f"Stored bias: {institution_value or 'unavailable'}",), "Supports frozen direction" if institution_status == "PASS" else "Contradicts or does not confirm frozen direction", "Stored institutional evidence", "Require evidence aligned with the frozen recommendation"),
        ("decision-confidence", "Decision Confidence", "UNAVAILABLE" if record.decision_confidence is None else ("PASS" if record.decision_confidence >= 70 else "PARTIAL"), (f"Frozen score: {record.decision_confidence if record.decision_confidence is not None else 'unavailable'}",), "Measures stored evidence strength", "Frozen confidence", "Require stronger confirmations"),
        ("decision-validation", "Validation", "FAIL" if record.blockers else ("PARTIAL" if record.missing_confirmations else "PASS"), tuple(record.blockers or record.missing_confirmations or ("No stored blocker",)), "Controls eligibility", None, "Resolve stored blockers" if record.blockers else None),
        ("trade-ranking", "Trade Ranking", "PASS" if record.ranking_eligibility else "PARTIAL", ("Ranking eligible" if record.ranking_eligibility else "Ranking unavailable or ineligible",), "Checks contract ranking readiness", None, "Require ranking eligibility" if not record.ranking_eligibility else None),
        ("option-data-coverage", "Option Liquidity / Data Completeness", "PASS" if option_complete else "UNAVAILABLE", ("Historical contract candles stored",) if option_complete else ("Historical bid/ask unavailable", "Historical IV unavailable", "Historical Greeks unavailable"), "Contract-level execution quality can be verified" if option_complete else "Contract-level execution quality cannot be verified", "Historical option data" if not option_complete else None, "Download officially supported historical option candles" if not option_complete else None),
    ]
    rules = {
        "market-structure": f"{record.recommendation}: bullish for BUY CE; bearish for BUY PE; WAIT is non-directional",
        "positioning": f"{record.recommendation}: LONG_BUILDUP/PUT_WRITING support CE; SHORT_BUILDUP/CALL_WRITING support PE",
        "compression": "PASS requires release readiness or expansion plus an aligned stored release direction",
        "institutional-evidence": f"Institutional bias must align with {record.recommendation}",
    }
    return tuple(TriggerCheckResult(key, name, status, evidence, impact, missing, fix, key,
        () if status != "UNAVAILABLE" else ("DATA_UNAVAILABLE",), "; ".join(evidence),
        rules.get(key, f"Stored {name.lower()} rule evaluated without future outcome data"))
        for key,name,status,evidence,impact,missing,fix in rows)


def trigger_summary(triggers: Sequence[TriggerCheckResult]) -> str:
    priority = ("FAIL", "UNAVAILABLE", "PARTIAL")
    for status in priority:
        found = next((t for t in triggers if t.status == status), None)
        if found: return f"{status} — {found.display_name.replace(' / Data Completeness','')}"
    passed = sum(t.status == "PASS" for t in triggers)
    return f"{passed}/{len(triggers)} PASS"


def _reason(record: HistoricalIntelligenceRecord, classification: str, option_complete: bool) -> tuple[str | None, str | None]:
    v = record.values
    if classification == "FAVOURABLE":
        if _truth(v, "volume_structure.confirmed_expansion"): return "Volume confirmed the move", None
        if "Long Build" in (record.positioning_state or ""): return "Long build-up continued", None
        if record.ranking_eligibility: return "Ranking was eligible", None
    if classification in {"UNFAVOURABLE", "AVOIDED", "NOT_EVALUABLE"}:
        for key, label in (("false_breakout","False breakout"),("false_breakdown","False breakdown"),("bull_trap","Bull trap"),("bear_trap","Bear trap")):
            if _truth(v, f"manipulation_intelligence.{key}"): return None, label
        if _get(v, "volume_structure.confirmed_expansion") is False: return None, "Weak volume confirmation"
        if not option_complete: return None, "Option execution quality could not be verified"
        if record.blockers: return None, record.blockers[0]
    return None, None


def build_trade_reviews(records: Sequence[HistoricalIntelligenceRecord], outcomes: Sequence[HistoricalOutcomeRecord],
                        option_dates: Sequence[date] = (), settings: HistoricalTradeReviewSettings = HistoricalTradeReviewSettings()) -> tuple[HistoricalTradeReview, ...]:
    by_id = {o.intelligence_record_id: o for o in outcomes}; option_days = set(option_dates); result = []
    for record in records:
        outcome = by_id.get(record.record_id); option_complete = record.trading_date in option_days
        adverse = any(_truth(record.values, f"manipulation_intelligence.{x}") for x in ("false_breakout","false_breakdown","bull_trap","bear_trap","liquidity_sweep"))
        classification, outcome_reason = classify_result(record.recommendation, outcome, settings, adverse_or_manipulative=adverse)
        triggers = build_trigger_checklist(record, option_complete); success, failure = _reason(record, classification, option_complete)
        changes = dict(outcome.horizon_point_changes) if outcome else {}
        ranking = _get(record.values, "trade_opportunity_ranking", {})
        side = "CE" if record.recommendation == "BUY CE" else "PE" if record.recommendation == "BUY PE" else "WAIT"
        contract = None
        if isinstance(ranking, Mapping) and side in {"CE","PE"}:
            best = ranking.get("top_"+side.lower()) or {}; strike = best.get("strike") if isinstance(best, Mapping) else None
            contract = f"{strike} {side}" if strike is not None else None
        result.append(HistoricalTradeReview(record.record_id, record.analysis_timestamp, record.trading_date,
            record.recommendation, side, contract, record.decision_confidence, record.decision_confidence_grade,
            triggers, sum(t.status == "PASS" for t in triggers), len(triggers), trigger_summary(triggers), classification,
            outcome_reason, changes.get(5), changes.get(15), changes.get(30), None if not outcome or outcome.end_of_session_price is None else outcome.end_of_session_price-outcome.reference_price,
            None if not outcome else outcome.maximum_favourable_excursion, None if not outcome else outcome.maximum_adverse_excursion,
            success, failure, record.blockers, record.missing_confirmations, record.replay_completeness,
            "COMPLETE" if option_complete else "UNAVAILABLE", tuple(sorted(set(record.quality_flags + (() if option_complete else ("OPTIONS_UNAVAILABLE",))))),
            tuple(t.analysis_target for t in triggers), record.positioning_state, record.compression_state, record.manipulation_state,
            record.market_bias, record.ranking_eligibility, dict(record.values)))
    return tuple(sorted(result, key=lambda r: r.analysis_timestamp))


@dataclass(frozen=True)
class TradeReviewFilters:
    start_date: date | None = None; end_date: date | None = None; decisions: tuple[str, ...] = ()
    classifications: tuple[str, ...] = (); minimum_confidence: float | None = None; maximum_confidence: float | None = None
    trigger_status: str | None = None; failed_trigger: str | None = None; positioning_state: str | None = None
    compression_state: str | None = None; manipulation_state: str | None = None; institutional_bias: str | None = None
    ranking_eligibility: bool | None = None; replay_completeness: str | None = None; option_data_status: str | None = None
    contract_search: str = ""; reason_search: str = ""


def filter_trade_reviews(reviews: Sequence[HistoricalTradeReview], filters: TradeReviewFilters) -> tuple[HistoricalTradeReview, ...]:
    def match(r: HistoricalTradeReview) -> bool:
        reason = " ".join(filter(None, (r.primary_success_reason, r.primary_failure_reason, r.outcome_reason))).lower()
        return all((filters.start_date is None or r.trading_date >= filters.start_date,
            filters.end_date is None or r.trading_date <= filters.end_date, not filters.decisions or r.recommendation in filters.decisions,
            not filters.classifications or r.outcome_classification in filters.classifications,
            filters.minimum_confidence is None or r.decision_confidence is not None and r.decision_confidence >= filters.minimum_confidence,
            filters.maximum_confidence is None or r.decision_confidence is not None and r.decision_confidence <= filters.maximum_confidence,
            filters.trigger_status is None or any(t.status == filters.trigger_status for t in r.trigger_results),
            filters.failed_trigger is None or any(t.display_name == filters.failed_trigger and t.status != "PASS" for t in r.trigger_results),
            filters.positioning_state is None or r.positioning_state == filters.positioning_state,
            filters.compression_state is None or r.compression_state == filters.compression_state,
            filters.manipulation_state is None or r.manipulation_state == filters.manipulation_state,
            filters.institutional_bias is None or r.institutional_bias == filters.institutional_bias,
            filters.ranking_eligibility is None or r.ranking_eligibility == filters.ranking_eligibility,
            filters.replay_completeness is None or r.replay_completeness == filters.replay_completeness,
            filters.option_data_status is None or r.option_data_status == filters.option_data_status,
            filters.contract_search.lower() in (r.best_contract or "").lower(), filters.reason_search.lower() in reason))
    return tuple(r for r in sorted(reviews, key=lambda x: x.analysis_timestamp) if match(r))


def trade_table_rows(reviews: Sequence[HistoricalTradeReview]) -> tuple[Mapping[str, Any], ...]:
    return tuple({"Record ID": r.record_id, "Date": r.trading_date, "Time": r.analysis_timestamp.strftime("%H:%M:%S"), "Decision": r.recommendation,
        "Recommended Side": r.recommended_side, "Best Contract": r.best_contract or "—", "Decision Confidence": r.decision_confidence,
        "Confidence Grade": r.confidence_grade or "—", "Trigger Checklist Summary": r.trigger_summary, "Result Classification": r.outcome_classification,
        "5m Outcome": r.change_5m, "15m Outcome": r.change_15m, "30m Outcome": r.change_30m, "EOD Outcome": r.change_eod,
        "MFE": r.mfe, "MAE": r.mae, "Primary Reason": r.primary_success_reason or r.outcome_reason,
        "Primary Failure / Blocker": r.primary_failure_reason or (r.blockers[0] if r.blockers else "—"),
        "Replay Completeness": r.replay_completeness, "Option Data Status": r.option_data_status, "View Details": False} for r in reviews)


def export_csv(reviews: Sequence[HistoricalTradeReview]) -> bytes:
    rows = trade_table_rows(reviews)
    if not rows: return b""
    stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    return stream.getvalue().encode()


def export_json(reviews: Sequence[HistoricalTradeReview]) -> bytes:
    return json.dumps([asdict(r) for r in reviews], default=str, sort_keys=True).encode()


@dataclass(frozen=True)
class CoverageRow:
    trading_date: date; underlying_candles: bool; option_contracts: bool; intelligence: bool; outcomes: bool
    replay_completeness: str; status: str; action_required: str
    session_classification: str = "EXPECTED_WEEKDAY"


def build_coverage_rows(manifest: DatasetManifest | None, expected_dates: Sequence[date]) -> tuple[CoverageRow, ...]:
    if manifest is None:
        return tuple(CoverageRow(d, False, False, False, False, "UNAVAILABLE", "RAW_MISSING", "Download Missing Underlying Data") for d in expected_dates)
    raw, options, intel, outcomes, failed, no_data = map(set, (manifest.available_dates, manifest.option_dates, manifest.intelligence_dates, manifest.outcome_dates, manifest.failed_dates, manifest.no_data_dates))
    rows=[]
    for d in expected_dates:
        if d in no_data: status, action = "NOT_TRADING_SESSION", "None"
        elif d in failed: status, action = "FAILED", "Retry Failed Dates"
        elif d not in raw: status, action = "RAW_MISSING", "Download Missing Underlying Data"
        elif d not in intel: status, action = "INTELLIGENCE_MISSING", "Build Missing Intelligence"
        elif d not in outcomes: status, action = "OUTCOMES_MISSING", "Build Missing Outcomes"
        elif d not in options: status, action = "PARTIAL_OPTIONS", "Download Historical Options"
        else: status, action = "COMPLETE", "None"
        rows.append(CoverageRow(d,d in raw,d in options,d in intel,d in outcomes,"FULL_REPLAY" if d in options else "PARTIAL_OPTION_REPLAY",status,action,
            "NOT_TRADING_SESSION" if d in no_data else "CONFIRMED_TRADING_SESSION" if d in raw else "EXPECTED_WEEKDAY"))
    return tuple(rows)
