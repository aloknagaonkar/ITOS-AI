"""Deterministic, advisory similarity and pattern discovery over frozen index rows.

Outcomes are deliberately attached only after all similarity scores have been
calculated.  This module neither imports nor executes ``DecisionPipeline``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from io import BytesIO
from typing import Any, Iterable, Mapping, Sequence
import csv
import json
import math

from .historical_intelligence_index import (
    HistoricalIndexQuery, IndexedHistoricalIntelligence, MarketFingerprint,
)

SIMILARITY_QUALITY_FLAGS = frozenset({
    "SOURCE_FINGERPRINT_UNAVAILABLE", "SOURCE_CONTEXT_UNAVAILABLE", "INDEX_UNAVAILABLE",
    "INDEX_STALE", "INDEX_VERSION_MISMATCH", "INSUFFICIENT_CANDIDATES",
    "INSUFFICIENT_MATCHES", "LOW_SIMILARITY_COVERAGE", "SEMANTIC_DATA_INCOMPLETE",
    "NUMERIC_DATA_INCOMPLETE", "CONTEXT_DATA_INCOMPLETE", "OUTCOME_COVERAGE_LOW",
    "LOW_SAMPLE_SIZE", "LOW_SAMPLE_PATTERN", "PATTERN_SUPPORT_INSUFFICIENT",
    "OPTION_DATA_INCOMPLETE", "CROSS_VERSION_MATCH_BLOCKED", "SOURCE_TRADE_EXCLUDED",
    "SAME_DAY_DUPLICATES_REDUCED",
})


@dataclass(frozen=True)
class HistoricalSimilaritySettings:
    historical_similarity_enabled: bool = True
    similarity_algorithm_version: str = "similarity-v1"
    context_fingerprint_version: str = "context-v1"
    similarity_weight_profile_version: str = "weights-v1"
    pattern_registry_version: str = "patterns-v1"
    similarity_semantic_weight: float = .45
    similarity_numeric_weight: float = .35
    similarity_context_weight: float = .20
    similarity_minimum_score: float = 0.0
    similarity_very_high_threshold: float = .90
    similarity_high_threshold: float = .80
    similarity_moderate_threshold: float = .65
    similarity_low_threshold: float = .50
    similarity_candidate_limit: int = 1000
    similarity_result_limit: int = 25
    similarity_query_maximum_limit: int = 1000
    semantic_dimension_weights: tuple[tuple[str, float], ...] = (
        ("POS", 1.5), ("MANIP", 1.4), ("INST", 1.4), ("COMP", 1.25),
        ("RELEASE", 1.25), ("MS", 1.2), ("VALID", 1.1), ("RANK", 1.1),
        ("REC", 1.0),
    )
    numeric_feature_weights: tuple[tuple[str, float], ...] = ()
    context_dimension_weights: tuple[tuple[str, float], ...] = ()
    similarity_minimum_semantic_coverage: float = .25
    similarity_minimum_numeric_coverage: float = .25
    similarity_minimum_context_coverage: float = .25
    similarity_minimum_overall_coverage: float = .40
    similarity_same_instrument_default: bool = True
    similarity_same_recommendation_default: bool = False
    similarity_exclude_same_date_default: bool = False
    similarity_maximum_matches_per_date: int = 5
    similarity_minimum_minutes_between_same_day_matches: int = 0
    similarity_semantic_deduplication_enabled: bool = False
    pattern_discovery_enabled: bool = True
    pattern_minimum_occurrences: int = 3
    pattern_minimum_evaluable_count: int = 2
    pattern_minimum_average_similarity: float = .65
    pattern_maximum_results: int = 20
    similarity_outcome_summary_enabled: bool = True
    similarity_live_advisory_enabled: bool = True
    similarity_export_enabled: bool = True
    similarity_cache_enabled: bool = False
    similarity_cache_version: str = "cache-v1"


@dataclass(frozen=True)
class SimilarityRequest:
    source_trade_id: str | None = None
    source_fingerprint: MarketFingerprint | None = None
    instrument_key: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    engine_version: str | None = None
    fingerprint_version: str | None = None
    same_instrument_only: bool = True
    same_recommendation_only: bool = False
    exclude_same_trading_date: bool = False
    exclude_source_trade: bool = True
    maximum_candidates: int = 1000
    maximum_results: int = 25
    minimum_overall_score: float = 0.0
    semantic_weight: float = .45
    numeric_weight: float = .35
    context_weight: float = .20
    include_opposite_setups: bool = False
    include_outcome_summary: bool = True
    include_pattern_summary: bool = True
    quality_flags: tuple[str, ...] = ()

    def validate(self, maximum_limit: int = 1000) -> "SimilarityRequest":
        if not self.source_trade_id and self.source_fingerprint is None:
            raise ValueError("one source trade ID or fingerprint is required")
        if self.source_trade_id and self.source_fingerprint is not None:
            raise ValueError("provide one source, not both")
        weights = (self.semantic_weight, self.numeric_weight, self.context_weight)
        if any(not math.isfinite(w) or w < 0 for w in weights) or sum(weights) <= 0:
            raise ValueError("similarity weights must be finite, non-negative, and non-zero")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must not follow end_date")
        if not 1 <= self.maximum_candidates <= maximum_limit:
            raise ValueError("invalid candidate limit")
        if not 1 <= self.maximum_results <= min(self.maximum_candidates, maximum_limit):
            raise ValueError("invalid result limit")
        if not math.isfinite(self.minimum_overall_score) or not 0 <= self.minimum_overall_score <= 1:
            raise ValueError("minimum score must be between zero and one")
        return self

    @property
    def normalized_weights(self) -> tuple[float, float, float]:
        total = self.semantic_weight + self.numeric_weight + self.context_weight
        return tuple(w / total for w in (self.semantic_weight, self.numeric_weight, self.context_weight))


@dataclass(frozen=True)
class SemanticSimilarity:
    score: float
    matched_tokens: tuple[str, ...]
    differing_tokens: tuple[tuple[str, str | None, str | None], ...]
    missing_source_tokens: tuple[str, ...]
    missing_candidate_tokens: tuple[str, ...]
    compared_dimension_count: int
    matched_dimension_count: int
    coverage: float
    quality_flags: tuple[str, ...] = ()
    explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class NumericFeatureComparison:
    feature_name: str; source_value: float | None; candidate_value: float | None
    distance: float | None; similarity: float | None; weight: float; included: bool; explanation: str


@dataclass(frozen=True)
class NumericSimilarity:
    score: float | None; feature_coverage: float
    comparisons: tuple[NumericFeatureComparison, ...]
    missing_source_features: tuple[str, ...]; missing_candidate_features: tuple[str, ...]
    quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextFingerprint:
    context_version: str; analysis_timestamp: datetime; session_phase: str
    minutes_from_open: int | None; minutes_to_close: int | None; day_of_week: str
    is_expiry_day: bool | None; days_to_expiry: int | None; gap_context: str
    gap_percent_normalized: float | None; intraday_regime: str; volatility_regime: str
    trend_range_context: str; opening_range_context: str; previous_day_context: str
    data_coverage: float; semantic_tokens: tuple[str, ...]
    numeric_features: tuple[tuple[str, float | None], ...]
    quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextSimilarity:
    score: float | None; semantic_score: float | None; numeric_score: float | None; coverage: float
    matched_context: tuple[str, ...]; differing_context: tuple[str, ...]; missing_context: tuple[str, ...]
    quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimilarityScoreBreakdown:
    semantic_score: float | None; numeric_score: float | None; context_score: float | None
    semantic_coverage: float; numeric_coverage: float; context_coverage: float
    semantic_weight: float; numeric_weight: float; context_weight: float
    effective_semantic_weight: float; effective_numeric_weight: float; effective_context_weight: float
    overall_score: float; overall_coverage: float; confidence_band: str
    quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimilarityDifference:
    dimension: str; source_value: str | float | None; candidate_value: str | float | None
    importance: str; direction: str; impact: str; analysis_target: str | None


@dataclass(frozen=True)
class DifferenceAnalysis:
    shared_evidence: tuple[str, ...]; important_differences: tuple[SimilarityDifference, ...]
    missing_evidence: tuple[str, ...]; contradictory_evidence: tuple[str, ...]
    quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalSimilarityMatch:
    source_trade_id: str | None; candidate_trade_id: str; candidate_analysis_timestamp: datetime
    instrument_key: str; recommendation: str; decision_confidence: float | None
    score_breakdown: SimilarityScoreBreakdown; semantic_similarity: SemanticSimilarity
    numeric_similarity: NumericSimilarity; context_similarity: ContextSimilarity
    difference_analysis: DifferenceAnalysis; outcome_classification: str | None = None
    change_5m: float | None = None; change_15m: float | None = None; change_30m: float | None = None
    change_eod: float | None = None; mfe: float | None = None; mae: float | None = None
    replay_completeness: str = "UNKNOWN"; option_data_status: str = "UNKNOWN"
    relationship_types: tuple[str, ...] = (); navigation_targets: tuple[str, ...] = ()
    semantic_tokens: tuple[str, ...] = (); context_tokens: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimilarityOutcomeSummary:
    match_count: int; evaluable_count: int; favourable_count: int; unfavourable_count: int
    inconclusive_count: int; avoided_count: int; missed_opportunity_count: int; not_evaluable_count: int
    favourable_percentage: float | None; unfavourable_percentage: float | None
    average_5m_change: float | None; average_15m_change: float | None; average_30m_change: float | None
    average_eod_change: float | None; average_mfe: float | None; average_mae: float | None
    outcome_coverage: float; quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscoveredPattern:
    pattern_id: str; display_name: str; token_signature: tuple[str, ...]; context_signature: tuple[str, ...]
    occurrence_count: int; evaluable_count: int; common_recommendation: str | None; common_outcome: str | None
    average_confidence: float | None; average_similarity: float | None; average_15m_change: float | None
    average_30m_change: float | None; average_mfe: float | None; average_mae: float | None
    supporting_trade_ids: tuple[str, ...]; quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatternDiscoverySummary:
    pattern_count: int; patterns: tuple[DiscoveredPattern, ...]; most_common_pattern_id: str | None
    strongest_pattern_id: str | None; pattern_registry_version: str = "patterns-v1"
    quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


@dataclass(frozen=True)
class HistoricalSimilarityResult:
    request: SimilarityRequest; source_trade_id: str | None; source_fingerprint_version: str
    candidate_count: int; compared_count: int; result_count: int
    matches: tuple[HistoricalSimilarityMatch, ...]; opposite_matches: tuple[HistoricalSimilarityMatch, ...]
    very_high_count: int; high_count: int; moderate_count: int; low_count: int
    best_match_trade_id: str | None; best_match_score: float | None
    aggregate_outcomes: SimilarityOutcomeSummary | None; pattern_summary: PatternDiscoverySummary | None
    similarity_algorithm_version: str; context_fingerprint_version: str
    similarity_weight_profile_version: str; pattern_registry_version: str
    quality_flags: tuple[str, ...] = (); explanations: tuple[str, ...] = ()


def _clamp(value: float) -> float: return max(0.0, min(1.0, value))
def _token_map(tokens: Iterable[str]) -> dict[str, str]:
    return {p: v for token in tokens if "=" in token for p, v in (token.split("=", 1),)}
def _average(values: Iterable[float | None]) -> float | None:
    numbers = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return sum(numbers) / len(numbers) if numbers else None


def semantic_similarity(source: MarketFingerprint | Sequence[str], candidate: MarketFingerprint | Sequence[str],
                        weights: Mapping[str, float] | None = None) -> SemanticSimilarity:
    left = _token_map(source.semantic_tokens if isinstance(source, MarketFingerprint) else source)
    right = _token_map(candidate.semantic_tokens if isinstance(candidate, MarketFingerprint) else candidate)
    dimensions = sorted(set(left) | set(right)); configured = dict(weights or ())
    matched, differing, missing_left, missing_right = [], [], [], []
    numerator = denominator = available_weight = 0.0
    for dimension in dimensions:
        weight = max(0.0, float(configured.get(dimension, 1.0))); denominator += weight
        lv, rv = left.get(dimension), right.get(dimension)
        if lv in (None, "UNKNOWN"): missing_left.append(dimension); continue
        if rv in (None, "UNKNOWN"): missing_right.append(dimension); continue
        available_weight += weight
        if lv == rv: matched.append(f"{dimension}={lv}"); numerator += weight
        else: differing.append((dimension, lv, rv))
    coverage = available_weight / denominator if denominator else 0.0
    flags = ("SEMANTIC_DATA_INCOMPLETE",) if coverage < 1 else ()
    return SemanticSimilarity(_clamp(numerator / available_weight) if available_weight else 0.0,
        tuple(matched), tuple(differing), tuple(missing_left), tuple(missing_right),
        sum(1 for d in dimensions if d in left and d in right), len(matched), coverage, flags,
        (f"Compared {sum(1 for d in dimensions if d in left and d in right)} registered token families.",))


def numeric_similarity(source: MarketFingerprint | Mapping[str, float | None] | Sequence[tuple[str, float | None]],
                       candidate: MarketFingerprint | Mapping[str, float | None] | Sequence[tuple[str, float | None]],
                       weights: Mapping[str, float] | None = None) -> NumericSimilarity:
    def values(item):
        raw = item.numeric_features if isinstance(item, MarketFingerprint) else item
        return dict(raw)
    left, right, configured = values(source), values(candidate), dict(weights or ())
    names = sorted(set(left) | set(right)); comparisons=[]; missing_left=[]; missing_right=[]
    numerator=available=total=0.0
    for name in names:
        weight=max(0.0,float(configured.get(name,1.0))); total += weight
        lv,rv=left.get(name),right.get(name)
        valid=lambda v: v is not None and isinstance(v,(int,float)) and math.isfinite(v)
        if not valid(lv): missing_left.append(name)
        if not valid(rv): missing_right.append(name)
        included=valid(lv) and valid(rv)
        distance=abs(float(lv)-float(rv)) if included else None
        similarity=_clamp(1-distance) if distance is not None else None
        if included: numerator += similarity*weight; available += weight
        comparisons.append(NumericFeatureComparison(name,lv if valid(lv) else None,rv if valid(rv) else None,
            distance,similarity,weight,included,"Compared normalized registry feature." if included else "Feature unavailable; excluded, not zeroed."))
    coverage=available/total if total else 0.0
    flags=("NUMERIC_DATA_INCOMPLETE",) if coverage < 1 else ()
    return NumericSimilarity(_clamp(numerator/available) if available else None,coverage,tuple(comparisons),
        tuple(missing_left),tuple(missing_right),flags,(f"Numeric feature coverage is {coverage:.1%}.",))


def build_context_fingerprint(analysis_timestamp: datetime, *, expiry_date: date | None = None,
        opening_price: float | None = None, previous_close: float | None = None,
        intraday_regime: str = "UNKNOWN", volatility_regime: str = "UNKNOWN",
        trend_range_context: str = "UNKNOWN", opening_range_context: str = "UNKNOWN",
        previous_high: float | None = None, previous_low: float | None = None,
        current_price: float | None = None, version: str = "context-v1") -> ContextFingerprint:
    local=analysis_timestamp; current=local.time(); market_open=time(9,15); market_close=time(15,30)
    minutes=local.hour*60+local.minute; open_minutes=9*60+15; close_minutes=15*60+30
    if current < time(9,0): phase="PRE_OPEN"
    elif current < market_open or current > market_close: phase="OUTSIDE_SESSION"
    elif minutes < 10*60: phase="OPENING"
    elif minutes < 12*60: phase="MORNING"
    elif minutes < 13*60+30: phase="MIDDAY"
    elif minutes < 15*60: phase="AFTERNOON"
    else: phase="CLOSING"
    in_session=market_open <= current <= market_close
    from_open=minutes-open_minutes if in_session else None; to_close=close_minutes-minutes if in_session else None
    days=None if expiry_date is None else (expiry_date-local.date()).days
    expiry=None if expiry_date is None else days == 0
    gap=None if opening_price is None or previous_close in (None,0) else (opening_price-previous_close)/abs(previous_close)
    gap_context="UNKNOWN" if gap is None else "GAP_UP" if gap>.001 else "GAP_DOWN" if gap<-.001 else "FLAT_OPEN"
    previous="UNKNOWN"
    if current_price is not None and previous_high is not None and current_price>previous_high: previous="ABOVE_PREVIOUS_HIGH"
    elif current_price is not None and previous_low is not None and current_price<previous_low: previous="BELOW_PREVIOUS_LOW"
    elif None not in (current_price,previous_high,previous_low): previous="INSIDE_PREVIOUS_RANGE"
    semantic=(f"SESSION={phase}",f"GAP={gap_context}",f"INTRADAY={intraday_regime}",
              f"VOLATILITY={volatility_regime}",f"TREND_RANGE={trend_range_context}",
              f"OPENING_RANGE={opening_range_context}",f"PREVIOUS_DAY={previous}")
    numeric=(("minutes_from_open",None if from_open is None else _clamp(from_open/375)),
             ("minutes_to_close",None if to_close is None else _clamp(to_close/375)),
             ("days_to_expiry",None if days is None else _clamp(days/30)),
             ("gap_percent",None if gap is None else _clamp((gap+.1)/.2)))
    available=sum("UNKNOWN" not in t for t in semantic)+sum(v is not None for _,v in numeric)
    coverage=available/(len(semantic)+len(numeric)); flags=("CONTEXT_DATA_INCOMPLETE",) if coverage<1 else ()
    return ContextFingerprint(version,analysis_timestamp,phase,from_open,to_close,local.strftime("%A"),expiry,days,
        gap_context,None if gap is None else _clamp((gap+.1)/.2),intraday_regime,volatility_regime,
        trend_range_context,opening_range_context,previous,coverage,semantic,numeric,flags,
        ("Context uses values available at the frozen analysis timestamp only.",))


def context_similarity(source: ContextFingerprint | None, candidate: ContextFingerprint | None) -> ContextSimilarity:
    if source is None or candidate is None:
        return ContextSimilarity(None,None,None,0,(),(),("context",),("CONTEXT_DATA_INCOMPLETE",),("Context was unavailable and was not scored as zero.",))
    semantic=semantic_similarity(source.semantic_tokens,candidate.semantic_tokens)
    numeric=numeric_similarity(source.numeric_features,candidate.numeric_features)
    components=[v for v in (semantic.score,numeric.score) if v is not None]
    score=sum(components)/len(components) if components else None
    matched=semantic.matched_tokens; differing=tuple(f"{d}: {a} → {b}" for d,a,b in semantic.differing_tokens)
    missing=tuple(sorted(set(semantic.missing_source_tokens+semantic.missing_candidate_tokens+
        numeric.missing_source_features+numeric.missing_candidate_features)))
    coverage=(semantic.coverage+numeric.feature_coverage)/2
    flags=("CONTEXT_DATA_INCOMPLETE",) if coverage<1 else ()
    return ContextSimilarity(score,semantic.score,numeric.score,coverage,matched,differing,missing,flags,
        (f"Context coverage is {coverage:.1%}.",))


def aggregate_similarity(semantic: SemanticSimilarity, numeric: NumericSimilarity, context: ContextSimilarity,
        weights: Sequence[float] = (.45,.35,.20), settings: HistoricalSimilaritySettings = HistoricalSimilaritySettings()) -> SimilarityScoreBreakdown:
    if len(weights)!=3 or any(w<0 or not math.isfinite(w) for w in weights) or sum(weights)<=0: raise ValueError("invalid weights")
    scores=(semantic.score,numeric.score,context.score); coverages=(semantic.coverage,numeric.feature_coverage,context.coverage)
    available=[i for i,v in enumerate(scores) if v is not None]; effective=[0.0]*3
    total=sum(weights[i] for i in available)
    if total:
        for i in available: effective[i]=weights[i]/total
    overall=_clamp(sum(float(scores[i])*effective[i] for i in available)) if available else 0.0
    normalized=[w/sum(weights) for w in weights]
    coverage=_clamp(sum(coverages[i]*normalized[i] for i in range(3)))
    band=("VERY_HIGH" if overall>=settings.similarity_very_high_threshold else "HIGH" if overall>=settings.similarity_high_threshold
          else "MODERATE" if overall>=settings.similarity_moderate_threshold else "LOW" if overall>=settings.similarity_low_threshold else "VERY_LOW")
    flags=set()
    if len(available)<3: flags.add("LOW_SIMILARITY_COVERAGE")
    if coverage<settings.similarity_minimum_overall_coverage: flags.add("LOW_SIMILARITY_COVERAGE")
    return SimilarityScoreBreakdown(*scores,*coverages,*normalized,*effective,overall,coverage,band,tuple(sorted(flags)),
        ("Unavailable components are excluded and available weights are renormalized.",))


def analyze_differences(semantic: SemanticSimilarity, numeric: NumericSimilarity,
                        context: ContextSimilarity) -> DifferenceAnalysis:
    differences=[]
    for dimension,left,right in semantic.differing_tokens:
        differences.append(SimilarityDifference(dimension,left,right,"HIGH" if dimension in {"POS","MANIP","INST","REC"} else "MEDIUM",
            "DIFFERENT","Registered semantic values differ.",f"analysis:{dimension.lower()}"))
    for comparison in numeric.comparisons:
        if comparison.included and comparison.distance is not None and comparison.distance>=.2:
            direction="SOURCE_HIGHER" if comparison.source_value>comparison.candidate_value else "CANDIDATE_HIGHER"
            differences.append(SimilarityDifference(comparison.feature_name,comparison.source_value,comparison.candidate_value,
                "MEDIUM",direction,"Normalized feature distance is at least 0.20.",f"analysis:{comparison.feature_name}"))
    for text in context.differing_context:
        differences.append(SimilarityDifference(text.split(":",1)[0],text,None,"MEDIUM","DIFFERENT",
            "Frozen context values differ.","analysis:context"))
    missing=tuple(sorted(set(semantic.missing_source_tokens+semantic.missing_candidate_tokens+
        numeric.missing_source_features+numeric.missing_candidate_features+context.missing_context)))
    contradictory=tuple(f"{d}: {a} versus {b}" for d,a,b in semantic.differing_tokens if d in {"REC","POS","MANIP","INST"})
    return DifferenceAnalysis(semantic.matched_tokens,tuple(differences),missing,contradictory,(),
        ("All statements are direct comparisons of registered fields.",))


class CandidateSelector:
    def __init__(self,index: Any, settings: HistoricalSimilaritySettings = HistoricalSimilaritySettings()):
        self.index,self.settings=index,settings
    def select(self, request: SimilarityRequest, source: IndexedHistoricalIntelligence | MarketFingerprint,
               source_timestamp: datetime | None = None) -> tuple[IndexedHistoricalIntelligence,...]:
        request.validate(self.settings.similarity_query_maximum_limit)
        instrument=request.instrument_key
        if request.same_instrument_only and isinstance(source,IndexedHistoricalIntelligence): instrument=source.instrument_key
        recommendation=source.recommendation if request.same_recommendation_only else None
        version=request.fingerprint_version or source.fingerprint_version
        query=HistoricalIndexQuery(instrument_key=instrument,start_date=request.start_date,end_date=request.end_date,
            recommendation=recommendation,engine_version=request.engine_version,fingerprint_version=version,
            limit=request.maximum_candidates,order_by="analysis_timestamp",descending=True)
        records=self.index.query(query)
        source_id=request.source_trade_id or getattr(source,"trade_id",None)
        source_date=source_timestamp.date() if source_timestamp else getattr(source,"trading_date",None)
        return tuple(r for r in records if not (request.exclude_source_trade and r.trade_id==source_id)
            and not (request.exclude_same_trading_date and source_date and r.trading_date==source_date))


def summarize_outcomes(matches: Sequence[HistoricalSimilarityMatch], minimum_sample: int = 3) -> SimilarityOutcomeSummary:
    aliases={"FAVOURABLE":"favourable","UNFAVOURABLE":"unfavourable","INCONCLUSIVE":"inconclusive",
             "AVOIDED":"avoided","AVOIDED_LOSS":"avoided","MISSED_OPPORTUNITY":"missed","NOT_EVALUABLE":"not"}
    counts=Counter(aliases.get((m.outcome_classification or "NOT_EVALUABLE").upper(),"not") for m in matches)
    evaluable=len(matches)-counts["not"]; flags=[]
    if len(matches)<minimum_sample: flags.append("LOW_SAMPLE_SIZE")
    coverage=evaluable/len(matches) if matches else 0
    if coverage<.5: flags.append("OUTCOME_COVERAGE_LOW")
    pct=lambda n: 100*n/evaluable if evaluable else None
    return SimilarityOutcomeSummary(len(matches),evaluable,counts["favourable"],counts["unfavourable"],counts["inconclusive"],
        counts["avoided"],counts["missed"],counts["not"],pct(counts["favourable"]),pct(counts["unfavourable"]),
        _average(m.change_5m for m in matches),_average(m.change_15m for m in matches),_average(m.change_30m for m in matches),
        _average(m.change_eod for m in matches),_average(m.mfe for m in matches),_average(m.mae for m in matches),coverage,
        tuple(flags),("Percentages are descriptive historical frequencies, not predicted probabilities.",))


def discover_patterns(matches: Sequence[HistoricalSimilarityMatch], settings: HistoricalSimilaritySettings = HistoricalSimilaritySettings()) -> PatternDiscoverySummary:
    groups=defaultdict(list)
    approved=("MS","POS","OPTPOS","COMP","RELEASE","MANIP","TRAP","INST","VALID","REC","TRIG")
    for match in matches:
        tokens=_token_map(match.semantic_tokens)
        signature=tuple(f"{key}={tokens[key]}" for key in approved if key in tokens and tokens[key]!="UNKNOWN")
        context=tuple(sorted(t for t in match.context_tokens if "UNKNOWN" not in t))
        if signature: groups[(signature,context)].append(match)
    patterns=[]
    for (signature,context),items in groups.items():
        similarity=_average(m.score_breakdown.overall_score for m in items) or 0
        evaluable=[m for m in items if (m.outcome_classification or "NOT_EVALUABLE")!="NOT_EVALUABLE"]
        supported=len(items)>=settings.pattern_minimum_occurrences and len(evaluable)>=settings.pattern_minimum_evaluable_count and similarity>=settings.pattern_minimum_average_similarity
        if not supported and len(items)<2: continue
        digest=sha256(("|".join(signature)+"||"+"|".join(context)).encode()).hexdigest()[:10].upper()
        common=lambda values: sorted(Counter(v for v in values if v).items(),key=lambda x:(-x[1],x[0]))[0][0] if any(values) else None
        outcomes=[m.outcome_classification for m in items]
        flags=() if supported else ("LOW_SAMPLE_PATTERN","PATTERN_SUPPORT_INSUFFICIENT")
        patterns.append(DiscoveredPattern(f"PAT-{digest}",f"Pattern {digest}",signature,context,len(items),len(evaluable),
            common([m.recommendation for m in items]),common(outcomes),_average(m.decision_confidence for m in items),similarity,
            _average(m.change_15m for m in items),_average(m.change_30m for m in items),_average(m.mfe for m in items),
            _average(m.mae for m in items),tuple(sorted(m.candidate_trade_id for m in items)),flags,
            ("Observed deterministic token co-occurrence; it is not a predictive claim.",)))
    patterns=sorted(patterns,key=lambda p:(-p.occurrence_count,-(p.average_similarity or 0),p.pattern_id))[:settings.pattern_maximum_results]
    strongest=max(patterns,key=lambda p:((p.average_similarity or 0),p.pattern_id),default=None)
    flags=("PATTERN_SUPPORT_INSUFFICIENT",) if not patterns else ()
    return PatternDiscoverySummary(len(patterns),tuple(patterns),patterns[0].pattern_id if patterns else None,
        strongest.pattern_id if strongest else None,settings.pattern_registry_version,flags,
        ("Patterns are descriptive observations over the selected matches.",))


OPPOSITE_VALUES={"BUY CE":"BUY PE","BUY PE":"BUY CE","BULLISH":"BEARISH","BEARISH":"BULLISH",
                 "LONG_BUILDUP":"SHORT_BUILDUP","SHORT_BUILDUP":"LONG_BUILDUP"}


class HistoricalSimilarityService:
    def __init__(self,index: Any, settings: HistoricalSimilaritySettings = HistoricalSimilaritySettings()):
        self.index,self.settings=index,settings
    def _fingerprint(self,row: IndexedHistoricalIntelligence) -> MarketFingerprint:
        return MarketFingerprint(row.trade_id,row.fingerprint_version,getattr(self.index.settings,"feature_registry_version","features-v1"),
            getattr(self.index.settings,"semantic_token_registry_version","semantic-v1"),row.engine_version,row.schema_version,
            row.semantic_tokens,row.semantic_key,row.numeric_features,sum(v is not None for _,v in row.numeric_features),
            sum(v is None for _,v in row.numeric_features),row.recommendation,
            {"BUY CE":"BULLISH","BUY PE":"BEARISH"}.get(row.recommendation,"NEUTRAL"),row.quality_flags,())
    def find_similar(self, request: SimilarityRequest, source_context: ContextFingerprint | None = None) -> HistoricalSimilarityResult:
        request.validate(self.settings.similarity_query_maximum_limit); flags=set(request.quality_flags)
        source_row=None
        if request.source_trade_id:
            source_row=self.index.get_by_trade_id(request.source_trade_id,request.fingerprint_version)
            if source_row is None: raise ValueError("SOURCE_FINGERPRINT_UNAVAILABLE")
            source=self._fingerprint(source_row)
        else: source=request.source_fingerprint
        if request.fingerprint_version and source.fingerprint_version!=request.fingerprint_version: raise ValueError("CROSS_VERSION_MATCH_BLOCKED")
        if source_context is None and source_row is not None:
            source_context=build_context_fingerprint(source_row.analysis_timestamp,version=self.settings.context_fingerprint_version)
        candidates=CandidateSelector(self.index,self.settings).select(request,source_row or source,
            source_row.analysis_timestamp if source_row else None)
        if request.exclude_source_trade: flags.add("SOURCE_TRADE_EXCLUDED")
        if not candidates: flags.add("INSUFFICIENT_CANDIDATES")
        scored=[]; semantic_weights=dict(self.settings.semantic_dimension_weights); numeric_weights=dict(self.settings.numeric_feature_weights)
        for row in candidates:
            candidate=self._fingerprint(row)
            semantic=semantic_similarity(source,candidate,semantic_weights)
            numeric=numeric_similarity(source,candidate,numeric_weights)
            candidate_context=build_context_fingerprint(row.analysis_timestamp,version=self.settings.context_fingerprint_version)
            context=context_similarity(source_context,candidate_context)
            breakdown=aggregate_similarity(semantic,numeric,context,
                (request.semantic_weight,request.numeric_weight,request.context_weight),self.settings)
            if breakdown.overall_score < request.minimum_overall_score: continue
            difference=analyze_differences(semantic,numeric,context) # score is frozen before outcome fields below
            scored.append(HistoricalSimilarityMatch(request.source_trade_id,row.trade_id,row.analysis_timestamp,row.instrument_key,
                row.recommendation,row.decision_confidence,breakdown,semantic,numeric,context,difference,row.outcome_classification,
                replay_completeness=row.replay_completeness,option_data_status="INCOMPLETE" if "OPTION_DATA_INCOMPLETE" in row.quality_flags else "AVAILABLE",
                navigation_targets=(f"historical_trade_review:{row.trade_id}",f"historical_replay:{row.trade_id}:{row.analysis_timestamp.isoformat()}"),
                semantic_tokens=row.semantic_tokens,context_tokens=candidate_context.semantic_tokens,quality_flags=row.quality_flags,
                explanations=("Historical outcomes were attached after similarity scoring.",)))
        scored.sort(key=lambda m:(-m.score_breakdown.overall_score,-m.score_breakdown.overall_coverage,
            -m.semantic_similarity.score,-(m.context_similarity.score or -1),-m.candidate_analysis_timestamp.timestamp(),m.candidate_trade_id))
        normal=[]; opposite=[]; per_date=Counter(); seen_semantic=set(); last_by_date={}
        source_tokens=_token_map(source.semantic_tokens)
        for match in scored:
            candidate_tokens=_token_map(match.semantic_tokens)
            is_opposite=any(OPPOSITE_VALUES.get(source_tokens.get(k))==candidate_tokens.get(k) for k in ("REC","POS"))
            if is_opposite and request.include_opposite_setups: opposite.append(match); continue
            if is_opposite: continue
            day=match.candidate_analysis_timestamp.date()
            if self.settings.similarity_maximum_matches_per_date and per_date[day]>=self.settings.similarity_maximum_matches_per_date:
                flags.add("SAME_DAY_DUPLICATES_REDUCED"); continue
            if self.settings.similarity_semantic_deduplication_enabled and match.semantic_tokens in seen_semantic:
                flags.add("SAME_DAY_DUPLICATES_REDUCED"); continue
            prior=last_by_date.get(day)
            if prior and abs((match.candidate_analysis_timestamp-prior).total_seconds()) < self.settings.similarity_minimum_minutes_between_same_day_matches*60:
                flags.add("SAME_DAY_DUPLICATES_REDUCED"); continue
            normal.append(match); per_date[day]+=1; seen_semantic.add(match.semantic_tokens); last_by_date[day]=match.candidate_analysis_timestamp
            if len(normal)>=request.maximum_results: break
        opposite=opposite[:request.maximum_results]
        if len(normal)<1: flags.add("INSUFFICIENT_MATCHES")
        outcomes=summarize_outcomes(normal) if request.include_outcome_summary and self.settings.similarity_outcome_summary_enabled else None
        patterns=discover_patterns(normal,self.settings) if request.include_pattern_summary and self.settings.pattern_discovery_enabled else None
        counts=Counter(m.score_breakdown.confidence_band for m in normal); best=normal[0] if normal else None
        return HistoricalSimilarityResult(request,request.source_trade_id,source.fingerprint_version,len(candidates),len(scored),len(normal),
            tuple(normal),tuple(opposite),counts["VERY_HIGH"],counts["HIGH"],counts["MODERATE"],counts["LOW"],
            best.candidate_trade_id if best else None,best.score_breakdown.overall_score if best else None,outcomes,patterns,
            self.settings.similarity_algorithm_version,self.settings.context_fingerprint_version,
            self.settings.similarity_weight_profile_version,self.settings.pattern_registry_version,tuple(sorted(flags)),
            ("Similarity is advisory and never changes recommendation, confidence, validation, or ranking.",))


def similarity_rows(result: HistoricalSimilarityResult) -> tuple[dict[str,Any],...]:
    rows=[]
    for rank,m in enumerate(result.matches,1):
        d=m.score_breakdown
        rows.append({"Rank":rank,"Trade ID":m.candidate_trade_id,"Date":m.candidate_analysis_timestamp.date().isoformat(),
            "Time":m.candidate_analysis_timestamp.time().isoformat(),"Recommendation":m.recommendation,"Overall Similarity":d.overall_score,
            "Semantic Similarity":d.semantic_score,"Numeric Similarity":d.numeric_score,"Context Similarity":d.context_score,
            "Coverage":d.overall_coverage,"Decision Confidence":m.decision_confidence,"Result Classification":m.outcome_classification,
            "15m Outcome":m.change_15m,"30m Outcome":m.change_30m,"MFE":m.mfe,"MAE":m.mae,
            "Primary Shared Evidence":m.difference_analysis.shared_evidence[0] if m.difference_analysis.shared_evidence else None,
            "Primary Difference":m.difference_analysis.important_differences[0].dimension if m.difference_analysis.important_differences else None,
            "Option Data Status":m.option_data_status,"View Match":m.navigation_targets[0] if m.navigation_targets else None})
    return tuple(rows)


def export_json(result: HistoricalSimilarityResult) -> bytes:
    return json.dumps(asdict(result),default=lambda v:v.isoformat() if isinstance(v,(date,datetime)) else str(v),sort_keys=True).encode()


def export_csv(result: HistoricalSimilarityResult) -> bytes:
    output=BytesIO(); rows=similarity_rows(result)
    text=[]
    if rows:
        import io
        stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=tuple(rows[0])); writer.writeheader(); writer.writerows(rows); return stream.getvalue().encode()
    return b""


def export_parquet(result: HistoricalSimilarityResult) -> bytes | None:
    try:
        import pandas as pd
        output=BytesIO(); pd.DataFrame(similarity_rows(result)).to_parquet(output,index=False); return output.getvalue()
    except (ImportError,ModuleNotFoundError):
        return None
