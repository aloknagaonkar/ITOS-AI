from __future__ import annotations

import pandas as pd
import streamlit as st

from models.trade import AITradeOpportunity, TradeCandidate


def _money(value: float) -> str:
    return "—" if value <= 0 else f"₹{value:,.2f}"


def _candidate_frame(candidates: tuple[TradeCandidate, ...]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Rank": index,
            "Contract": item.contract,
            "State": item.state,
            "Score": item.score,
            "Confidence": item.confidence,
            "Entry": item.entry_trigger,
            "SL": item.stop_loss,
            "T1": item.target1,
            "T2": item.target2,
        }
        for index, item in enumerate(candidates, start=1)
    ])


def render_ai_trade_opportunity(opportunity: AITradeOpportunity) -> None:
    """Render decision-critical information first; keep research detail collapsed."""
    st.markdown("## ❓ What should I do?")
    st.caption("AI Decision")

    decision = (
        f"BUY {opportunity.recommended_side}"
        if opportunity.recommendation == "BUY" and opportunity.recommended_side in {"CE", "PE"}
        else "WAIT"
    )

    # Row 1: the four values needed for an immediate decision.
    action_col, best_col, direction_col, ready_col = st.columns([1.15, 1.45, 1, 1])
    action_col.metric("AI Decision", decision, opportunity.execution.state)
    best_col.metric("Best Contract", opportunity.contract)
    direction_col.metric("Directional Confidence", f"{opportunity.directional_confidence:.0f}/100")
    ready_col.metric("Trade Readiness", f"{opportunity.trade_readiness:.0f}/100")

    # Row 2: side comparison prevents unclear or low-edge entries.
    st.markdown("## ❓ Which side is stronger?")
    st.caption("CE vs PE Strength")
    ce_col, pe_col, edge_col, confidence_col = st.columns(4)
    ce_col.metric("CE Strength", f"{opportunity.ce_strength:.0f}%")
    pe_col.metric("PE Strength", f"{opportunity.pe_strength:.0f}%")
    edge_label = opportunity.recommended_side if opportunity.recommended_side in {"CE", "PE"} else "NO CLEAR EDGE"
    edge_col.metric("Stronger Side", edge_label, f"{opportunity.strength_advantage:.0f}-point edge")
    confidence_col.metric("Recommendation Confidence", f"{opportunity.confidence:.0f}%")

    # Trigger checklist is decision-critical and therefore stays above all research panels.
    st.markdown("## ❓ Can I trade now?")
    st.caption("Trigger Checklist")
    checklist = opportunity.metadata.get("condition_checklist", []) or []
    missing = opportunity.metadata.get("missing_conditions", []) or []
    passed = int(opportunity.metadata.get("passed_conditions", 0) or 0)
    total = int(opportunity.metadata.get("total_conditions", 0) or 0)
    if total > 0:
        st.progress(passed / max(total, 1), text=f"Trigger readiness: {passed} of {total} conditions complete")

    check_left, check_right = st.columns(2)
    with check_left:
        st.markdown("### Confirmation status")
        if checklist:
            for item in checklist:
                icon = "✅" if item.get("passed") else "🟡"
                st.write(f"{icon} {item.get('name', 'Condition')} — {item.get('detail', '')}")
        else:
            st.info("Trigger checklist is warming up.")
    with check_right:
        st.markdown("### What is still missing?")
        if missing:
            for item in missing:
                st.write(f"• {item}")
        else:
            st.success("Nothing missing. All trigger conditions are complete.")

    # Early move is an advance-warning layer, never the execution authority.
    st.markdown("## ❓ Am I early?")
    st.caption("Early Move Detector")
    early1, early2, early3 = st.columns(3)
    early1.metric("Build-up State", opportunity.early_move_state)
    early2.metric("Watch Side", opportunity.early_move_side)
    early3.metric("Build-up Probability", f"{opportunity.early_move_probability:.0f}%")
    st.caption("Informational only: prepares CE/PE watchlist and does not override the confirmed AI decision.")

    st.markdown("## ❓ What changed in the last 5 minutes?")
    st.caption("Live Change Intelligence")
    changes = opportunity.metadata.get("recent_changes", []) or []
    st.info(opportunity.metadata.get("change_summary", "Waiting for enough history."))
    if changes:
        columns = st.columns(min(4, len(changes)))
        for index, item in enumerate(changes[:4]):
            with columns[index]:
                if "before_text" in item:
                    st.metric(item.get("label", "Change"), item.get("now_text", "—"), f"From {item.get('before_text', '—')}")
                else:
                    delta = float(item.get("delta", 0) or 0)
                    st.metric(
                        item.get("label", "Change"),
                        f"{float(item.get('now', 0) or 0):.0f}%",
                        f"{delta:+.1f} pts",
                    )
    else:
        st.caption("The comparison becomes available after multiple refreshes spanning approximately five minutes.")

    st.markdown("## ❓ What should I watch next?")
    st.caption("Next Confirmation Watchlist")
    watch_next = opportunity.metadata.get("watch_next", []) or []
    if watch_next:
        for item in watch_next:
            st.write(f"• {item}")
    else:
        st.success("No additional confirmation is currently required.")

    # Explainability appears before execution so the trader sees the evidence first.
    st.markdown("## ❓ Why is ITOS saying this?")
    st.caption("Explainable AI")
    why_col, risk_col = st.columns(2)
    with why_col:
        st.markdown("### Supporting evidence")
        if opportunity.reasons:
            for reason in opportunity.reasons[:6]:
                st.write(f"✅ {reason}")
        else:
            st.info("Waiting for sufficient confirmation evidence.")
    with risk_col:
        st.markdown("### Active blockers")
        if opportunity.blockers:
            for blocker in opportunity.blockers[:6]:
                st.write(f"• {blocker}")
        else:
            st.success("No active blocker passed to the decision layer.")

    # Execution plan remains on the first screen.
    st.markdown("## ❓ How do I execute?")
    st.caption("Trade Plan")
    plan = opportunity.execution
    p1, p2, p3, p4, p5 = st.columns(5)
    entry = _money(plan.entry_low) if plan.entry_high <= plan.entry_low else f"{_money(plan.entry_low)} – {_money(plan.entry_high)}"
    p1.metric("Entry", entry)
    p2.metric("Stop Loss", _money(plan.stop_loss))
    p3.metric("Target 1", _money(plan.targets[0]) if plan.targets else "—")
    p4.metric("Target 2", _money(plan.targets[1]) if len(plan.targets) > 1 else "—")
    p5.metric("Risk : Reward", f"1:{plan.risk_reward:.2f}" if plan.risk_reward > 0 else "—")

    # Supporting context stays visible but below the decision and trigger layers.
    context1, context2, context3 = st.columns(3)
    context1.metric("Market Regime", opportunity.market_regime)
    context2.metric("Institutional Score", f"{opportunity.institutional_score:.0f}/100")
    context3.metric("Trade Quality", f"{opportunity.trade_quality:.0f}/100")

    # Candidate research is useful but should not push the live decision below the fold.
    with st.expander("Top 5 CE and PE candidates", expanded=False):
        ce_table, pe_table = st.columns(2)
        with ce_table:
            st.markdown("#### CE Candidates")
            ce = _candidate_frame(opportunity.top_ce)
            if ce.empty:
                st.info("No CE contract currently passes ranking filters.")
            else:
                st.dataframe(
                    ce.style.format({"Score": "{:.1f}", "Confidence": "{:.1f}%", "Entry": "₹{:.2f}", "SL": "₹{:.2f}", "T1": "₹{:.2f}", "T2": "₹{:.2f}"}),
                    use_container_width=True,
                    hide_index=True,
                )
        with pe_table:
            st.markdown("#### PE Candidates")
            pe = _candidate_frame(opportunity.top_pe)
            if pe.empty:
                st.info("No PE contract currently passes ranking filters.")
            else:
                st.dataframe(
                    pe.style.format({"Score": "{:.1f}", "Confidence": "{:.1f}%", "Entry": "₹{:.2f}", "SL": "₹{:.2f}", "T1": "₹{:.2f}", "T2": "₹{:.2f}"}),
                    use_container_width=True,
                    hide_index=True,
                )

    st.caption("ITOS v9.1.0 • Live change and next-watch intelligence")
    st.divider()
