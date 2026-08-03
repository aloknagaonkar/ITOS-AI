from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from itos_platform.historical_intelligence_index import MarketFingerprint
from itos_platform.historical_similarity import (
    HistoricalSimilarityMatch, HistoricalSimilaritySettings, SimilarityRequest,
    aggregate_similarity, analyze_differences, build_context_fingerprint,
    context_similarity, discover_patterns, numeric_similarity, semantic_similarity,
    summarize_outcomes,
)


def fingerprint(tokens=("MS=BULLISH", "POS=LONG_BUILDUP", "REC=BUY_CE"), features=(("decision_confidence", .8),)):
    return MarketFingerprint("T1","fp-v1","features-v1","semantic-v1","engine-v1","schema-v1",tokens,
        "|".join(tokens),features,sum(v is not None for _,v in features),sum(v is None for _,v in features),
        "BUY CE","BULLISH",(),())


def test_request_validation_and_normalization():
    request=SimilarityRequest(source_trade_id="T1",semantic_weight=2,numeric_weight=1,context_weight=1)
    assert request.validate().normalized_weights == (.5,.25,.25)
    assert SimilarityRequest(source_fingerprint=fingerprint()).validate()
    with pytest.raises(ValueError): SimilarityRequest().validate()
    with pytest.raises(ValueError): SimilarityRequest(source_trade_id="T",semantic_weight=-1).validate()
    with pytest.raises(ValueError): SimilarityRequest(source_trade_id="T",start_date=date(2025,2,2),end_date=date(2025,1,1)).validate()
    with pytest.raises(ValueError): SimilarityRequest(source_trade_id="T",maximum_candidates=1001).validate()


def test_semantic_similarity_is_family_weighted_and_reports_coverage():
    same=semantic_similarity(fingerprint(),fingerprint())
    assert same.score == 1 and same.coverage == 1
    partial=semantic_similarity(("MS=BULLISH","POS=LONG_BUILDUP"),("MS=BEARISH","POS=LONG_BUILDUP"),{"MS":3,"POS":1})
    assert partial.score == .25 and partial.matched_tokens == ("POS=LONG_BUILDUP",)
    missing=semantic_similarity(("MS=BULLISH",),("POS=LONG_BUILDUP",))
    assert missing.score == 0 and missing.coverage == 0 and "SEMANTIC_DATA_INCOMPLETE" in missing.quality_flags
    # An outcome-looking value outside the registered token family is merely a differing family; no outcome field is read.
    assert semantic_similarity(("REC=BUY_CE",),("REC=BUY_PE",)).score == 0


def test_numeric_similarity_missing_is_not_zero_and_is_clamped():
    result=numeric_similarity({"a":.2,"b":None},{"a":.3,"b":1})
    assert result.score == pytest.approx(.9) and result.feature_coverage == .5
    assert result.comparisons[1].included is False
    assert numeric_similarity({"a":-4},{"a":4}).score == 0
    assert numeric_similarity({"a":None},{"a":1}).score is None


def test_context_fingerprint_session_gap_and_no_future_classification():
    opening=build_context_fingerprint(datetime(2025,1,6,9,30,tzinfo=timezone.utc),opening_price=101,previous_close=100)
    assert opening.session_phase == "OPENING" and opening.gap_context == "GAP_UP" and opening.day_of_week == "Monday"
    midday=build_context_fingerprint(datetime(2025,1,6,12,30,tzinfo=timezone.utc))
    closing=build_context_fingerprint(datetime(2025,1,6,15,15,tzinfo=timezone.utc))
    assert midday.session_phase == "MIDDAY" and closing.session_phase == "CLOSING"
    assert midday.previous_day_context == "UNKNOWN"


def test_context_similarity_and_aggregation_redistribute_unavailable_component():
    context=build_context_fingerprint(datetime(2025,1,6,10,30))
    compared=context_similarity(context,context)
    assert compared.score == 1
    semantic=semantic_similarity(("MS=BULLISH",),("MS=BULLISH",))
    numeric=numeric_similarity({"a":None},{"a":None})
    unavailable=context_similarity(None,None)
    score=aggregate_similarity(semantic,numeric,unavailable)
    assert score.overall_score == 1 and score.effective_semantic_weight == 1
    assert score.effective_numeric_weight == score.effective_context_weight == 0


def make_match(trade_id="T1", outcome="FAVOURABLE", score=.8, tokens=("MS=BULLISH","POS=LONG_BUILDUP")):
    semantic=semantic_similarity(tokens,tokens); numeric=numeric_similarity({"a":.8},{"a":.8})
    context=context_similarity(build_context_fingerprint(datetime(2025,1,6,10)),build_context_fingerprint(datetime(2025,1,6,10)))
    breakdown=aggregate_similarity(semantic,numeric,context)
    difference=analyze_differences(semantic,numeric,context)
    return HistoricalSimilarityMatch(None,trade_id,datetime(2025,1,6,10),"NIFTY","BUY CE",80,replace(breakdown,overall_score=score),
        semantic,numeric,context,difference,outcome,change_15m=1,change_30m=2,mfe=3,mae=-1,
        semantic_tokens=tokens,context_tokens=("SESSION=MORNING",))


def test_difference_outcomes_and_pattern_discovery_are_factual():
    semantic=semantic_similarity(("REC=BUY_CE",),("REC=BUY_PE",))
    difference=analyze_differences(semantic,numeric_similarity({"a":.1},{"a":.8}),context_similarity(None,None))
    assert difference.important_differences[0].analysis_target == "analysis:rec"
    matches=(make_match("T1"),make_match("T2","UNFAVOURABLE"),make_match("T3","NOT_EVALUABLE"))
    summary=summarize_outcomes(matches)
    assert summary.evaluable_count == 2 and summary.favourable_percentage == 50
    patterns=discover_patterns(matches,HistoricalSimilaritySettings())
    assert patterns.pattern_count == 1
    assert patterns.patterns[0].pattern_id.startswith("PAT-")
    assert patterns.patterns[0].supporting_trade_ids == ("T1","T2","T3")
