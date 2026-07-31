from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def line_chart(history: pd.DataFrame, columns: list[str], title: str, y_title: str) -> go.Figure:
    fig = go.Figure()
    for column in columns:
        if column in history.columns:
            fig.add_trace(
                go.Scatter(
                    x=history["captured_at"],
                    y=history[column],
                    mode="lines+markers",
                    name=column.replace("_", " ").title(),
                )
            )
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title=y_title,
        height=330,
        margin=dict(l=30, r=20, t=50, b=30),
        legend=dict(orientation="h"),
    )
    return fig


def oi_flow_chart(history: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=history["captured_at"], y=history["call_oi"], name="Call OI"))
    fig.add_trace(go.Scatter(x=history["captured_at"], y=history["put_oi"], name="Put OI"))
    fig.update_layout(
        title="Total near-ATM OI flow",
        xaxis_title="Time",
        yaxis_title="Open Interest",
        height=330,
        margin=dict(l=30, r=20, t=50, b=30),
        legend=dict(orientation="h"),
    )
    return fig


def strike_heatmap(strike_history: pd.DataFrame, side: str = "net") -> go.Figure:
    if strike_history.empty:
        return go.Figure()
    pivot_call = strike_history.pivot_table(
        index="strike", columns="captured_at", values="call_oi", aggfunc="last"
    )
    pivot_put = strike_history.pivot_table(
        index="strike", columns="captured_at", values="put_oi", aggfunc="last"
    )
    if side == "call":
        matrix, title = pivot_call, "Call OI heatmap"
    elif side == "put":
        matrix, title = pivot_put, "Put OI heatmap"
    else:
        matrix, title = pivot_put.subtract(pivot_call, fill_value=0), "Net OI heatmap (Put − Call)"
    matrix = matrix.sort_index(ascending=False)
    fig = go.Figure(
        data=go.Heatmap(
            z=matrix.values,
            x=[value.strftime("%H:%M") for value in matrix.columns],
            y=[f"{value:.0f}" for value in matrix.index],
            colorbar=dict(title="OI"),
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Snapshot time",
        yaxis_title="Strike",
        height=520,
        margin=dict(l=30, r=20, t=50, b=30),
    )
    return fig
