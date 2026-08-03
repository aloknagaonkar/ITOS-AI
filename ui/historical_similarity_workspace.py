"""Readable Streamlit workspace for advisory historical similarity."""
from __future__ import annotations

from datetime import date, timedelta
import pandas as pd
import streamlit as st

from itos_platform.historical_intelligence_index import SQLiteHistoricalIntelligenceIndex
from itos_platform.historical_similarity import (
    HistoricalSimilarityService, SimilarityRequest, export_csv, export_json,
    export_parquet, similarity_rows,
)

PREFIX = "historical_similarity_"


def render_historical_similarity_workspace(index: SQLiteHistoricalIntelligenceIndex | None = None) -> None:
    """Render filters/results without running or mutating any analytical pipeline."""
    st.title("Historical Similarity & Pattern Discovery")
    st.info("Advisory only — observed historical similarity does not change the current recommendation.")
    index = index or SQLiteHistoricalIntelligenceIndex()
    source_mode = st.selectbox("Source", ("Selected Historical Trade", "Selected Replay State", "Current Live State"), key=PREFIX+"source_mode")
    source_trade_id = st.text_input("Stable Historical Trade ID", value=st.session_state.get(PREFIX+"source_trade_id", ""), key=PREFIX+"source_input").strip()
    cols=st.columns(3)
    instrument=cols[0].text_input("Instrument", key=PREFIX+"instrument").strip() or None
    start=cols[1].date_input("Start date", value=date.today()-timedelta(days=30), key=PREFIX+"start")
    end=cols[2].date_input("End date", value=date.today(), key=PREFIX+"end")
    options=st.columns(4)
    same_instrument=options[0].checkbox("Same instrument only",True,key=PREFIX+"same_instrument")
    same_recommendation=options[1].checkbox("Same recommendation only",False,key=PREFIX+"same_recommendation")
    exclude_date=options[2].checkbox("Exclude same date",False,key=PREFIX+"exclude_date")
    opposites=options[3].checkbox("Include opposite setups",False,key=PREFIX+"opposites")
    limits=st.columns(2)
    minimum=limits[0].slider("Minimum similarity",0.0,1.0,0.65,0.01,key=PREFIX+"minimum")
    maximum=limits[1].number_input("Maximum results",1,100,25,key=PREFIX+"maximum")
    actions=st.columns(2)
    if actions[1].button("Reset",key=PREFIX+"reset"):
        for key in tuple(st.session_state):
            if key.startswith(PREFIX): del st.session_state[key]
        st.rerun()
    if actions[0].button("Find Similar Markets",type="primary",key=PREFIX+"find"):
        if not source_trade_id:
            st.session_state[PREFIX+"error"] = f"{source_mode} requires a frozen indexed Trade ID."
        else:
            try:
                request=SimilarityRequest(source_trade_id=source_trade_id,instrument_key=instrument,start_date=start,end_date=end,
                    same_instrument_only=same_instrument,same_recommendation_only=same_recommendation,
                    exclude_same_trading_date=exclude_date,include_opposite_setups=opposites,
                    maximum_candidates=1000,maximum_results=int(maximum),minimum_overall_score=minimum)
                st.session_state[PREFIX+"result"] = HistoricalSimilarityService(index).find_similar(request)
                st.session_state.pop(PREFIX+"error",None)
            except (ValueError,RuntimeError) as error:
                st.session_state[PREFIX+"error"] = str(error)
    if error:=st.session_state.get(PREFIX+"error"): st.warning(f"Similarity unavailable: {error}")
    result=st.session_state.get(PREFIX+"result")
    if result is None:
        st.caption("Choose an indexed frozen source and find similar markets. No live broker call is made.")
        return
    summary=result.aggregate_outcomes
    cards=st.columns(5)
    cards[0].metric("Matches Found",result.result_count); cards[1].metric("Very High Matches",result.very_high_count)
    cards[2].metric("High Matches",result.high_count); cards[3].metric("Best Match Score",f"{(result.best_match_score or 0):.1%}")
    cards[4].metric("Outcome Coverage",f"{(summary.outcome_coverage if summary else 0):.1%}")
    st.caption(f"Sample size: {summary.match_count if summary else 0} • Evaluable: {summary.evaluable_count if summary else 0} • "
        f"Fingerprint: {result.source_fingerprint_version} • Algorithm: {result.similarity_algorithm_version} • "
        f"Weights: semantic {result.request.normalized_weights[0]:.0%}, numeric {result.request.normalized_weights[1]:.0%}, context {result.request.normalized_weights[2]:.0%}")
    if summary:
        outcomes=st.columns(5)
        outcomes[0].metric("Historical favourable frequency","—" if summary.favourable_percentage is None else f"{summary.favourable_percentage:.1f}%")
        outcomes[1].metric("Average 15m Move",summary.average_15m_change or "—"); outcomes[2].metric("Average 30m Move",summary.average_30m_change or "—")
        outcomes[3].metric("Average MFE",summary.average_mfe or "—"); outcomes[4].metric("Average MAE",summary.average_mae or "—")
    if result.quality_flags: st.warning("Quality flags: "+", ".join(result.quality_flags))
    rows=similarity_rows(result)
    st.subheader("Similar Historical Trades")
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    if not rows: st.info("No historical matches satisfy the selected filters and threshold.")
    downloads=st.columns(3)
    downloads[0].download_button("Export CSV",export_csv(result),"historical_similarity.csv","text/csv")
    downloads[1].download_button("Export JSON",export_json(result),"historical_similarity.json","application/json")
    parquet=export_parquet(result)
    downloads[2].download_button("Export Parquet",parquet or b"","historical_similarity.parquet",disabled=parquet is None)
    if result.opposite_matches:
        st.subheader("Opposite Setups (separate group)"); st.caption(f"{len(result.opposite_matches)} explicit-registry opposite matches")
    if result.pattern_summary:
        st.subheader("Observed Historical Patterns")
        pattern_rows=[{"Pattern":p.display_name,"Occurrences":p.occurrence_count,"Evaluable":p.evaluable_count,
            "Common Recommendation":p.common_recommendation,"Common Outcome":p.common_outcome,"Average Similarity":p.average_similarity,
            "Average Confidence":p.average_confidence,"Average 15m":p.average_15m_change,"Average 30m":p.average_30m_change,
            "Average MFE":p.average_mfe,"Average MAE":p.average_mae,"View Trades":", ".join(p.supporting_trade_ids)}
            for p in result.pattern_summary.patterns]
        st.dataframe(pd.DataFrame(pattern_rows),hide_index=True,use_container_width=True)
        st.caption("Patterns are observed, deterministic co-occurrences; they are not proven or predictive.")
