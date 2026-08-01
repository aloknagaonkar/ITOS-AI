from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def make_market_chart(
    candles: pd.DataFrame,
    support: float,
    resistance: float,
    max_pain: float,
    title: str,
) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.76, 0.24],
    )
    fig.add_trace(
        go.Candlestick(
            x=candles["timestamp"],
            open=candles["open"],
            high=candles["high"],
            low=candles["low"],
            close=candles["close"],
            name="Price",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(go.Scatter(x=candles["timestamp"], y=candles["ema9"], name="EMA 9", mode="lines"), row=1, col=1)
    fig.add_trace(go.Scatter(x=candles["timestamp"], y=candles["ema21"], name="EMA 21", mode="lines"), row=1, col=1)
    fig.add_trace(go.Scatter(x=candles["timestamp"], y=candles["vwap"], name="VWAP", mode="lines"), row=1, col=1)
    fig.add_trace(go.Bar(x=candles["timestamp"], y=candles["volume"], name="Volume"), row=2, col=1)

    fig.add_hline(y=support, line_dash="dash", annotation_text=f"OI Support {support:.0f}", row=1, col=1)
    fig.add_hline(y=resistance, line_dash="dash", annotation_text=f"OI Resistance {resistance:.0f}", row=1, col=1)
    fig.add_hline(y=max_pain, line_dash="dot", annotation_text=f"Max Pain {max_pain:.0f}", row=1, col=1)

    fig.update_layout(
        title=title,
        height=670,
        xaxis_rangeslider_visible=False,
        legend_orientation="h",
        legend_y=1.03,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    return fig
