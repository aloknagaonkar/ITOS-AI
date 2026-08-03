from __future__ import annotations

import os
import time
from datetime import date, timedelta
from urllib.parse import urlencode

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from ai_engine import analyse_market
from charting import make_market_chart
from market_intelligence import combine_intelligence, evaluate_price_action
from history_charts import line_chart, oi_flow_chart, strike_heatmap
from institutional_engine import institutional_summary
from recommendation_engine import build_recommendation
from engines import (
    CandleDNAEngine,
    FalseBreakoutEngine,
    InstitutionalConfirmationEngine,
    InstitutionalFootprintEngine,
    InstitutionalRadarEngine,
    InstitutionalStructureEngine,
    MarketCycleEngine,
    MarketStoryEngine,
    PatternRecognitionEngine,
    PhaseTransitionEngine,
    RecommendationStabilityEngine,
    SmartCandlestickEngine,
    TradeReadinessEngine,
    build_historical_candle_pattern_table,
    build_pattern_statistics,
    AITradePlannerEngine,
    InstitutionalDecisionMatrixEngine,
    InstitutionalFlowEngine,
    InstitutionalConfidenceEngine,
    SignalValidationEngine,
    EarlyWarningEngine,
    MarketRegimeEngine,
    SmartMoneyIndexEngine,
    MarketEnergyEngine,
    OpportunityLifecycleEngine,
    HistoricalSimilarityEngine,
    InstitutionalPlaybookEngine,
    MarketReplayEngine,
    ExplainableSessionReportEngine,
    AIConsensusEngine, TradeProbabilityEngine, EnhancedRiskValidationEngine,
    DecisionReasoningEngine, InvalidationEngine, DecisionPackageEngine,
    DataHealthEngine,
)
from snapshot_store import SnapshotStore
from upstox_client import UpstoxAPIError, UpstoxClient
from engines.ai_trade_engine import AITradeEngine
from ui.ai_trade_card import render_ai_trade_opportunity
from dashboard_application_service import (
    DashboardApplicationService,
    DashboardDataUnavailable,
)
from itos_platform.replay import (
    DataMode, SampleDataProvider, build_upstox_historical_replay_provider,
)
from itos_platform.replay_ux import change_data_mode, initialize_replay_state
from ui.replay_workspace import render_replay_workspace
from ui.historical_analytics_workspace import render_historical_analytics_workspace
from ui.historical_similarity_workspace import render_historical_similarity_workspace
from itos_platform.historical_analytics import WorkspaceMode
from itos_platform.historical_sync import HistoricalSyncManager, UpstoxHistoricalSyncProvider
from itos_platform.market_lake import LocalHistoricalMarketLake

load_dotenv()
st.set_page_config(
    page_title="AI Institutional Options Terminal v9.0.3",
    page_icon="📊",
    layout="wide",
)

UNDERLYINGS = {
    "NIFTY 50": "NSE_INDEX|Nifty 50",
    "BANK NIFTY": "NSE_INDEX|Nifty Bank",
}


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def auth() -> str:
    st.sidebar.subheader("Authentication")
    token = st.sidebar.text_input(
        "Access token", value=env("UPSTOX_ACCESS_TOKEN"), type="password"
    )
    with st.sidebar.expander("OAuth login (optional)"):
        key = st.text_input("API Key", value=env("UPSTOX_API_KEY"))
        secret = st.text_input("API Secret", value=env("UPSTOX_API_SECRET"), type="password")
        redirect = st.text_input(
            "Redirect URI", value=env("UPSTOX_REDIRECT_URI", "http://localhost:8501")
        )
        if key and redirect:
            q = urlencode(
                {
                    "response_type": "code",
                    "client_id": key,
                    "redirect_uri": redirect,
                    "state": "ce_pe_decision_engine_v5",
                }
            )
            st.link_button(
                "1. Login with Upstox",
                f"https://api.upstox.com/v2/login/authorization/dialog?{q}",
            )
        code = st.text_input("Authorization code", value=st.query_params.get("code", ""))
        if st.button("2. Exchange code"):
            try:
                data = UpstoxClient("").exchange_code(code, key, secret, redirect)
                st.session_state["access_token"] = data["access_token"]
                st.success("Access token generated for this session.")
            except Exception as exc:
                st.error(str(exc))
    return st.session_state.get("access_token", token)


def compact_number(value: float) -> str:
    value = float(value)
    if abs(value) >= 10_000_000:
        return f"{value / 10_000_000:.2f} Cr"
    if abs(value) >= 100_000:
        return f"{value / 100_000:.2f} L"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f} K"
    return f"{value:,.0f}"


def state_icon(state: str) -> str:
    return {
        "Strong Bullish": "🟢",
        "Bullish": "🟩",
        "Neutral": "⚪",
        "Bearish": "🟥",
        "Strong Bearish": "🔴",
    }.get(state, "⚪")

st.title("ITOS — Institutional Trading Operating System v9.0.3")
with st.sidebar:
    st.markdown("---")
    st.markdown("**ITOS — Institutional Trading Operating System**")
    st.caption("Version 9.0.2 • Decision-First Dashboard")

st.caption(
    "Same institutional terminal UI • Two-tab workflow • AI Trade Opportunity added below Key Market Summary"
)
token = auth()
authenticated_client = UpstoxClient(token) if token else None
initialize_replay_state(st.session_state)
workspace_mode = st.sidebar.selectbox(
    "Top Level Mode", (*tuple(WorkspaceMode), "HISTORICAL_SIMILARITY"),
    format_func=lambda mode: (mode.value if isinstance(mode, WorkspaceMode) else mode).replace("_", " "),
)
if workspace_mode is WorkspaceMode.HISTORICAL_ANALYTICS:
    historical_lake = LocalHistoricalMarketLake()
    historical_provider = (UpstoxHistoricalSyncProvider(client=authenticated_client)
                           if authenticated_client is not None else None)
    render_historical_analytics_workspace(UNDERLYINGS, lake=historical_lake,
        sync_manager=HistoricalSyncManager(provider=historical_provider, market_lake=historical_lake))
    st.stop()
if workspace_mode == "HISTORICAL_SIMILARITY":
    render_historical_similarity_workspace()
    st.stop()
selected_mode = {
    WorkspaceMode.LIVE: DataMode.LIVE,
    WorkspaceMode.HISTORICAL_REPLAY: DataMode.HISTORICAL_REPLAY,
    WorkspaceMode.SAMPLE_DATA: DataMode.SAMPLE_DATA,
}[workspace_mode]
change_data_mode(st.session_state, selected_mode)
workspace_options = ("Analyst Dashboard",) if selected_mode is DataMode.LIVE else ("Historical Replay", "Analyst Dashboard")
workspace = st.sidebar.radio("Workspace", workspace_options, key="replay_selected_workspace")

if selected_mode is not DataMode.LIVE and workspace == "Historical Replay":
    def replay_provider_factory(mode: DataMode):
        if mode is DataMode.SAMPLE_DATA:
            return SampleDataProvider()
        return build_upstox_historical_replay_provider(authenticated_client)
    render_replay_workspace(selected_mode, st.session_state, replay_provider_factory, UNDERLYINGS)
    st.stop()
if selected_mode is not DataMode.LIVE:
    st.warning(f"**{selected_mode.value.replace('_', ' ')} MODE** — live acquisition is disabled.")
    frozen = st.session_state.get("replay_frozen_result")
    if frozen is None:
        st.info("Run a replay point in the Historical Replay workspace before opening the Analyst Dashboard.")
    else:
        st.info("The frozen replay snapshot is retained. Return to Historical Replay to inspect it; no live data was loaded.")
    st.stop()
if not token:
    st.info("Enter an Upstox access token. A read-only Analytics Token is the simplest choice.")
    st.stop()

with st.sidebar:
    st.subheader("Market selection")
    underlying = st.selectbox("Underlying", list(UNDERLYINGS))
    timeframe = st.selectbox("Chart timeframe", [1, 3, 5, 10, 15, 30], index=2)
    strikes = st.slider("Strikes around ATM", 3, 20, 8)
    auto_refresh = st.checkbox("Auto-refresh", value=False)
    refresh_seconds = st.selectbox("Refresh interval", [15, 30, 60], index=2)
    st.caption("Use 60 seconds for one clean database snapshot per minute.")
    history_hours = st.selectbox("History window", [1, 2, 4, 8, 12], index=3)
    save_snapshots = st.checkbox("Store snapshots in SQLite", value=True)

    expiry = None
    try:
        expiry_client = authenticated_client
        available_expiries = expiry_client.get_option_expiries(UNDERLYINGS[underlying])
        expiry = st.selectbox(
            "Active expiry",
            available_expiries,
            index=0,
            help="Loaded from the Upstox Option Contracts API.",
        )
        st.caption(f"{len(available_expiries)} active expiry date(s) found.")
    except UpstoxAPIError as exc:
        st.error(f"Unable to retrieve active expiries: {exc}")

    run = st.button(
        "Run market intelligence",
        type="primary",
        use_container_width=True,
        disabled=expiry is None,
    )

should_load = run or (auto_refresh and expiry is not None)
dashboard_service = DashboardApplicationService(
    warning=st.warning, client=authenticated_client,
)
dashboard_result = None
try:
    if should_load:
        with st.spinner("Loading option chain, candles and intelligence signals..."):
            dashboard_result = dashboard_service.execute(
                token=token,
                instrument_key=UNDERLYINGS[underlying],
                underlying=underlying,
                expiry=expiry,
                timeframe=timeframe,
                strikes=strikes,
                save_snapshots=save_snapshots,
                history_hours=history_hours,
                should_load=True,
                session_state=st.session_state,
            )
    else:
        dashboard_result = dashboard_service.execute(
            token=token,
            instrument_key=UNDERLYINGS[underlying],
            underlying=underlying,
            expiry=expiry,
            timeframe=timeframe,
            strikes=strikes,
            save_snapshots=save_snapshots,
            history_hours=history_hours,
            should_load=False,
            session_state=st.session_state,
        )
except UpstoxAPIError as exc:
    st.error(f"Upstox API error: {exc}")
except DashboardDataUnavailable:
    pass
except Exception as exc:
    st.exception(exc)

# Acquisition errors historically left any previous successful refresh visible.
if dashboard_result is None and st.session_state.get("option_result") and st.session_state.get("intelligence"):
    try:
        dashboard_result = dashboard_service.execute(
            token=token, instrument_key=UNDERLYINGS[underlying], underlying=underlying,
            expiry=expiry, timeframe=timeframe, strikes=strikes,
            save_snapshots=save_snapshots, history_hours=history_hours,
            should_load=False, session_state=st.session_state,
        )
    except Exception as exc:
        st.exception(exc)

if dashboard_result is None:
    st.warning("Click **Run market intelligence** to load the dashboard.")
    st.stop()

if dashboard_result.values.get("data_unavailable"):
    st.warning(dashboard_result.warning)
    st.stop()

# Preserve the variable names consumed by the unchanged presentation layer.
globals().update(dashboard_result.values)
s = option_result["summary"]
df = option_result["chain"]
p = intelligence["price"]

tab_live, tab_explorer = st.tabs([
    "📊 Live Market Intelligence",
    "📚 Intelligence Explorer",
])

with tab_live:
    st.caption(
        f"{dashboard_result.market_snapshot.selected_instrument} • "
        f"Expiry {dashboard_result.market_snapshot.expiry} • "
        f"{dashboard_result.market_snapshot.timeframe}-minute candles • "
        f"Last refresh {dashboard_result.market_snapshot.timestamps.get('last_refresh', '-')}"
    )

    # Keep only urgent feed failures at the top. The complete Data Health section
    # appears at the bottom of the live dashboard.
    if not data_health_result.metadata.get("trading_allowed", False):
        st.error("⚠ DATA ISSUE — NO TRADE: " + "; ".join(data_health_result.explanation))
    elif data_health_result.vote == "CAUTION":
        st.warning("⚠ Data inputs are degraded. Treat decisions as WATCH until inputs recover.")

    # Decision-critical information comes before research and diagnostic sections.
    render_ai_trade_opportunity(ai_trade_opportunity)

    # Key levels remain on the first screen, directly below the decision cockpit.
    st.markdown("### Key Market Levels")
    level1, level2, level3, level4 = st.columns(4)
    level1.metric("Support", f"{s['support']:,.0f}")
    level2.metric("Resistance", f"{s['resistance']:,.0f}")
    level3.metric("Max Pain", f"{s['max_pain']:,.0f}")
    level4.metric("Spot / ATM", f"{s['spot']:,.2f} / {s['atm']:,.0f}")


    st.markdown("## ❓ Why is the market behaving this way?")
    st.caption("Institutional Intelligence")

    # Version 7.1 executive intelligence appears immediately below the key market
    # levels so the first screen answers what, why, and whether the trade is ready.
    st.markdown("### AI Institutional Brief")
    st.info(story_result.metadata.get("story", "Institutional story is developing."))

    brief1, brief2, brief3, brief4 = st.columns(4)
    brief1.metric("Trade Readiness", f"{readiness_result.metadata.get('readiness_score', 0):.0f}%", readiness_result.metadata.get("status", "WAIT"))
    brief2.metric("Current → Next Phase", f"{transition_result.metadata.get('current_phase', 'Unknown')} → {transition_result.metadata.get('next_phase', 'Unknown')}")
    brief3.metric("Transition Probability", f"{transition_result.metadata.get('transition_probability', 0):.0f}%", transition_result.metadata.get("transition_state", "DEVELOPING"))
    brief4.metric("Institutional Bias", radar_result.metadata.get("institution_bias", "Neutral"), f"Pattern: {pattern_result.metadata.get('primary_pattern', {}).get('name', 'None')}")

    st.markdown("#### Version 7.5 Institutional Confirmation")
    v751, v752, v753, v754 = st.columns(4)
    v751.metric("Institutional Confirmation", f"{confirmation_result.score:.0f}/100", confirmation_result.metadata.get("status", "DEVELOPING"))
    v752.metric("Footprint", footprint_result.metadata.get("participant", "UNKNOWN"), f"{footprint_result.score:.0f}% • {footprint_result.metadata.get('behaviour', 'MIXED')}")
    v753.metric("Market Structure", structure_result.metadata.get("primary", {}).get("name", "None"), structure_result.metadata.get("primary", {}).get("status", "INACTIVE"))
    v754.metric("False-Breakout Risk", f"{false_breakout_result.score:.0f}/100", false_breakout_result.metadata.get("label", "LOW"))

    conf_rows = pd.DataFrame(confirmation_result.metadata.get("rows", []))
    if not conf_rows.empty:
        conf_rows["Status"] = conf_rows["aligned"].map({True: "✅ ALIGNED", False: "⚠ CONFLICT"})
        with st.expander("Institutional confirmation evidence", expanded=False):
            st.dataframe(conf_rows[["engine", "vote", "score", "weight", "Status"]], use_container_width=True, hide_index=True)

    st.markdown("#### Smart Candle & Candle DNA")
    cd1, cd2, cd3, cd4 = st.columns(4)
    cd1.metric("Candle Pattern", smart_candle_result.metadata.get("primary", {}).get("name", "None"))
    cd2.metric("Pattern Reliability", f"{smart_candle_result.score:.0f}%", smart_candle_result.vote)
    cd3.metric("Candle Strength", f"{candle_dna_result.score:.0f}/100", candle_dna_result.metadata.get("grade", "NORMAL"))
    cd4.metric("Candle Volume", f"{candle_dna_result.metadata.get('relative_volume', 0):.2f}×", f"Body {candle_dna_result.metadata.get('body_pct', 0):.0f}%")

    custom_dna_patterns = candle_dna_result.metadata.get("custom_patterns_detected", []) or []
    if custom_dna_patterns:
        st.success(
            "🧬 Custom Candle DNA detected: " + ", ".join(custom_dna_patterns) +
            " — bullish bottom-reversal structure; candle colour is ignored."
        )
        with st.expander("Injection-Pinbar (Bottom) DNA details", expanded=False):
            ip1, ip2, ip3, ip4 = st.columns(4)
            ip1.metric("Body", f"{candle_dna_result.metadata.get('body_pct', 0):.1f}%")
            ip2.metric("Upper Wick", f"{candle_dna_result.metadata.get('upper_wick_pct', 0):.1f}%")
            variant = candle_dna_result.metadata.get("injection_pinbar_variant", "CLASSIC_INJECTION")
            ip3.metric(
                "Lower Tip" if variant == "SMALL_TIP" else "Lower Wick / Body",
                f"{candle_dna_result.metadata.get('lower_wick_pct', 0):.1f}%" if variant == "SMALL_TIP"
                else f"{candle_dna_result.metadata.get('lower_wick_to_body', 0):.2f}×",
                variant.replace("_", " ").title(),
            )
            ip4.metric("Bottom Context", "YES" if candle_dna_result.metadata.get("near_bottom") or candle_dna_result.metadata.get("downmove_context") else "NO")
            st.caption(
                "Accepted variants: (1) Classic Injection — body ≥55%, upper wick ≤12%, lower wick ≥0.30× body; "
                "or (2) Small Tip — body ≥85%, upper wick ≤3%, and a visible lower tip ≤8% of range. "
                "Both require recent-bottom or short-downmove context. Candle colour is ignored."
            )

    historical_pattern_candles = st.session_state.get("historical_pattern_candles")
    historical_patterns = build_historical_candle_pattern_table(
        historical_pattern_candles, trading_days=2, evaluation_bars=5
    )
with tab_explorer:
    with st.expander("Historical Pattern Intelligence — Last 2 Trading Days", expanded=True):
        if historical_patterns.empty:
            st.info("No priority Smart Candle patterns were detected in the available last two trading sessions.")
        else:
            hp1, hp2, hp3, hp4, hp5 = st.columns(5)
            hp1.metric("Patterns", len(historical_patterns))
            hp2.metric("Confirmed", int((historical_patterns["Status"] == "CONFIRMED").sum()))
            hp3.metric("Failed", int(historical_patterns["Status"].isin(["FAILED", "INVALIDATED"]).sum()))
            evaluated_count = int(historical_patterns["Status"].isin(["CONFIRMED", "FAILED", "INVALIDATED", "UNRESOLVED"]).sum())
            win_rate = (historical_patterns["Status"].eq("CONFIRMED").sum() / evaluated_count * 100) if evaluated_count else 0
            hp4.metric("Evaluated Win Rate", f"{win_rate:.1f}%")
            hp5.metric("Institution Grade", int((historical_patterns["DNA Grade"] == "INSTITUTION GRADE").sum()))

            f1, f2, f3 = st.columns(3)
            with f1:
                direction_filter = st.multiselect(
                    "Direction", ["CE", "PE", "WAIT"], default=["CE", "PE", "WAIT"],
                    key="historical_candle_direction_filter",
                )
            with f2:
                status_options = sorted(historical_patterns["Status"].dropna().unique().tolist())
                status_filter = st.multiselect(
                    "Lifecycle status", status_options, default=status_options,
                    key="historical_candle_status_filter",
                )
            with f3:
                minimum_reliability = st.slider(
                    "Minimum reliability", 0, 100, 40, 5,
                    key="historical_candle_reliability_filter",
                )

            filtered_patterns = historical_patterns[
                historical_patterns["Direction"].isin(direction_filter)
                & historical_patterns["Status"].isin(status_filter)
                & (historical_patterns["Reliability %"] >= minimum_reliability)
            ].copy()
            display_columns = [
                "Date", "Time", "Pattern", "Direction", "Status", "Reliability %",
                "Institutional Confirmation %", "DNA Score", "DNA Grade", "Entry",
                "After 1 Bars", "After 3 Bars", "After 5 Bars", "MFE Points",
                "MAE Points", "R Multiple", "Relative Volume", "Confirmation Evidence",
                "Failure Analysis",
            ]
            st.dataframe(filtered_patterns[display_columns], use_container_width=True, hide_index=True)
            st.download_button(
                "Download evaluated pattern history (CSV)",
                filtered_patterns.drop(columns=["Timestamp"], errors="ignore").to_csv(index=False).encode("utf-8"),
                file_name=(
                    f"{dashboard_result.market_snapshot.selected_instrument.replace(' ', '_').lower()}"
                    "_pattern_intelligence_v752.csv"
                ),
                mime="text/csv",
            )

            st.markdown("##### Pattern Performance Statistics")
            pattern_stats = build_pattern_statistics(historical_patterns)
            if pattern_stats.empty:
                st.info("More completed forward candles are required before performance statistics can be calculated.")
            else:
                st.dataframe(pattern_stats, use_container_width=True, hide_index=True)

            st.markdown("##### Pattern Replay & Evidence Locker")
            replay_options = filtered_patterns["Pattern ID"].tolist()
            if replay_options:
                label_lookup = {
                    row["Pattern ID"]: f"{row['Date']} {row['Time']} • {row['Pattern']} • {row['Direction']} • {row['Status']}"
                    for _, row in filtered_patterns.iterrows()
                }
                selected_id = st.selectbox(
                    "Select a detected pattern", replay_options,
                    format_func=lambda value: label_lookup.get(value, value),
                    key="historical_pattern_replay_selection",
                )
                selected = historical_patterns[historical_patterns["Pattern ID"] == selected_id].iloc[0]
                evidence1, evidence2, evidence3, evidence4 = st.columns(4)
                evidence1.metric("Pattern", selected["Pattern"], selected["Status"])
                evidence2.metric("Confirmation", f"{selected['Institutional Confirmation %']:.0f}%", selected["Confirmation Evidence"])
                evidence3.metric("MFE / MAE", f"{selected['MFE Points'] if pd.notna(selected['MFE Points']) else '-'} / {selected['MAE Points'] if pd.notna(selected['MAE Points']) else '-'}")
                evidence4.metric("R Multiple", f"{selected['R Multiple']:.2f}R" if pd.notna(selected["R Multiple"]) else "Pending")

                if selected.get("Failure Analysis"):
                    st.warning("Failure analysis: " + str(selected["Failure Analysis"]))
                st.caption("Detection evidence: " + str(selected["Evidence"]))

                replay_df = historical_pattern_candles.copy() if isinstance(historical_pattern_candles, pd.DataFrame) else pd.DataFrame()
                if not replay_df.empty:
                    if "timestamp" not in replay_df.columns and isinstance(replay_df.index, pd.DatetimeIndex):
                        replay_df = replay_df.reset_index().rename(columns={replay_df.index.name or "index": "timestamp"})
                    replay_df["timestamp"] = pd.to_datetime(replay_df["timestamp"], errors="coerce")
                    replay_df = replay_df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
                    selected_ts = pd.to_datetime(selected["Timestamp"])
                    nearest = (replay_df["timestamp"] - selected_ts).abs().idxmin()
                    replay_window = replay_df.iloc[max(0, nearest-5): nearest+11].copy()
                    fig = go.Figure(data=[go.Candlestick(
                        x=replay_window["timestamp"], open=replay_window["open"], high=replay_window["high"],
                        low=replay_window["low"], close=replay_window["close"], name="Price"
                    )])
                    fig.add_vline(x=selected_ts, line_dash="dash", annotation_text="Pattern")
                    fig.add_hline(y=float(selected["Entry"]), line_dash="dot", annotation_text="Entry")
                    if pd.notna(selected["Target (1 ATR)"]):
                        fig.add_hline(y=float(selected["Target (1 ATR)"]), line_dash="dot", annotation_text="Target")
                    if pd.notna(selected["Stop (0.6 ATR)"]):
                        fig.add_hline(y=float(selected["Stop (0.6 ATR)"]), line_dash="dot", annotation_text="Stop")
                    fig.update_layout(height=480, xaxis_rangeslider_visible=False, title=label_lookup[selected_id])
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No patterns match the selected filters for replay.")

    structure_rows = structure_result.metadata.get("structures", [])
    if structure_rows:
        st.markdown("#### Institutional Structures")
        st.dataframe(pd.DataFrame(structure_rows), use_container_width=True, hide_index=True)


with tab_live:
    st.markdown("## Version 7.6 — Institutional Decision Matrix & AI Trade Planner")
    with st.expander("Risk and position sizing settings", expanded=False):
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            planner_capital = st.number_input("Trading capital (₹)", min_value=0.0, value=200000.0, step=10000.0)
        with rc2:
            planner_risk_pct = st.number_input("Maximum risk per trade (%)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
        with rc3:
            planner_lot_size = st.number_input("Option lot size", min_value=1, value=25, step=1)

    trade_plan_result = AITradePlannerEngine().analyze({
        "recommendation": recommendation, "intelligence": intelligence,
        "decision_matrix_result": decision_matrix_result,
        "capital": planner_capital, "risk_pct": planner_risk_pct,
        "lot_size": planner_lot_size,
    })
    recommendation["decision_matrix"] = decision_matrix_result.metadata
    recommendation["trade_plan"] = trade_plan_result.metadata
    opportunity_result = OpportunityLifecycleEngine().analyze({
        "recommendation": recommendation, "ice_result": ice_result,
        "validation_result": validation_result, "early_warning_result": early_warning_result,
        "smi_result": smi_result, "energy_result": energy_result,
        "trade_plan_result": trade_plan_result,
    })
    recommendation["opportunity_lifecycle_v80"] = opportunity_result.metadata

    # Version 8.1 Historical Intelligence. Historical evidence supports the live
    # decision but can never override current validation, stability or risk gates.
    historical_long = pd.DataFrame()
    try:
        historical_long = SnapshotStore().get_history(
            dashboard_result.market_snapshot.selected_instrument,
            dashboard_result.market_snapshot.expiry,
            hours=24 * 45,
        )
    except Exception:
        historical_long = decision_history
    current_similarity_features = {
        "pcr_oi": s.get("pcr_oi", 0), "pcr_volume": s.get("pcr_volume", 0),
        "atm_iv": s.get("atm_iv", 0), "iv_skew": s.get("iv_skew", 0),
        "combined_score": intelligence.get("score", 0), "confidence": intelligence.get("confidence", 0),
        "oi_imbalance": float(df["put_oi"].sum() - df["call_oi"].sum()),
        "volume_imbalance": float(df["put_volume"].sum() - df["call_volume"].sum()),
    }
    similarity_result = HistoricalSimilarityEngine().analyze({"history": historical_long, "current": current_similarity_features})
    playbook_result = InstitutionalPlaybookEngine().analyze({
        "regime_result": regime_result, "flow_result": flow_result, "energy_result": energy_result,
        "pattern_result": pattern_result, "intelligence": intelligence, "option_result": option_result,
    })
    replay_result = MarketReplayEngine().analyze({"history": decision_history})
    report_result = ExplainableSessionReportEngine().analyze({
        "regime_result": regime_result, "smi_result": smi_result, "energy_result": energy_result,
        "similarity_result": similarity_result, "playbook_result": playbook_result,
        "recommendation": recommendation,
    })
    recommendation["historical_similarity_v81"] = similarity_result.metadata
    recommendation["institutional_playbook_v81"] = playbook_result.metadata
    recommendation["session_report_v81"] = report_result.metadata

    # Version 8.2 Decision Intelligence Core. All engines vote into one central
    # decision package. Critical live-risk checks retain veto authority.
    consensus_result = AIConsensusEngine().analyze({
        "recommendation": recommendation, "regime_result": regime_result,
        "flow_result": flow_result, "smi_result": smi_result, "energy_result": energy_result,
        "decision_matrix_result": decision_matrix_result, "candle_dna_result": candle_dna_result,
        "pattern_result": pattern_result, "similarity_result": similarity_result,
        "playbook_result": playbook_result, "validation_result": validation_result,
    })
    probability_result = TradeProbabilityEngine().analyze({
        "consensus_result": consensus_result, "similarity_result": similarity_result,
        "validation_result": validation_result,
    })
    risk_v82_result = EnhancedRiskValidationEngine().analyze({
        "recommendation": recommendation, "consensus_result": consensus_result,
        "probability_result": probability_result, "validation_result": validation_result,
        "stability_result": stability_result, "false_breakout_result": false_breakout_result,
        "confirmation_result": confirmation_result, "trade_plan_result": trade_plan_result,
    })
    reasoning_result = DecisionReasoningEngine().analyze({
        "recommendation": recommendation, "consensus_result": consensus_result,
        "risk_result": risk_v82_result,
    })
    invalidation_result = InvalidationEngine().analyze({"consensus_result": consensus_result})
    decision_package_result = DecisionPackageEngine().analyze({
        "recommendation": recommendation, "consensus_result": consensus_result,
        "probability_result": probability_result, "risk_result": risk_v82_result,
        "reasoning_result": reasoning_result, "invalidation_result": invalidation_result,
        "trade_plan_result": trade_plan_result, "regime_result": regime_result,
        "opportunity_result": opportunity_result, "playbook_result": playbook_result,
    })
    recommendation["decision_intelligence_v82"] = decision_package_result.metadata


    # Render Version 8.2 only after every Decision Intelligence result has been initialized.
    st.markdown("## Version 8.2 — Decision Intelligence Center")
    dp = decision_package_result.metadata
    cm = consensus_result.metadata
    pm = probability_result.metadata
    rm = risk_v82_result.metadata

    d1, d2, d3, d4, d5, d6 = st.columns(6)
    d1.metric("Final Decision", dp.get("recommendation", "WAIT"), dp.get("status", "WAITING"))
    d2.metric("Decision Confidence", f"{dp.get('confidence', 0):.0f}%")
    d3.metric("Leading Probability", f"{dp.get('probability', 0):.0f}%")
    d4.metric("Consensus", f"{dp.get('consensus', 0):.0f}%")
    d5.metric("Conflict", dp.get("conflict_level", "LOW"), f"{dp.get('conflict_score', 0):.0f}%")
    d6.metric("Risk", dp.get("risk_level", "HIGH"), "VETO" if dp.get("risk_veto") else "PASS")

    probs = pm.get("probabilities", {})
    pr1, pr2, pr3 = st.columns(3)
    pr1.metric("BUY CE Probability", f"{probs.get('BUY CE', 0):.1f}%")
    pr2.metric("BUY PE Probability", f"{probs.get('BUY PE', 0):.1f}%")
    pr3.metric("WAIT Probability", f"{probs.get('WAIT', 0):.1f}%")

    if dp.get("risk_veto"):
        st.error("Decision blocked by critical risk controls. Final action remains WAIT.")
    elif dp.get("recommendation") != "WAIT":
        st.success(f"{dp.get('recommendation')} passed consensus and risk validation. Confirm execution manually.")
    else:
        st.warning("WAIT — evidence is incomplete, conflicting, or below the institutional threshold.")

    left_decision, right_decision = st.columns(2)
    with left_decision:
        st.markdown("#### Engine Voting Committee")
        vote_df = pd.DataFrame(cm.get("votes", []))
        if not vote_df.empty:
            st.dataframe(vote_df, use_container_width=True, hide_index=True)
        st.markdown("#### Risk Validation")
        risk_df = pd.DataFrame(rm.get("checks", []))
        if not risk_df.empty:
            st.dataframe(risk_df, use_container_width=True, hide_index=True)
    with right_decision:
        st.markdown("#### Decision Reasoning Trace")
        for index, step in enumerate(dp.get("reasoning_trace", []), start=1):
            st.write(f"{index}. {step}")
        st.markdown("#### Invalidation Conditions")
        for rule in dp.get("invalidation", []):
            st.write("• " + rule)
        if dp.get("blockers"):
            st.markdown("#### Active Blockers")
            for blocker in dp.get("blockers", []):
                st.write("• " + blocker)

    plan82 = dp.get("entry", {}) or {}
    if plan82.get("contract"):
        with st.expander("Structured Decision Package", expanded=False):
            st.json({
                "recommendation": dp.get("recommendation"),
                "confidence": dp.get("confidence"),
                "probabilities": dp.get("probabilities"),
                "market_regime": dp.get("market_regime"),
                "opportunity_stage": dp.get("opportunity_stage"),
                "playbook": dp.get("playbook"),
                "entry": plan82,
                "stop_loss": dp.get("stop_loss"),
                "targets": dp.get("targets"),
                "evidence": dp.get("evidence"),
                "blockers": dp.get("blockers"),
            })

    with st.expander("Version 8.2 design contract", expanded=False):
        st.write("• Every intelligence engine votes into one central consensus object.")
        st.write("• Probability and confidence are displayed separately.")
        st.write("• Critical risk controls can veto any directional consensus.")
        st.write("• The decision package contains evidence, blockers, entries, targets and invalidation rules.")
        st.write("• Injection-Pinbar Bottom remains supporting Candle DNA evidence; it cannot independently create a trade.")


    try:
        if should_load:
            SnapshotStore().save_playbook_history(
                dashboard_result.market_snapshot.selected_instrument,
                dashboard_result.market_snapshot.expiry,
                playbook_result,
            )
            SnapshotStore().save_decision_audit(
                dashboard_result.market_snapshot.selected_instrument,
                dashboard_result.market_snapshot.expiry,
                recommendation, regime_result, smi_result,
                energy_result, opportunity_result, similarity_result, playbook_result, report_result,
            )
        decision_audit_history = SnapshotStore().get_decision_audit(
            dashboard_result.market_snapshot.selected_instrument,
            dashboard_result.market_snapshot.expiry,
        )
        playbook_history = SnapshotStore().get_playbook_history(
            dashboard_result.market_snapshot.selected_instrument,
            dashboard_result.market_snapshot.expiry,
            hours=24 * 7,
        )
    except Exception as exc:
        decision_audit_history = pd.DataFrame()
        playbook_history = pd.DataFrame()
        st.warning(f"Version 8.1 history could not be updated: {exc}")

    idm = decision_matrix_result.metadata
    idm1, idm2, idm3, idm4, idm5 = st.columns(5)
    idm1.metric("Decision", idm.get("decision", "WAIT"))
    idm2.metric("Institutional Score", f"{idm.get('overall_score', 0):.0f}/100")
    idm3.metric("Trade Quality", f"{idm.get('trade_quality', 0):.0f}/100", idm.get("grade", "-"))
    idm4.metric("Risk", idm.get("risk_level", "HIGH"))
    idm5.metric("Planner State", trade_plan_result.metadata.get("state", "WAIT"))

    matrix_df = pd.DataFrame(idm.get("matrix", []))
    if not matrix_df.empty:
        st.dataframe(matrix_df, use_container_width=True, hide_index=True)

    plan = trade_plan_result.metadata.get("plan")
    if plan:
        st.markdown("### AI Trade Plan")
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Selected Contract", plan.get("contract", "-"), plan.get("state", "WAITING"))
        p2.metric("Entry Zone", f"₹{plan.get('entry_low', 0):.2f} – ₹{plan.get('entry_high', 0):.2f}")
        p3.metric("Stop Loss", f"₹{plan.get('stop_loss', 0):.2f}")
        p4.metric("Position", f"{plan.get('lots', 0)} lot(s)", f"Qty {plan.get('quantity', 0)}")

        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Target 1", f"₹{plan.get('target1', 0):.2f}", "1.25R")
        t2.metric("Target 2", f"₹{plan.get('target2', 0):.2f}", "2.0R")
        t3.metric("Target 3", f"₹{plan.get('target3', 0):.2f}", "3.0R")
        t4.metric("Planned Exposure", f"₹{plan.get('exposure', 0):,.0f}", f"Risk ₹{plan.get('risk_amount', 0):,.0f}")

        if plan.get("state") == "TRIGGERED":
            st.success("Existing safety gates and institutional confirmation support this planning setup.")
        else:
            req = plan.get("trigger_requirements", [])
            st.warning("WAITING — " + (" • ".join(req) if req else "Confirmation conditions are still developing."))

        ranking_rows = trade_plan_result.metadata.get("rankings", [])
        if ranking_rows:
            st.markdown("#### AI Strike Selector")
            st.dataframe(pd.DataFrame(ranking_rows), use_container_width=True, hide_index=True)
        with st.expander("Dynamic exit intelligence", expanded=False):
            for rule in plan.get("exit_rules", []):
                st.write("• " + rule)
            st.caption("Planning levels are analytical estimates, not guaranteed fills or investment advice.")

    st.markdown("## Version 8.0 — Core Institutional Intelligence")
    regime = regime_result.metadata
    smi = smi_result.metadata
    energy = energy_result.metadata
    opportunity = opportunity_result.metadata

    v81, v82, v83, v84, v85 = st.columns(5)
    v81.metric("Market Regime", regime.get("regime", "Unknown"), f"{regime.get('confidence', 0):.0f}%")
    v82.metric("Regime Direction", regime.get("direction", "NEUTRAL"))
    v83.metric("Smart Money Index", f"{smi.get('smi', 0):.0f}/100", smi.get("label", "WEAK"))
    v84.metric("Market Energy", f"{energy.get('energy', 0):.0f}%", energy.get("state", "LOW"))
    v85.metric("Opportunity Stage", opportunity.get("stage", "SCANNING"), f"Next: {opportunity.get('next_stage', '—')}")

    if opportunity.get("stage") == "READY":
        st.success(f"Opportunity READY for {opportunity.get('side', 'WAIT')} review. Existing risk and validation gates remain mandatory.")
    elif opportunity.get("stage") in {"ACCUMULATION", "VALIDATION"}:
        st.warning(f"Opportunity {opportunity.get('stage')}: {opportunity.get('probability', 0):.0f}% evidence score. Do not enter before READY.")
    else:
        st.info("Opportunity lifecycle is SCANNING. The system is waiting for stronger multi-engine alignment.")

    core_left, core_right = st.columns(2)
    with core_left:
        st.markdown("#### Market Regime Ranking")
        regime_df = pd.DataFrame(regime.get("rankings", []))
        if not regime_df.empty:
            st.dataframe(regime_df, use_container_width=True, hide_index=True)
        st.markdown("#### Smart Money Components")
        smi_df = pd.DataFrame(smi.get("components", []))
        if not smi_df.empty:
            st.dataframe(smi_df, use_container_width=True, hide_index=True)
    with core_right:
        st.markdown("#### Market Energy Components")
        energy_df = pd.DataFrame(energy.get("components", []))
        if not energy_df.empty:
            st.dataframe(energy_df, use_container_width=True, hide_index=True)
        st.markdown("#### Opportunity Lifecycle")
        lifecycle_df = pd.DataFrame(opportunity.get("lifecycle", []))
        if not lifecycle_df.empty:
            st.dataframe(lifecycle_df, use_container_width=True, hide_index=True)
        for requirement in opportunity.get("requirements", []):
            st.write("• " + requirement)

    with st.expander("Version 8.0 design contract", expanded=False):
        st.write("• Market Regime answers: what type of session is active?")
        st.write("• Smart Money Index answers: how strongly are institutional signals aligned?")
        st.write("• Market Energy answers: does the market have enough force for follow-through?")
        st.write("• Opportunity Lifecycle answers: where is the setup between scanning and readiness?")
        st.write("• None of these engines can bypass the existing false-breakout, stability, flow-validation or risk gates.")


with tab_explorer:
    st.markdown("## Version 8.1 — Historical Intelligence")
    similarity = similarity_result.metadata
    playbook = playbook_result.metadata
    report = report_result.metadata
    replay = replay_result.metadata
    hi1, hi2, hi3, hi4, hi5 = st.columns(5)
    hi1.metric("Similarity Status", similarity.get("status", "WARMING UP"))
    hi2.metric("Top Similarity", f"{similarity_result.score:.0f}%", similarity.get("historical_vote", "WAIT"))
    hi3.metric("Sessions Scanned", int(similarity.get("sessions_scanned", 0)))
    hi4.metric("Active Playbook", playbook.get("primary", {}).get("Playbook", "Developing"), f"{playbook_result.score:.0f}%")
    hi5.metric("Session Report Grade", report.get("grade", "D"))

    st.info(report.get("report", "Historical intelligence is warming up."))

    hist_left, hist_right = st.columns(2)
    with hist_left:
        st.markdown("#### Historical Similarity Matches")
        similarity_df = pd.DataFrame(similarity.get("matches", []))
        if similarity_df.empty:
            st.info("Store snapshots across at least two trading sessions to activate similarity matching.")
        else:
            st.dataframe(similarity_df, use_container_width=True, hide_index=True)
            st.download_button("Export similarity matches", similarity_df.to_csv(index=False), "itos_v8_1_similarity.csv", "text/csv")
        st.markdown("#### Institutional Playbook Ranking")
        playbook_df = pd.DataFrame(playbook.get("rankings", []))
        if not playbook_df.empty:
            st.dataframe(playbook_df, use_container_width=True, hide_index=True)
    with hist_right:
        st.markdown("#### Market Replay — Material Events")
        replay_df = pd.DataFrame(replay.get("events", []))
        if replay_df.empty:
            st.info("Replay events will appear as stored market states, confidence or price change materially.")
        else:
            st.dataframe(replay_df, use_container_width=True, hide_index=True)
        st.markdown("#### Decision Audit")
        if decision_audit_history.empty:
            st.info("Decision audit records are created on each market-intelligence refresh.")
        else:
            audit_view = decision_audit_history.drop(columns=["report"], errors="ignore").head(50)
            st.dataframe(audit_view, use_container_width=True, hide_index=True)
            st.download_button("Export decision audit", decision_audit_history.to_csv(index=False), "itos_v8_1_decision_audit.csv", "text/csv")

    if not playbook_history.empty:
        with st.expander("Playbook history — last 7 days", expanded=False):
            st.dataframe(playbook_history, use_container_width=True, hide_index=True)

    with st.expander("Version 8.1 design contract", expanded=False):
        st.write("• Historical Similarity answers: have we seen a comparable session before?")
        st.write("• Decision Audit answers: exactly what did the system know when it made the recommendation?")
        st.write("• Institutional Playbooks answer: which recurring market behaviour best describes the live session?")
        st.write("• Market Replay answers: how did price, state and confidence evolve during the session?")
        st.write("• Session Reports translate the evidence into plain English without claiming certainty.")
        st.write("• Historical evidence is advisory and cannot override live validation, false-breakout or risk controls.")


with tab_live:
    st.markdown("## Version 7.7 — Institutional Flow Engine")
    flow = flow_result.metadata
    ice = ice_result.metadata
    valid = validation_result.metadata
    early = early_warning_result.metadata

    f1, f2, f3, f4, f5 = st.columns(5)
    f1.metric("Flow State", flow.get("flow_state", "WARMING UP"))
    f2.metric("Institutional Confidence", f"{ice.get('confidence', 0):.0f}%", ice.get("label", "WEAK"))
    f3.metric("Signal Validation", valid.get("decision", "WAIT"), f"{valid.get('passed', 0)}/{valid.get('total', 6)} controls")
    f4.metric("Early Warning", early.get("state", "NO SETUP"))
    f5.metric("Expected Trigger", early.get("estimated_trigger", "Not available"), f"{early.get('probability', 0):.0f}% probability")

    if flow.get("snapshot_count", 0) < flow.get("minimum_snapshots", 4):
        st.info(f"Flow engine is warming up: {flow.get('snapshot_count', 0)} stored snapshot(s). Refresh until at least {flow.get('minimum_snapshots', 4)} minute snapshots are available.")
    elif valid.get("validated"):
        st.success(f"Version 7.7 flow validation supports {valid.get('decision')}.")
    elif "EARLY" in early.get("state", ""):
        st.warning(f"{early.get('state')} — prepare the contract, but wait for all safety controls. Estimated confirmation window: {early.get('estimated_trigger')}.")
    else:
        st.warning("Institutional evidence is mixed. The disciplined action is WAIT.")

    flow_cols = st.columns(6)
    flow_cols[0].metric("Put Flow", f"{flow.get('put_flow_score', 0):.0f}/100")
    flow_cols[1].metric("Call Flow", f"{flow.get('call_flow_score', 0):.0f}/100")
    flow_cols[2].metric("Net Bullish Flow", f"{flow.get('net_bullish_flow', 0):+.0f}")
    flow_cols[3].metric("OI Momentum", f"{flow.get('oi_momentum', 0):+,.0f}")
    flow_cols[4].metric("OI Acceleration", f"{flow.get('oi_acceleration', 0):+,.1f}")
    flow_cols[5].metric("IV Expansion", f"{flow.get('iv_expansion', 0):+.3f}")

    left_flow, right_flow = st.columns(2)
    with left_flow:
        st.markdown("#### Institutional Confidence Contributions")
        contribution_df = pd.DataFrame(ice.get("contributions", []))
        if not contribution_df.empty:
            st.dataframe(contribution_df, use_container_width=True, hide_index=True)
        st.markdown("#### Signal Validation Framework")
        validation_df = pd.DataFrame(valid.get("checks", []))
        if not validation_df.empty:
            st.dataframe(validation_df, use_container_width=True, hide_index=True)
    with right_flow:
        st.markdown("#### Liquidity / OI Heatmap")
        heatmap_df = pd.DataFrame(flow.get("heatmap", []))
        if not heatmap_df.empty:
            heatmap_plot = go.Figure()
            heatmap_plot.add_bar(x=heatmap_df["Strike"].astype(str), y=heatmap_df["Call OI"], name="Call OI")
            heatmap_plot.add_bar(x=heatmap_df["Strike"].astype(str), y=heatmap_df["Put OI"], name="Put OI")
            heatmap_plot.update_layout(barmode="stack", height=360, xaxis_title="Strike", yaxis_title="Open Interest")
            st.plotly_chart(heatmap_plot, use_container_width=True)
        else:
            st.info("Strike heatmap will appear after option-chain snapshots are stored.")
        wall = flow.get("gamma_wall")
        if wall:
            st.metric("Gamma Wall", f"{wall.get('strike', 0):.0f}", f"Strength {wall.get('strength', 0):.0f}/100")

    st.markdown("#### Institutional Timeline")
    timeline_df = pd.DataFrame(flow.get("timeline", []))
    if not timeline_df.empty:
        st.dataframe(timeline_df, use_container_width=True, hide_index=True)
    else:
        st.info("Timeline needs multiple stored snapshots. Keep SQLite snapshot storage enabled and refresh during market hours.")

    with st.expander("How Version 7.7 protects against false confidence", expanded=False):
        st.write("• Flow scores measure change and acceleration, not only static OI.")
        st.write("• ICE combines flow with price, VWAP, volume, patterns, cycle and institutional confirmation.")
        st.write("• Early warnings are preparation alerts—not BUY instructions.")
        st.write("• BUY remains blocked until the signal-validation controls pass and previous safety gates remain healthy.")
        st.caption("This platform is analytical decision support. Options trading carries substantial risk; validate with paper trading before live use.")

    st.markdown("#### Institutional Radar")
    rad1, rad2, rad3, rad4 = st.columns(4)
    rad1.metric("Buying Pressure", f"{radar_result.metadata.get('buying_pressure', 0):.0f}/100")
    rad2.metric("Selling Pressure", f"{radar_result.metadata.get('selling_pressure', 0):.0f}/100")
    rad3.metric("Call Writing", f"{radar_result.metadata.get('call_writing', 0):.0f}/100")
    rad4.metric("Put Writing", f"{radar_result.metadata.get('put_writing', 0):.0f}/100")

    st.markdown("#### Institutional Checklist")
    check_df = pd.DataFrame(readiness_result.metadata.get("checks", []))
    if not check_df.empty:
        check_df["Status"] = check_df["passed"].map({True: "✅ PASS", False: "🟡 WAIT"})
        checklist_view = check_df[["name", "score", "Status", "requirement"]].copy()
        checklist_view.columns = ["Control", "Score", "Status", "Requirement"]
        st.dataframe(checklist_view, use_container_width=True, hide_index=True)
    if readiness_result.metadata.get("missing"):
        st.warning("Waiting for: " + " • ".join(readiness_result.metadata["missing"]))
    else:
        st.success("All Version 7.1 institutional readiness controls are healthy.")

    st.markdown("#### Pattern Recognition")
    primary_pattern = pattern_result.metadata.get("primary_pattern", {})
    pat1, pat2, pat3 = st.columns(3)
    pat1.metric("Primary Pattern", primary_pattern.get("name", "None"))
    pat2.metric("Pattern Confidence", f"{primary_pattern.get('confidence', 0):.0f}%")
    pat3.metric("Pattern Vote", pattern_result.vote)
    pattern_rows = pattern_result.metadata.get("patterns", [])
    if pattern_rows:
        with st.expander("View detected and conflicting patterns", expanded=False):
            st.dataframe(pd.DataFrame(pattern_rows), use_container_width=True, hide_index=True)

    headline, probability = st.columns([2, 1])
    with headline:
        st.subheader(f"{state_icon(intelligence['state'])} {intelligence['state']}")
        st.write(f"**Decision:** {intelligence['action']}")
        if intelligence["no_trade"]:
            st.warning(" • ".join(intelligence["no_trade_reasons"]))
        elif intelligence["agreement"]:
            st.success("Option-chain positioning and underlying price action are aligned.")
    with probability:
        q1, q2 = st.columns(2)
        q1.metric("Bullish probability", f"{intelligence['bullish_probability']:.0f}%")
        q2.metric("Bearish probability", f"{intelligence['bearish_probability']:.0f}%")
        st.metric("Base model confidence", f"{intelligence['confidence']:.0f}%")

    st.subheader("Institutional Market Cycle & Recommendation Stability")
    cycle1, cycle2, cycle3, cycle4 = st.columns(4)
    cycle1.metric("Current phase", cycle_meta.get("phase", "Unknown"))
    cycle2.metric("Phase confidence", f"{cycle_meta.get('phase_confidence', 0):.1f}%")
    cycle3.metric("Manipulation score", f"{cycle_meta.get('manipulation_score', 0):.1f}/100")
    cycle4.metric("Cycle vote", cycle_result.vote)

    stable1, stable2, stable3, stable4 = st.columns(4)
    stable1.metric("Stability score", f"{stability_meta.get('stability_score', 0):.1f}/100")
    stable2.metric("Stability label", stability_meta.get("label", "Unknown"))
    stable3.metric("Stability trend", stability_meta.get("trend", "Unknown"))
    stable4.metric("Direction changes", int(stability_meta.get("direction_changes", 0)))

    st.markdown("#### Market Status")
    status_location = market_location if market_location is not None else None
    status_volume = volume_structure if volume_structure is not None else None
    status_positioning = positioning_intelligence if positioning_intelligence is not None else None
    flow_meta = getattr(flow_result, "metadata", {}) or {}
    status_values = [
        ("Location", getattr(status_location, "zone", "Unavailable")),
        ("Location score", f"{status_location.location_score:.1f}" if status_location else "Unavailable"),
        ("Price", getattr(status_volume, "price_direction", "Unavailable")),
        ("Volume", getattr(status_volume, "volume_direction", "Unavailable")),
        ("Confirmation", getattr(status_volume, "volume_confirmation", "Unavailable")),
        ("Institutional flow", flow_meta.get("direction", flow_meta.get("flow", "Unavailable"))),
        ("Interpretation", getattr(status_volume, "interpretation", "Unavailable")),
        ("Confidence", f"{status_volume.confidence:.0f}%" if status_volume else "Unavailable"),
        ("Positioning", status_positioning.dominant_state if status_positioning and status_positioning.dominant_state != "UNAVAILABLE" else "Not available yet"),
        ("Meaning", (
            max((status_positioning.futures, status_positioning.options), key=lambda item: item.confidence).meaning
            if status_positioning and status_positioning.dominant_state != "UNAVAILABLE"
            else "Not available yet"
        )),
    ]
    for column, (label, value) in zip(st.columns(10), status_values):
        column.metric(label, str(value).replace("_", " ").title())
    status_manipulation = manipulation_intelligence if manipulation_intelligence is not None else None
    if status_manipulation and status_manipulation.state != "UNAVAILABLE":
        manipulation_status = [
            ("Manipulation Risk", status_manipulation.risk_label),
            ("Primary State", status_manipulation.display_label),
            ("Bull-Trap Risk", f"{status_manipulation.bull_trap_risk:.0f}%"),
            ("Bear-Trap Risk", f"{status_manipulation.bear_trap_risk:.0f}%"),
            ("Breakout Quality", f"{status_manipulation.breakout_quality:.0f}%"),
        ]
        for column, (label, value) in zip(st.columns(5), manipulation_status):
            column.metric(label, value)
        st.caption(f"Meaning: ({status_manipulation.meaning})")
    else:
        st.caption("Manipulation: Not available yet")
    status_evidence = institutional_evidence if institutional_evidence is not None else None
    if status_evidence and status_evidence.bias != "UNAVAILABLE":
        evidence_status = [
            ("Institutional Bias", status_evidence.display_label),
            ("Institutional Confidence", f"{status_evidence.confidence:.0f}%"),
            ("Dominant Theme", status_evidence.dominant_theme.replace("_", " ").title()),
            ("Evidence Quality", f"{status_evidence.evidence_quality:.0f}%"),
            ("Primary Contradiction", status_evidence.contradictions[0] if status_evidence.contradictions else "None"),
        ]
        for column, (label, value) in zip(st.columns(5), evidence_status):
            column.metric(label, value)
    else:
        st.caption("Institutional Evidence: Not available yet")
    status_confidence = decision_confidence if decision_confidence is not None else None
    if status_confidence and status_confidence.grade != "UNAVAILABLE":
        confidence_status = [
            ("Decision Confidence", f"{status_confidence.score:.0f}%"),
            ("Grade", status_confidence.grade.replace("_", " ").title()),
            ("Setup Quality", status_confidence.setup_quality.replace("_", " ").title()),
            ("Ranking Ready", "Yes" if status_confidence.ranking_ready else "No"),
            ("Primary Reason", status_confidence.primary_reason),
            ("Primary Blocker", status_confidence.primary_blocker),
        ]
        for column, (label, value) in zip(st.columns(6), confidence_status):
            column.metric(label, value)
    else:
        st.caption("Decision Confidence: Not available yet")
    status_validation = decision_confidence_validation if decision_confidence_validation is not None else None
    if status_validation and status_validation.trend != "UNAVAILABLE":
        validation_status = [
            ("Confidence Trend", status_validation.trend.replace("_", " ").title()),
            ("Confidence Stability", f"{status_validation.stability_score:.0f}%"),
            ("Pillar Agreement", f"{status_validation.pillar_agreement_score:.0f}%"),
            ("Ranking Eligibility", status_validation.ranking_eligibility_state.replace("CONDITIONALLY_ELIGIBLE", "CONDITIONAL").replace("_", " ").title()),
            ("Readiness Persistence", f"{status_validation.readiness_persistence:.0f}%"),
            ("Primary Change Driver", status_validation.primary_change_driver),
        ]
        for column, (label, value) in zip(st.columns(6), validation_status):
            column.metric(label, value)
    else:
        st.caption("Decision Confidence Validation: Not available yet")
    status_ranking = trade_opportunity_ranking if trade_opportunity_ranking is not None else None
    if status_ranking:
        def status_contract(candidate):
            return f"{candidate.strike:g} {candidate.option_type} — {candidate.opportunity_score:.0f}" if candidate else "None"
        ranking_status = [
            ("Option Ranking", status_ranking.ranking_state.replace("_", " ").title()),
            ("Preferred Direction", status_ranking.preferred_direction.replace("_", " ").title()),
            ("Best CE", status_contract(status_ranking.best_ce)),
            ("Best PE", status_contract(status_ranking.best_pe)),
            ("Best Overall", status_contract(status_ranking.best_overall)),
        ]
        for column, (label, value) in zip(st.columns(5), ranking_status):
            column.metric(label, value)
        if not status_ranking.ranking_eligible:
            st.caption(f"Option Ranking Reason: {status_ranking.eligibility_reason}")
    else:
        st.caption("Option Ranking: Unavailable")

    with st.expander("Market Location & Transition", expanded=False):
        if market_location is None:
            st.info("Market location data is unavailable.")
        else:
            location_columns = st.columns(5)
            location_columns[0].metric("Zone", market_location.zone)
            location_columns[1].metric("Location score", f"{market_location.location_score:.1f}/100")
            location_columns[2].metric("Transition", market_location.transition)
            location_columns[3].metric("Direction", market_location.direction)
            location_columns[4].metric("Confidence", f"{market_location.confidence:.0f}%")
            st.write(
                f"Support: {market_location.support_level if market_location.support_level is not None else '—'} • "
                f"Resistance: {market_location.resistance_level if market_location.resistance_level is not None else '—'} • "
                f"Distance to support: {market_location.distance_to_support if market_location.distance_to_support is not None else '—'} • "
                f"Distance to resistance: {market_location.distance_to_resistance if market_location.distance_to_resistance is not None else '—'}"
            )
            if market_location.quality_flags:
                st.caption("Quality flags: " + ", ".join(market_location.quality_flags))
            for explanation in market_location.explanations:
                st.write(f"• {explanation}")

    with st.expander("Price & Volume Behaviour", expanded=False):
        if (
            volume_structure is None
            or getattr(volume_structure, "volume_confirmation", "UNAVAILABLE")
            == "UNAVAILABLE"
        ):
            st.info("Price and volume behaviour is unavailable.")
        else:
            def display_value(value, suffix=""):
                return "Unavailable" if value is None else f"{value}{suffix}"
            def display_state(value):
                if value in (None, "UNKNOWN", "UNAVAILABLE"):
                    return "Unavailable"
                return str(value).replace("_", " ").title()
            st.markdown("**Measured facts**")
            facts = {
                "Market Location": display_state(getattr(market_location, "zone", None)),
                "Price Direction": display_state(volume_structure.price_direction),
                "Price Strength": display_value(volume_structure.price_strength, "/100"),
                "Price Change Percent": display_value(volume_structure.price_change_percent, "%"),
                "Price Slope": display_value(volume_structure.price_slope),
                "Volume Direction": display_state(volume_structure.volume_direction),
                "Volume Strength": display_value(volume_structure.volume_strength, "/100"),
                "Volume Change Percent": display_value(volume_structure.volume_change_percent, "%"),
                "Relative Volume": display_value(volume_structure.relative_volume, "x"),
                "Volume Confirmation": display_state(volume_structure.volume_confirmation),
                "Effort vs Result": display_state(volume_structure.effort_result_state),
            }
            st.table(pd.DataFrame(facts.items(), columns=["Measure", "Value"]))
            st.markdown("**Location-aware interpretation**")
            interpreted = {
                "Interpretation": display_state(volume_structure.interpretation),
                "Direction": display_state(volume_structure.direction),
                "Accumulation Score": volume_structure.accumulation_score,
                "Distribution Score": volume_structure.distribution_score,
                "Absorption Score": volume_structure.absorption_score,
                "Exhaustion Score": volume_structure.exhaustion_score,
                "Confidence": f"{volume_structure.confidence:.0f}%",
                "Quality Flags": ", ".join(volume_structure.quality_flags) or "None",
            }
            st.table(pd.DataFrame(interpreted.items(), columns=["Interpretation", "Value"]))
            for explanation in volume_structure.explanations:
                st.write(f"• {explanation}")

    with st.expander("Positioning Intelligence", expanded=False):
        if positioning_intelligence is None or (
            positioning_intelligence.futures.state == "UNAVAILABLE"
            and positioning_intelligence.options.state == "UNAVAILABLE"
        ):
            st.info("Positioning intelligence is unavailable.")
        else:
            def render_positioning_state(title, state):
                st.markdown(f"### {title}")
                st.write(f"**State:** {state.display_state}")
                st.write(f"**Meaning:** ({state.meaning})")
                st.write(f"**Market Impact:** {state.market_impact}")
                st.write(f"**Confidence:** {state.confidence:.0f}%")
                st.markdown("**Measured evidence**")
                for item in state.evidence or ("No confirming evidence is available yet.",):
                    st.write(f"• {item}")
                st.markdown("**Contradictions**")
                for item in state.contradictions or ("None identified.",):
                    st.write(f"• {item}")
            render_positioning_state("Futures Positioning", positioning_intelligence.futures)
            render_positioning_state("Options Positioning", positioning_intelligence.options)
            st.markdown("### Overall Positioning")
            st.write(f"**Bias:** {positioning_intelligence.overall_bias.replace('_', ' ').title()}")
            st.write(f"**Dominant State:** {positioning_intelligence.dominant_state.replace('_', ' ').title()}")
            st.write(f"**Overall Confidence:** {positioning_intelligence.overall_confidence:.0f}%")
            st.write("**Quality Flags:** " + (", ".join(positioning_intelligence.quality_flags) or "None"))
            for explanation in positioning_intelligence.explanations:
                st.write(f"• {explanation}")

    with st.expander("Compression Intelligence", expanded=False):
        if compression_intelligence is None or compression_intelligence.state == "UNAVAILABLE":
            st.info("Compression intelligence is unavailable.")
        else:
            st.caption(compression_intelligence.meaning)
            compression_columns = st.columns(4)
            compression_columns[0].metric("State", compression_intelligence.state.replace("_", " ").title())
            compression_columns[1].metric("Compression Score", f"{compression_intelligence.compression_score:.0f}%")
            compression_columns[2].metric("Energy Stored", f"{compression_intelligence.energy_stored:.0f}%")
            compression_columns[3].metric("Expansion Readiness", f"{compression_intelligence.expansion_readiness:.0f}%")
            st.write(f"**Direction:** {compression_intelligence.direction.replace('_', ' ').title()} · **Confidence:** {compression_intelligence.confidence:.0f}%")
            st.write("**Component scores:**", {"ATR": compression_intelligence.atr_compression_score, "Range": compression_intelligence.range_compression_score, "Spread": compression_intelligence.candle_spread_compression_score, "Volume": compression_intelligence.volume_compression_score, "Return volatility": compression_intelligence.volatility_compression_score, "Time": compression_intelligence.time_compression_score, "OI build": compression_intelligence.oi_build_score})
            st.write("**Raw diagnostics:**", {"Recent ATR": compression_intelligence.recent_atr, "Baseline ATR": compression_intelligence.baseline_atr, "ATR ratio": compression_intelligence.atr_ratio, "Recent range": compression_intelligence.recent_range, "Baseline range": compression_intelligence.baseline_range, "Range ratio": compression_intelligence.range_ratio, "Recent volume": compression_intelligence.recent_volume, "Baseline volume": compression_intelligence.baseline_volume, "Relative volume": compression_intelligence.relative_volume, "Duration": compression_intelligence.compression_duration})
            if compression_intelligence.evidence:
                st.write("**Evidence:**", list(compression_intelligence.evidence))
            if compression_intelligence.contradictions:
                st.write("**Contradictions:**", list(compression_intelligence.contradictions))
            if compression_intelligence.quality_flags:
                st.write("**Quality flags:**", list(compression_intelligence.quality_flags))
            for explanation in compression_intelligence.explanations:
                st.write(f"• {explanation}")

    with st.expander("Manipulation Intelligence", expanded=False):
        if manipulation_intelligence is None or manipulation_intelligence.state == "UNAVAILABLE":
            st.info("Manipulation intelligence is unavailable.")
        else:
            st.markdown("### Summary")
            st.write(f"**State:** {manipulation_intelligence.display_label}")
            st.write(f"**Meaning:** ({manipulation_intelligence.meaning})")
            st.write(f"**Market Impact:** {manipulation_intelligence.market_impact}")
            summary_values = {
                "Manipulation Probability": f"{manipulation_intelligence.manipulation_probability:.0f}%",
                "Trap Severity": f"{manipulation_intelligence.trap_severity:.0f}%",
                "Direction": manipulation_intelligence.direction.replace("_", " ").title(),
                "Confidence": f"{manipulation_intelligence.confidence:.0f}%",
            }
            st.table(pd.DataFrame(summary_values.items(), columns=["Measure", "Value"]))
            st.markdown("### Trap diagnostics")
            traps = {
                "Bull-Trap Risk": f"{manipulation_intelligence.bull_trap_risk:.0f}%",
                "Bear-Trap Risk": f"{manipulation_intelligence.bear_trap_risk:.0f}%",
                "Stop-Hunt Probability": f"{manipulation_intelligence.stop_hunt_probability:.0f}%",
                "Liquidity Sweep Detected": manipulation_intelligence.liquidity_sweep_detected,
                "Liquidity Sweep Side": manipulation_intelligence.liquidity_sweep_side,
                "False Breakout Detected": manipulation_intelligence.false_breakout_detected,
                "False Breakdown Detected": manipulation_intelligence.false_breakdown_detected,
            }
            st.table(pd.DataFrame(traps.items(), columns=["Diagnostic", "Value"]))
            st.markdown("### Quality diagnostics")
            quality = {
                "Breakout Quality": manipulation_intelligence.breakout_quality,
                "Follow-through Quality": manipulation_intelligence.follow_through_quality,
                "Rejection Score": manipulation_intelligence.rejection_score,
                "Wick Score": manipulation_intelligence.wick_score,
                "Return Inside Range": manipulation_intelligence.return_inside_range,
                "Range Re-entry Speed": manipulation_intelligence.range_reentry_speed if manipulation_intelligence.range_reentry_speed is not None else "Unavailable",
                "Confirmation Candles": manipulation_intelligence.confirmation_candles,
            }
            st.table(pd.DataFrame(quality.items(), columns=["Diagnostic", "Value"]))
            st.markdown("### Reasoning")
            for title, items, fallback in (
                ("Evidence used", manipulation_intelligence.evidence, "No confirming evidence."),
                ("Contradictions", manipulation_intelligence.contradictions, "None identified."),
                ("Quality Flags", manipulation_intelligence.quality_flags, "None."),
                ("Explanations", manipulation_intelligence.explanations, "No explanation available."),
            ):
                st.markdown(f"**{title}**")
                for item in items or (fallback,): st.write(f"• {item}")

    with st.expander("Institutional Evidence", expanded=False):
        if institutional_evidence is None or institutional_evidence.bias == "UNAVAILABLE":
            st.info("Institutional evidence is unavailable.")
        else:
            st.markdown("### Summary")
            summary = {
                "Institutional Bias": institutional_evidence.display_label,
                "Meaning": institutional_evidence.meaning,
                "Confidence": f"{institutional_evidence.confidence:.0f}%",
                "Evidence Quality": f"{institutional_evidence.evidence_quality:.0f}%",
                "Dominant Theme": institutional_evidence.dominant_theme.replace("_", " ").title(),
                "Secondary Theme": institutional_evidence.secondary_theme.replace("_", " ").title() if institutional_evidence.secondary_theme else "None",
                "Bullish Score": institutional_evidence.bullish_score,
                "Bearish Score": institutional_evidence.bearish_score,
                "Neutral Score": institutional_evidence.neutral_score,
            }
            st.table(pd.DataFrame(summary.items(), columns=["Measure", "Value"]))
            st.markdown("### Supporting evidence")
            for title, evidence_items in (("Bullish", institutional_evidence.bullish_evidence), ("Bearish", institutional_evidence.bearish_evidence), ("Neutral", institutional_evidence.neutral_evidence)):
                st.markdown(f"**{title} evidence**")
                if evidence_items:
                    st.table(pd.DataFrame([{"Label": item.label, "Source": item.source, "Strength": item.strength, "Reliability": item.reliability, "Explanation": item.explanation} for item in evidence_items]))
                else:
                    st.write("• None identified.")
            st.markdown("### Risk and completeness")
            for title, entries in (("Contradictions", institutional_evidence.contradictions), ("Missing Evidence", institutional_evidence.missing_evidence), ("Quality Flags", institutional_evidence.quality_flags)):
                st.markdown(f"**{title}**")
                for entry in entries or ("None identified.",): st.write(f"• {entry}")
            st.markdown("### Narrative")
            st.write(institutional_evidence.narrative)

    with st.expander("Decision Confidence", expanded=False):
        if decision_confidence is None or decision_confidence.grade == "UNAVAILABLE":
            st.info("Decision confidence is unavailable.")
        else:
            st.markdown("### Summary")
            confidence_summary = {
                "Decision Confidence Score": f"{decision_confidence.score:.1f}/100",
                "Grade": decision_confidence.grade.replace("_", " ").title(),
                "Setup Quality": decision_confidence.setup_quality.replace("_", " ").title(),
                "Ranking Ready": "Yes" if decision_confidence.ranking_ready else "No",
                "Evidence Quality": f"{decision_confidence.evidence_quality:.1f}%",
                "Confidence Ceiling": f"{decision_confidence.confidence_ceiling:.1f}",
                "Critical Blocker Count": decision_confidence.critical_blocker_count,
                "Contradiction Count": decision_confidence.contradiction_count,
            }
            st.table(pd.DataFrame(confidence_summary.items(), columns=["Measure", "Value"]))
            st.markdown("### Pillars")
            st.table(pd.DataFrame([{
                "Pillar": pillar.label, "Score": pillar.score, "Weight": pillar.weight,
                "Reliability": pillar.reliability, "Contribution": pillar.contribution,
                "Explanation": pillar.explanation,
                "Quality Flags": ", ".join(pillar.quality_flags) or "None",
            } for pillar in decision_confidence.pillars]))
            st.markdown("### Decision reasoning")
            for title, entries, fallback in (
                ("Why confidence increased", decision_confidence.contributors, "No strong contributor is confirmed."),
                ("Why confidence decreased", decision_confidence.penalties, "No explicit penalty is present."),
                ("What is missing", decision_confidence.missing_confirmations, "No material confirmation is missing."),
                ("Quality Flags", decision_confidence.quality_flags, "None."),
            ):
                st.markdown(f"**{title}**")
                for entry in entries or (fallback,):
                    st.write(f"• {entry}")
            st.markdown("**Narrative**")
            st.write(decision_confidence.narrative)

    with st.expander("Decision Confidence Validation", expanded=False):
        validation = decision_confidence_validation
        if validation is None or validation.trend == "UNAVAILABLE":
            st.info("Decision confidence validation is unavailable.")
        else:
            st.markdown("### Current state")
            current_state = {
                "Current Score": f"{validation.current_score:.1f}/100",
                "Previous Score": f"{validation.previous_score:.1f}" if validation.previous_score is not None else "Unavailable",
                "Score Change": f"{validation.score_change:+.1f}" if validation.score_change is not None else "Unavailable",
                "Trend": validation.trend.replace("_", " ").title(),
                "Stability State": validation.stability_state.replace("_", " ").title(),
                "Stability Score": f"{validation.stability_score:.1f}/100",
                "Pillar Agreement": f"{validation.pillar_agreement_score:.1f}/100",
                "Ranking Ready Now": "Yes" if validation.ranking_ready_now else "No",
                "Readiness Persistence": f"{validation.readiness_persistence:.1f}%",
                "Ranking Eligibility": validation.ranking_eligibility_state.replace("_", " ").title(),
                "Validation Confidence": f"{validation.confidence:.1f}%",
            }
            st.table(pd.DataFrame(current_state.items(), columns=["Measure", "Value"]))
            st.markdown("### History summary")
            history_summary = {
                "Valid History Points": validation.valid_history_points,
                "Improving Periods": validation.improving_periods,
                "Stable Periods": validation.stable_periods,
                "Weakening Periods": validation.weakening_periods,
            }
            st.table(pd.DataFrame(history_summary.items(), columns=["Measure", "Value"]))
            st.markdown("### Change analysis")
            change_summary = {
                "Strongest Improving Pillar": validation.strongest_improving_pillar or "None",
                "Weakest Deteriorating Pillar": validation.weakest_deteriorating_pillar or "None",
                "Positive Change Drivers": " • ".join(validation.positive_change_drivers) or "None",
                "Negative Change Drivers": " • ".join(validation.negative_change_drivers) or "None",
                "New Penalties": " • ".join(validation.new_penalties) or "None",
                "Resolved Penalties": " • ".join(validation.resolved_penalties) or "None",
                "New Blockers": " • ".join(validation.new_blockers) or "None",
                "Resolved Blockers": " • ".join(validation.resolved_blockers) or "None",
            }
            st.table(pd.DataFrame(change_summary.items(), columns=["Measure", "Value"]))
            st.markdown("### Shadow comparison")
            st.write(f"**Recommendation Alignment:** {validation.recommendation_alignment.replace('_', ' ').title()}")
            st.write(validation.shadow_observation)
            st.markdown("### Reasoning")
            for title, entries in (("Quality Flags", validation.quality_flags), ("Explanations", validation.explanations)):
                st.markdown(f"**{title}**")
                for entry in entries or ("None",):
                    st.write(f"• {entry}")
            st.markdown("**Narrative**")
            st.write(validation.narrative)

    with st.expander("Trade Opportunity Ranking", expanded=False):
        ranking = trade_opportunity_ranking
        if ranking is None:
            st.info("Trade opportunity ranking is unavailable.")
        else:
            def ranking_contract(candidate):
                return f"{candidate.strike:g} {candidate.option_type} — {candidate.opportunity_score:.1f}" if candidate else "None"
            ranking_summary = {
                "Ranking State": ranking.ranking_state.replace("_", " ").title(),
                "Ranking Eligible": "Yes" if ranking.ranking_eligible else "No",
                "Eligibility Reason": ranking.eligibility_reason,
                "Preferred Direction": ranking.preferred_direction,
                "Institutional Bias": ranking.institutional_bias,
                "Decision Confidence": f"{ranking.decision_confidence:.1f}%",
                "Validation State": ranking.validation_state.replace("_", " ").title(),
                "Evaluated Contracts": ranking.evaluated_count,
                "Rejected Contracts": ranking.rejected_count,
                "Best CE": ranking_contract(ranking.best_ce),
                "Best PE": ranking_contract(ranking.best_pe),
                "Best Overall": ranking_contract(ranking.best_overall),
            }
            st.table(pd.DataFrame(ranking_summary.items(), columns=["Measure", "Value"]))
            if not ranking.ranking_eligible:
                st.info(ranking.eligibility_reason)
            else:
                def opportunity_rows(candidates):
                    return [{
                        "Rank": index, "Strike": item.strike, "Expiry": item.expiry,
                        "LTP": item.ltp, "Opportunity Score": item.opportunity_score,
                        "Grade": item.grade, "Risk": item.risk_level, "Delta": item.delta,
                        "Gamma": item.gamma, "Theta": item.theta, "IV": item.iv,
                        "OI": item.oi, "Volume": item.volume, "Spread %": item.spread_percent,
                        "Moneyness": item.moneyness,
                        "Positive Reasons": " • ".join(item.positive_reasons) or "None",
                        "Warnings": " • ".join(item.warnings) or "None",
                        "Explanation": item.explanation,
                    } for index, item in enumerate(candidates, 1)]
                st.markdown("### Top CE Opportunities")
                ce_rows = opportunity_rows(ranking.top_ce)
                st.table(pd.DataFrame(ce_rows)) if ce_rows else st.info("No eligible CE contracts.")
                st.markdown("### Top PE Opportunities")
                pe_rows = opportunity_rows(ranking.top_pe)
                st.table(pd.DataFrame(pe_rows)) if pe_rows else st.info("No eligible PE contracts.")
                st.markdown("### Rejected-contract summary")
                if ranking.rejection_reason_counts:
                    st.table(pd.DataFrame(ranking.rejection_reason_counts, columns=["Reason", "Count"]))
                    representatives = [
                        {"Contract": f"{item.strike:g} {item.option_type}", "Reasons": " • ".join(item.rejection_reasons)}
                        for item in ranking.rejected[:5]
                    ]
                    st.table(pd.DataFrame(representatives))
                else:
                    st.write("No rejected contracts.")
            st.caption("Informational only — this ranking does not alter the live recommendation or existing strike selection.")

    with st.expander("Institutional Metrics v2 Preview", expanded=False):
        if institutional_metrics is None:
            st.info("Institutional metrics are unavailable.")
        else:
            metric_values = {
                name.replace("_", " ").title(): value
                for name, value in vars(institutional_metrics).items()
                if name not in {"explanations", "quality_flags"}
            }
            st.table(pd.DataFrame(metric_values.items(), columns=["Metric", "Value"]))
            quality_flags = getattr(institutional_metrics, "quality_flags", ())
            if quality_flags:
                st.caption("Quality flags: " + ", ".join(quality_flags))

    phase_probabilities = cycle_meta.get("probabilities", {})
    if phase_probabilities:
        st.markdown("#### Market Phase Detectors")

        # Display every phase detector explicitly so users can see which engines are
        # active instead of only seeing the winning/current phase.
        detector_specs = [
            ("Compression Detector", "Compression", "WAIT"),
            ("Accumulation Detector", "Accumulation", "CE"),
            ("Manipulation Detector", "Manipulation", "BLOCK"),
            ("Bullish Expansion Detector", "Bullish Expansion", "CE"),
            ("Bearish Expansion Detector", "Bearish Expansion", "PE"),
            ("Distribution Detector", "Distribution", "PE"),
        ]
        winning_phase = cycle_meta.get("phase", "Unknown")
        detector_threshold = 20.0

        for row_start in range(0, len(detector_specs), 3):
            detector_columns = st.columns(3)
            for column, (label, phase_name, directional_vote) in zip(
                detector_columns, detector_specs[row_start:row_start + 3]
            ):
                detector_score = float(phase_probabilities.get(phase_name, 0.0) or 0.0)
                is_primary = winning_phase == phase_name
                is_active = is_primary or detector_score >= detector_threshold
                detector_status = "PRIMARY" if is_primary else ("ACTIVE" if is_active else "INACTIVE")

                with column:
                    st.metric(label, f"{detector_score:.1f}%", detector_status)
                    if phase_name == "Manipulation":
                        raw_manipulation = float(cycle_meta.get("manipulation_score", 0.0) or 0.0)
                        st.caption(
                            f"Raw manipulation risk: {raw_manipulation:.1f}/100 • "
                            + ("New entries blocked" if raw_manipulation >= 55 else "Risk below hard-block level")
                        )
                    elif directional_vote == "WAIT":
                        st.caption("Observe only until directional expansion confirms.")
                    elif directional_vote == "BLOCK":
                        st.caption("Can veto CE/PE entries when manipulation risk is high.")
                    else:
                        st.caption(f"Directional bias: {directional_vote}")

        probability_view = pd.DataFrame({
            "Detector": list(phase_probabilities),
            "Probability %": list(phase_probabilities.values()),
            "Status": [
                "PRIMARY" if name == winning_phase else ("ACTIVE" if float(phase_probabilities.get(name, 0) or 0) >= detector_threshold else "INACTIVE")
                for name in phase_probabilities
            ],
        })
        with st.expander("View detector probability table", expanded=False):
            st.dataframe(
                probability_view.sort_values("Probability %", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

    with st.expander("Why the cycle and stability engines reached this view", expanded=False):
        cwhy, swhy = st.columns(2)
        with cwhy:
            st.markdown("**Market Cycle Engine**")
            for item in cycle_result.explanation:
                st.write(f"• {item}")
        with swhy:
            st.markdown("**Recommendation Stability Engine**")
            for item in stability_result.explanation:
                st.write(f"• {item}")

    if not phase_history.empty or not stability_history.empty:
        hist1, hist2 = st.columns(2)
        with hist1:
            if not phase_history.empty:
                st.markdown("**Phase transition history**")
                phase_view = phase_history[["captured_at", "phase", "phase_confidence", "vote", "manipulation_score"]].tail(20).copy()
                phase_view.columns = ["Time", "Phase", "Confidence", "Vote", "Manipulation"]
                st.dataframe(phase_view, use_container_width=True, hide_index=True)
        with hist2:
            if not stability_history.empty:
                st.markdown("**Stability trend**")
                stability_chart = stability_history.set_index("captured_at")[["stability_score"]]
                st.line_chart(stability_chart, use_container_width=True)

    st.subheader("CE / PE Decision Engine")
    status = recommendation["status"]
    if status.startswith("BUY SETUP CONFIRMED"):
        st.success(f"### {status}")
    elif status.startswith("WATCH"):
        st.warning(f"### {status}")
    else:
        st.error(f"### {status}")

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Direction", recommendation["direction"])
    d2.metric("Model setup score", f"{recommendation['model_probability']:.0f}%")
    d3.metric("Market regime", recommendation["regime"]["name"])
    d4.metric("Relative volume", f"{recommendation['regime']['relative_volume']:.2f}×")

    st.markdown("#### Trade Readiness & Explainable Confidence")
    ready1, ready2, ready3, ready4 = st.columns(4)
    ready1.metric("Calibrated confidence", f"{recommendation['confidence']:.0f}%", recommendation['confidence_detail']['label'])
    ready2.metric("Trade quality", f"{recommendation['trade_quality']:.0f}/100")
    ready3.metric("Health score", f"{recommendation['health_score']:.0f}/100")
    ready4.metric("Lifecycle", "TRIGGERED" if recommendation["confirmed"] else ("READY / WATCH" if recommendation["passed_conditions"] >= recommendation["total_conditions"] - 1 else "WAITING"))

    confidence_detail = recommendation["confidence_detail"]

    st.markdown("#### Confidence Hierarchy")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Market confidence", f"{confidence_detail['market_confidence']:.0f}%")
    h2.metric(f"{recommendation['side']} direction confidence", f"{confidence_detail['direction_confidence']:.0f}%")
    h3.metric("Trigger confidence", f"{confidence_detail['trigger_confidence']:.0f}%")
    h4.metric("Config version", confidence_detail.get("config_version", "unknown"))

    consensus = confidence_detail.get("consensus", {})
    st.markdown(f"#### AI Consensus — {consensus.get('agreeing', 0)} of {consensus.get('total', 0)} engines agree")
    consensus_df = pd.DataFrame(consensus.get("engines", []))
    if not consensus_df.empty:
        consensus_df["Status"] = consensus_df["agrees"].map({True: "✅ AGREES", False: "⚠ NEUTRAL / CONFLICT"})
        consensus_view = consensus_df[["engine", "vote", "score", "Status"]].copy()
        consensus_view.columns = ["Engine", "Vote", "Score", "Status"]
        st.dataframe(consensus_view.style.format({"Score": "{:.1f}"}), use_container_width=True, hide_index=True)

    if not confidence_history.empty:
        st.markdown("#### Confidence Trend")
        chart_df = confidence_history.set_index("captured_at")[["market_confidence", "direction_confidence", "trigger_confidence", "calibrated_confidence"]]
        chart_df.columns = ["Market", "Direction", "Trigger", "Calibrated"]
        st.line_chart(chart_df, use_container_width=True)
        latest_delta = 0.0
        if len(confidence_history) >= 2:
            latest_delta = float(confidence_history.iloc[-1]["calibrated_confidence"] - confidence_history.iloc[-2]["calibrated_confidence"])
        trend_word = "building" if latest_delta > 1 else "fading" if latest_delta < -1 else "stable"
        st.caption(f"Latest confidence is {trend_word}: {latest_delta:+.1f} points since the previous stored refresh.")

    st.caption(
        f"Confidence range: {confidence_detail['lower_bound']:.0f}%–{confidence_detail['upper_bound']:.0f}% • "
        f"Method: {confidence_detail['method']} • Active cap: {confidence_detail['cap']:.0f}%"
    )
    with st.expander("How confidence is calculated", expanded=False):
        confidence_rows = pd.DataFrame(confidence_detail["contributions"])
        if not confidence_rows.empty:
            confidence_rows = confidence_rows[["name", "score", "weight", "points", "passed"]]
            confidence_rows.columns = ["Signal", "Signal Score", "Weight %", "Weighted Points", "Healthy"]
            st.dataframe(
                confidence_rows.style.format({
                    "Signal Score": "{:.1f}", "Weight %": "{:.0f}%", "Weighted Points": "{:.1f}"
                }),
                use_container_width=True, hide_index=True,
            )
        cgood, cbad = st.columns(2)
        with cgood:
            st.markdown("**Confidence boosters**")
            if confidence_detail["bonuses"]:
                for item in confidence_detail["bonuses"]:
                    st.write(f"✅ {item}")
            else:
                st.write("No additional confidence bonus is active.")
        with cbad:
            st.markdown("**Confidence deductions / caps**")
            if confidence_detail["deductions"]:
                for item in confidence_detail["deductions"]:
                    st.write(f"⚠️ {item}")
            else:
                st.write("No confidence deduction is active.")

    progress_value = recommendation["passed_conditions"] / max(recommendation["total_conditions"], 1)
    st.progress(progress_value, text=f"Trigger countdown: {recommendation['passed_conditions']} of {recommendation['total_conditions']} conditions complete")

    component_cols = st.columns(len(recommendation["component_scores"]))
    for idx, (name, value) in enumerate(recommendation["component_scores"].items()):
        component_cols[idx].metric(name, f"{value:.0f}")

    check_left, check_right = st.columns(2)
    with check_left:
        st.markdown("**Trigger checklist**")
        for item in recommendation["condition_checklist"]:
            icon = "✅" if item["passed"] else "🟡"
            st.write(f"{icon} {item['name']} — {item['detail']}")
    with check_right:
        st.markdown("**What is still missing?**")
        if recommendation["missing_conditions"]:
            for item in recommendation["missing_conditions"]:
                st.write(f"• {item}")
        else:
            st.success("Nothing missing. The setup has passed all trigger conditions.")

    best = recommendation.get("best")
    if best:
        st.markdown(f"#### Best-ranked contract: **{best['contract']}**")
        t1, t2, t3, t4, t5 = st.columns(5)
        t1.metric("Contract score", f"{best['score']:.0f}/100")
        t2.metric("Entry trigger", f"₹{best['entry_trigger']:.2f}")
        t3.metric("Stop-loss", f"₹{best['stop_loss']:.2f}")
        t4.metric("Target 1", f"₹{best['target1']:.2f}")
        t5.metric("Target 2", f"₹{best['target2']:.2f}")
        st.caption(
            f"Delta {best['delta']:.2f} • Spread {best['spread_pct']:.2f}% • "
            f"Volume {compact_number(best['volume'])} • OI {compact_number(best['oi'])}"
        )

    explain_left, explain_right = st.columns(2)
    with explain_left:
        st.markdown("**Confirmation evidence**")
        for reason in recommendation["reasons"][:7]:
            st.write(f"• {reason}")
    with explain_right:
        st.markdown("**Why the engine may still wait**")
        if recommendation["blockers"]:
            for blocker in recommendation["blockers"]:
                st.write(f"• {blocker}")
        else:
            st.write("• No active blocker passed to the decision layer.")

    def show_top_trade_table(title: str, trades: pd.DataFrame) -> None:
        st.markdown(f"#### {title}")
        if trades.empty:
            st.info("No contract currently passes the liquidity, spread and delta filters.")
            return

        view = trades[[
            "trade_state", "strike", "premium", "entry_trigger", "stop_loss",
            "target1", "target2", "candidate_confidence", "confidence_band", "final_score", "flow_score", "liquidity_score",
            "spread_pct", "delta_abs", "volume", "oi", "oi_change"
        ]].copy()
        view.columns = [
            "Status", "Strike", "LTP", "Entry Trigger", "Stop-Loss",
            "Target 1", "Target 2", "Confidence", "Confidence Band", "Score", "Flow", "Liquidity",
            "Spread %", "Abs Delta", "Volume", "OI", "OI Change"
        ]

        def color_trade_state(row: pd.Series) -> list[str]:
            background = "background-color: #d1fae5; color: #065f46; font-weight: 700;" if row["Status"] == "TRIGGERED" else "background-color: #fef3c7; color: #92400e; font-weight: 700;"
            return [background] * len(row)

        formatted = view.style.apply(color_trade_state, axis=1).format({
            "Strike": "{:.0f}",
            "LTP": "₹{:.2f}",
            "Entry Trigger": "₹{:.2f}",
            "Stop-Loss": "₹{:.2f}",
            "Target 1": "₹{:.2f}",
            "Target 2": "₹{:.2f}",
            "Confidence": "{:.1f}%",
            "Score": "{:.1f}",
            "Flow": "{:.1f}",
            "Liquidity": "{:.1f}",
            "Spread %": "{:.2f}",
            "Abs Delta": "{:.2f}",
            "Volume": "{:,.0f}",
            "OI": "{:,.0f}",
            "OI Change": "{:,.0f}",
        })
        st.dataframe(formatted, use_container_width=True, hide_index=True)

    st.markdown("### Top 5 CE and PE Trade Candidates")
    st.caption("Green = setup triggered by the decision engine. Yellow = candidate is ranked but confirmation is still pending.")
    show_top_trade_table("Top 5 CE Trades", recommendation["ce_top5"])
    st.divider()
    show_top_trade_table("Top 5 PE Trades", recommendation["pe_top5"])

    st.caption(recommendation["note"])

    st.markdown("### Live Trade Lifecycle")
    active_lifecycle = trade_history[trade_history["status"] == "ACTIVE"].copy() if not trade_history.empty else pd.DataFrame()
    if active_lifecycle.empty:
        st.info("No active paper trade. Triggered candidates will move through TRIGGERED → ACTIVE → TARGET/STOP → COMPLETED.")
    else:
        active_lifecycle["Progress to T1 %"] = ((active_lifecycle["current_ltp"] - active_lifecycle["entry_price"]) / (active_lifecycle["target1"] - active_lifecycle["entry_price"]).replace(0, pd.NA) * 100).clip(lower=-100, upper=150)
        lifecycle_view = active_lifecycle[["contract", "opened_at", "entry_price", "current_ltp", "stop_loss", "target1", "target2", "Progress to T1 %"]].copy()
        lifecycle_view.columns = ["Contract", "Triggered At", "Entry", "Current", "Stop-Loss", "Target 1", "Target 2", "Progress to T1 %"]
        st.dataframe(lifecycle_view, use_container_width=True, hide_index=True)

with tab_explorer:
    st.markdown("### Historical Trade Tracker")
    st.caption(
        "Yellow = active trade, green = completed successfully at Target 1, "
        "red = completed after stop-loss. Outcomes use the latest LTP observed at each refresh."
    )

    stat_cols = st.columns(8)
    stat_cols[0].metric("Total triggered", int(trade_stats["total"]))
    stat_cols[1].metric("Active", int(trade_stats["active"]))
    stat_cols[2].metric("Successful", int(trade_stats["success"]))
    stat_cols[3].metric("Failed", int(trade_stats["failure"]))
    stat_cols[4].metric("Success rate", f"{trade_stats['success_rate']:.1f}%")
    stat_cols[5].metric("Avg winner", f"{trade_stats['avg_winner']:+.1f}%")
    stat_cols[6].metric("Avg loser", f"{trade_stats['avg_loser']:+.1f}%")
    stat_cols[7].metric("Profit factor", f"{trade_stats['profit_factor']:.2f}")

    if trade_history.empty:
        st.info("No triggered trades have been recorded yet. A trade will be added automatically when a candidate turns green.")
    else:
        history_view = trade_history[[
            "status", "outcome", "opened_at", "closed_at", "contract",
            "entry_price", "current_ltp", "stop_loss", "target1", "target2",
            "max_ltp", "min_ltp", "pnl_points", "pnl_percent",
            "signal_score", "confidence", "market_regime", "trade_quality", "health_score", "close_reason"
        ]].copy()
        history_view["display_status"] = history_view.apply(
            lambda row: "ACTIVE" if row["status"] == "ACTIVE" else str(row["outcome"] or "COMPLETED"),
            axis=1,
        )
        history_view = history_view[[
            "display_status", "opened_at", "closed_at", "contract",
            "entry_price", "current_ltp", "stop_loss", "target1", "target2",
            "max_ltp", "min_ltp", "pnl_points", "pnl_percent",
            "signal_score", "confidence", "market_regime", "trade_quality", "health_score", "close_reason"
        ]]
        history_view.columns = [
            "Result", "Triggered At", "Completed At", "Contract",
            "Entry", "Latest/Exit", "Stop-Loss", "Target 1", "Target 2",
            "Best LTP", "Lowest LTP", "P&L Points", "P&L %",
            "Signal Score", "Confidence", "Market Regime", "Trade Quality", "Health Score", "Completion Reason"
        ]

        def color_history_row(row: pd.Series) -> list[str]:
            if row["Result"] == "SUCCESS":
                css = "background-color: #d1fae5; color: #065f46; font-weight: 700;"
            elif row["Result"] == "FAILURE":
                css = "background-color: #fee2e2; color: #991b1b; font-weight: 700;"
            else:
                css = "background-color: #fef3c7; color: #92400e; font-weight: 700;"
            return [css] * len(row)

        history_styled = history_view.style.apply(color_history_row, axis=1).format({
            "Triggered At": lambda value: value.strftime("%d-%b %H:%M:%S") if pd.notna(value) else "—",
            "Completed At": lambda value: value.strftime("%d-%b %H:%M:%S") if pd.notna(value) else "—",
            "Entry": "₹{:.2f}",
            "Latest/Exit": "₹{:.2f}",
            "Stop-Loss": "₹{:.2f}",
            "Target 1": "₹{:.2f}",
            "Target 2": "₹{:.2f}",
            "Best LTP": "₹{:.2f}",
            "Lowest LTP": "₹{:.2f}",
            "P&L Points": lambda value: f"{value:+.2f}" if pd.notna(value) else "—",
            "P&L %": lambda value: f"{value:+.2f}%" if pd.notna(value) else "—",
            "Signal Score": "{:.1f}",
            "Confidence": "{:.1f}%",
            "Trade Quality": lambda value: f"{value:.0f}/100" if pd.notna(value) else "—",
            "Health Score": lambda value: f"{value:.0f}/100" if pd.notna(value) else "—",
        })
        st.dataframe(history_styled, use_container_width=True, hide_index=True)

        csv_data = history_view.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download trade history CSV",
            data=csv_data,
            file_name=(
                f"{dashboard_result.market_snapshot.selected_instrument.replace(' ', '_')}_"
                f"{dashboard_result.market_snapshot.expiry}_trade_history.csv"
            ),
            mime="text/csv",
        )

with tab_live:
    row1 = st.columns(5)
    row1[0].metric("Spot", f"{s['spot']:,.2f}")
    row1[1].metric("ATM", f"{s['atm']:,.0f}")
    row1[2].metric("PCR (OI)", f"{s['pcr_oi']:.2f}")
    row1[3].metric("PCR (Volume)", f"{s['pcr_volume']:.2f}")
    row1[4].metric("Combined score", f"{intelligence['score']:+.2f}")

    fig = make_market_chart(
        p["candles"],
        support=s["support"],
        resistance=s["resistance"],
        max_pain=s["max_pain"],
        title=(
            f"{dashboard_result.market_snapshot.selected_instrument}"
            " — Native Upstox Intraday Chart"
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Why the engine reached this view")
        for reason in intelligence["evidence"]:
            st.write(f"• {reason}")
    with right:
        st.subheader("Price confirmation")
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("EMA 9", f"{p['ema9']:,.2f}")
        r2.metric("EMA 21", f"{p['ema21']:,.2f}")
        r3.metric("VWAP", f"{p['vwap']:,.2f}")
        r4.metric("RSI 14", f"{p['rsi']:.1f}")
        if intelligence["risk_flags"]:
            for flag in intelligence["risk_flags"]:
                st.warning(flag)
        else:
            st.info("No major model risk flag is active at the current snapshot.")

    st.subheader("OI activity summary")
    a1, a2, a3, a4, a5, a6 = st.columns(6)
    a1.metric("CE ΔOI", compact_number(s["call_oi_change"]))
    a2.metric("PE ΔOI", compact_number(s["put_oi_change"]))
    a3.metric("Call-writing strikes", s["call_writing"])
    a4.metric("Put-writing strikes", s["put_writing"])
    a5.metric("CE short-covering", s["call_short_covering"])
    a6.metric("PE short-covering", s["put_short_covering"])

with tab_explorer:
    st.subheader("Institutional flow memory")
    if save_snapshots:
        store = SnapshotStore()
        history = store.get_history(
            dashboard_result.market_snapshot.selected_instrument,
            dashboard_result.market_snapshot.expiry,
            hours=history_hours,
        )
        strike_history = store.get_strike_history(
            dashboard_result.market_snapshot.selected_instrument,
            dashboard_result.market_snapshot.expiry,
            hours=history_hours,
        )
        institutional = institutional_summary(history, strike_history)

        h1, h2, h3 = st.columns(3)
        h1.metric(
            "Stored snapshots",
            store.count_snapshots(
                dashboard_result.market_snapshot.selected_instrument,
                dashboard_result.market_snapshot.expiry,
            ),
        )
        h2.metric("Institutional flow", institutional["primary_label"])
        h3.metric("Flow strength", f"{institutional['primary_strength']:+.0f}")

        if st.session_state.get("snapshot_created") is False:
            st.info("The current minute was refreshed in SQLite rather than duplicated.")

        for sentence in institutional["narrative"]:
            st.write(f"• {sentence}")

        windows = institutional["windows"]
        if windows:
            window_rows = []
            for item in windows:
                window_rows.append({
                    "Window": f"{item.minutes} min",
                    "Actual history": f"{item.actual_minutes:.0f} min",
                    "Flow": item.label,
                    "Strength": item.strength,
                    "Spot Δ": item.spot_change,
                    "PCR Δ": item.pcr_change,
                    "CE OI flow": item.call_oi_change,
                    "PE OI flow": item.put_oi_change,
                    "Max Pain Δ": item.max_pain_change,
                })
            st.dataframe(window_rows, use_container_width=True, hide_index=True)
        else:
            st.warning("Only one snapshot is available. Keep auto-refresh enabled to build 5/15/30/60-minute comparisons.")

        if len(history) >= 2:
            hc1, hc2 = st.columns(2)
            with hc1:
                st.plotly_chart(oi_flow_chart(history), use_container_width=True)
            with hc2:
                st.plotly_chart(
                    line_chart(history, ["pcr_oi", "pcr_volume"], "PCR history", "PCR"),
                    use_container_width=True,
                )
            hc3, hc4 = st.columns(2)
            with hc3:
                st.plotly_chart(
                    line_chart(history, ["max_pain", "spot"], "Spot and Max Pain movement", "Index points"),
                    use_container_width=True,
                )
            with hc4:
                st.plotly_chart(
                    line_chart(history, ["atm_iv", "iv_skew"], "ATM IV and IV skew", "IV"),
                    use_container_width=True,
                )

            heatmap_side = st.radio("OI heatmap", ["net", "call", "put"], horizontal=True)
            st.plotly_chart(strike_heatmap(strike_history, heatmap_side), use_container_width=True)

            strike_flows = institutional["strike_flows"]
            if not strike_flows.empty:
                st.subheader("Strongest 15-minute strike flows")
                flow_view = strike_flows.head(12).copy()
                flow_view = flow_view[[
                    "strike", "ce_activity", "ce_oi_flow", "ce_premium_flow",
                    "pe_activity", "pe_oi_flow", "pe_premium_flow", "net_oi_flow"
                ]]
                flow_view.columns = [
                    "Strike", "CE Activity", "CE OI Flow", "CE Premium Flow",
                    "PE Activity", "PE OI Flow", "PE Premium Flow", "Net Put−Call Flow"
                ]
                st.dataframe(flow_view, use_container_width=True, hide_index=True)
    else:
        st.info("SQLite snapshot storage is disabled for this run.")

    st.subheader("Option chain near ATM")
    view_cols = [
        "call_activity", "call_oi_change", "call_oi", "call_volume", "call_iv",
        "call_delta", "call_gamma", "call_theta", "call_vega", "call_ltp",
        "strike", "put_ltp", "put_delta", "put_gamma", "put_theta", "put_vega",
        "put_iv", "put_volume", "put_oi", "put_oi_change", "put_activity",
    ]
    view = df[view_cols].copy()
    view.columns = [
        "CE Activity", "CE ΔOI", "CE OI", "CE Volume", "CE IV", "CE Delta",
        "CE Gamma", "CE Theta", "CE Vega", "CE LTP", "Strike", "PE LTP",
        "PE Delta", "PE Gamma", "PE Theta", "PE Vega", "PE IV", "PE Volume",
        "PE OI", "PE ΔOI", "PE Activity",
    ]
    numeric_format = {
        "CE IV": "{:.2f}", "CE Delta": "{:.3f}", "CE Gamma": "{:.5f}",
        "CE Theta": "{:.2f}", "CE Vega": "{:.2f}", "CE LTP": "{:.2f}",
        "Strike": "{:.0f}", "PE LTP": "{:.2f}", "PE Delta": "{:.3f}",
        "PE Gamma": "{:.5f}", "PE Theta": "{:.2f}", "PE Vega": "{:.2f}",
        "PE IV": "{:.2f}",
    }
    st.dataframe(view.style.format(numeric_format), use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Open-interest walls")
        temp = df.set_index("strike")[["call_oi", "put_oi"]]
        temp.columns = ["Call OI", "Put OI"]
        st.bar_chart(temp)
    with c2:
        st.subheader("Change in open interest")
        temp = df.set_index("strike")[["call_oi_change", "put_oi_change"]]
        temp.columns = ["Call ΔOI", "Put ΔOI"]
        st.bar_chart(temp)

    st.markdown("## ❓ Are the data feeds healthy?")
    st.caption("Data Health")
    dh1, dh2, dh3, dh4 = st.columns(4)
    dh1.metric("System State", data_health_result.metadata.get("status", "UNKNOWN"))
    dh2.metric("Data Quality", f"{data_health_result.score:.0f}/100", data_health_result.vote)
    dh3.metric("Option Rows", int(data_health_result.metadata.get("chain_rows", 0)))
    age = data_health_result.metadata.get("age_seconds")
    dh4.metric("Refresh Age", "Unknown" if age is None else f"{age:.0f}s")
    if not data_health_result.metadata.get("trading_allowed", False):
        st.error("NO TRADE — DATA QUALITY FAILURE: " + "; ".join(data_health_result.explanation))
    elif data_health_result.vote == "CAUTION":
        st.warning("Data quality is degraded. Treat all decisions as WATCH until inputs recover.")
    else:
        st.success("Data inputs are healthy enough for decision-support analysis.")

    with st.expander("How the Market Intelligence Engine works"):
        st.markdown(
            """
    The engine combines two independent groups of evidence:

    1. **Option-chain intelligence:** PCR, call/put OI additions, OI walls, volume PCR, IV skew and buildup classification.
    2. **Underlying confirmation:** EMA 9/21 alignment, VWAP position, recent momentum, ATR and RSI.

    The option-chain score receives 58% weight and price confirmation receives 42%. Version 4 stores one strike-level snapshot per minute in SQLite and compares market changes over 5, 15, 30 and 60 minutes. Version 5 adds relative-volume checks, market-regime detection, strike liquidity/delta/spread ranking and rule-based entry/exit planning. Institutional activity is inferred from changes in spot, OI and option premiums; it does not identify actual institutions. The probability values are model scores, not statistically guaranteed win rates.
    """
        )

st.caption(
    "For analysis and education only. This dashboard does not place orders and does not guarantee market direction."
)

if auto_refresh:
    time.sleep(refresh_seconds)
    st.rerun()
