from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from .base_engine import BaseEngine, EngineResult
from itos_platform import DecisionContext


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if np.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _clip(value: float) -> float:
    return float(np.clip(value, 0.0, 100.0))


def _vote(direction: str) -> str:
    return direction if direction in {"CE", "PE"} else "WAIT"


def _safe_df(market_data: dict[str, Any]) -> pd.DataFrame:
    price = market_data.get("intelligence", {}).get("price", {})
    df = price.get("candles")
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    result = df.copy().sort_index()
    for col in ("open", "high", "low", "close", "volume"):
        if col not in result:
            return pd.DataFrame()
        result[col] = pd.to_numeric(result[col], errors="coerce")
    return result.dropna(subset=["open", "high", "low", "close"])


def _candle_features(row: pd.Series) -> dict[str, float]:
    o, h, l, c = (_num(row.get(x)) for x in ("open", "high", "low", "close"))
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    return {
        "range": rng,
        "body_pct": body / rng * 100,
        "upper_wick_pct": (h - max(o, c)) / rng * 100,
        "lower_wick_pct": (min(o, c) - l) / rng * 100,
        "bullish": float(c > o),
        "bearish": float(c < o),
    }


class CandleDNAEngine(BaseEngine):
    name = "Candle DNA"

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        market_data = self._adapt_input(market_data)
        df = _safe_df(market_data)
        if df.empty:
            return EngineResult(self.name, 0, "WAIT", ["Candle data unavailable"], {})
        latest = df.iloc[-1]
        f = _candle_features(latest)
        atr = _num(latest.get("atr14"), df["high"].sub(df["low"]).tail(14).mean())
        range_atr = f["range"] / max(atr, 1e-9)
        vol = _num(latest.get("volume"))
        avg_vol = _num(df["volume"].tail(20).iloc[:-1].mean(), vol)
        rvol = vol / max(avg_vol, 1.0)
        close_location = (_num(latest["close"]) - _num(latest["low"])) / max(f["range"], 1e-9)
        direction = "CE" if latest["close"] > latest["open"] else "PE" if latest["close"] < latest["open"] else "WAIT"
        close_strength = close_location if direction == "CE" else 1 - close_location

        # Custom Candle DNA: Injection-Pinbar at the bottom. Candle colour is
        # intentionally ignored; structure and bottom-location context are what
        # make the setup bullish. The lower-wick rule is measured against the
        # real body so the detector remains useful for the large-body examples
        # supplied by the user.
        body_size = abs(_num(latest["close"]) - _num(latest["open"]))
        lower_wick_size = min(_num(latest["open"]), _num(latest["close"])) - _num(latest["low"])
        lower_wick_to_body = lower_wick_size / max(body_size, 1e-9)
        recent_low = _num(df["low"].tail(8).min(), _num(latest["low"]))
        near_bottom = _num(latest["low"]) <= recent_low + max(atr * .15, 1e-9)
        prior = df.iloc[-4:-1] if len(df) >= 4 else df.iloc[:-1]
        downmove = bool(len(prior) >= 2 and _num(prior["close"].iloc[-1]) <= _num(prior["close"].iloc[0]))
        # Two accepted structures belong to the same bullish bottom pattern:
        # 1) CLASSIC_INJECTION: a visible lower injection wick.
        # 2) SMALL_TIP: an exceptionally large body with an almost absent upper
        #    wick and a very small but visible lower tip. This is the additional
        #    user-supplied structure. Candle colour remains irrelevant.
        classic_injection = bool(
            f["body_pct"] >= 55
            and f["upper_wick_pct"] <= 12
            and lower_wick_to_body >= .30
        )
        small_tip_injection = bool(
            f["body_pct"] >= 85
            and f["upper_wick_pct"] <= 3
            and 0 < f["lower_wick_pct"] <= 8
        )
        injection_variant = (
            "SMALL_TIP" if small_tip_injection else
            "CLASSIC_INJECTION" if classic_injection else
            "NONE"
        )
        injection_pinbar_bottom = bool(
            (classic_injection or small_tip_injection)
            and (near_bottom or downmove)
        )

        score = _clip(f["body_pct"] * .42 + min(range_atr, 2.0) * 18 + min(rvol, 3.0) * 10 + close_strength * 12)
        if injection_pinbar_bottom:
            score = _clip(max(score, 72) + (8 if near_bottom else 3) + min(rvol, 2.0) * 3)
            direction = "CE"
        grade = "INSTITUTION GRADE" if score >= 80 else "STRONG" if score >= 65 else "NORMAL" if score >= 45 else "WEAK"
        detected_custom_patterns = ["Injection-Pinbar (Bottom)"] if injection_pinbar_bottom else []
        evidence = [
            f"Body occupies {f['body_pct']:.1f}% of the candle range.",
            f"Range is {range_atr:.2f}× ATR and volume is {rvol:.2f}× recent average.",
            f"The candle closes {close_strength * 100:.0f}% toward its directional extreme.",
        ]
        if injection_pinbar_bottom:
            evidence.append(
                "Injection-Pinbar (Bottom) detected: "
                + (
                    f"small-tip variant with {f['body_pct']:.1f}% body, {f['upper_wick_pct']:.1f}% upper wick "
                    f"and {f['lower_wick_pct']:.1f}% lower tip"
                    if injection_variant == "SMALL_TIP" else
                    f"classic injection variant with lower wick {lower_wick_to_body:.2f}× body"
                )
                + ", with bottom/downmove context; candle colour ignored."
            )
        return EngineResult(self.name, score, _vote(direction), evidence, {
            **f, "range_atr": range_atr, "relative_volume": rvol, "grade": grade,
            "direction": direction, "lower_wick_to_body": lower_wick_to_body,
            "near_bottom": near_bottom, "downmove_context": downmove,
            "injection_pinbar_bottom": injection_pinbar_bottom,
            "injection_pinbar_variant": injection_variant,
            "small_tip_injection": small_tip_injection,
            "classic_injection": classic_injection,
            "custom_patterns_detected": detected_custom_patterns,
        })


    @staticmethod
    def _adapt_input(market_data: DecisionContext | Mapping[str, Any]) -> Mapping[str, Any]:
        """Normalize typed and legacy engine inputs."""
        if not isinstance(market_data, DecisionContext):
            return market_data
        return {"intelligence": market_data.market_snapshot.intelligence}


class SmartCandlestickEngine(BaseEngine):
    name = "Smart Candlestick"

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        market_data = self._adapt_input(market_data)
        df = _safe_df(market_data)
        if len(df) < 3:
            return EngineResult(self.name, 0, "WAIT", ["At least three candles are required"], {})
        a, b, c = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        fb, fc = _candle_features(b), _candle_features(c)
        patterns: list[dict[str, Any]] = []

        def add(name: str, direction: str, base: float, reason: str) -> None:
            context = market_data.get("intelligence", {}).get("price", {})
            vwap = _num(context.get("vwap"), _num(c["close"]))
            aligned = (direction == "CE" and c["close"] >= vwap) or (direction == "PE" and c["close"] <= vwap)
            volume_ratio = _num(c.get("volume")) / max(_num(df["volume"].tail(20).iloc[:-1].mean()), 1.0)
            score = _clip(base + (10 if aligned else -8) + min(volume_ratio, 3) * 5)
            patterns.append({"name": name, "direction": direction, "confidence": round(score, 1), "evidence": reason, "vwap_aligned": aligned})

        if c["close"] > c["open"] and b["close"] < b["open"] and c["open"] <= b["close"] and c["close"] >= b["open"]:
            add("Bullish Engulfing", "CE", 68, "Current bullish body fully engulfs the prior bearish body")
        if c["close"] < c["open"] and b["close"] > b["open"] and c["open"] >= b["close"] and c["close"] <= b["open"]:
            add("Bearish Engulfing", "PE", 68, "Current bearish body fully engulfs the prior bullish body")
        # User-defined bullish structure: Injection-Pinbar at the bottom.
        # Candle colour is irrelevant. It requires a large real body, minimal
        # upper wick, a meaningful lower injection wick relative to the body,
        # and either a recent-low or short downmove context.
        body_size = abs(_num(c["close"]) - _num(c["open"]))
        lower_wick_size = min(_num(c["open"]), _num(c["close"])) - _num(c["low"])
        lower_wick_to_body = lower_wick_size / max(body_size, 1e-9)
        atr = _num(c.get("atr14"), df["high"].sub(df["low"]).tail(14).mean())
        recent_low = _num(df["low"].tail(8).min(), _num(c["low"]))
        near_bottom = _num(c["low"]) <= recent_low + max(atr * .15, 1e-9)
        prior = df.iloc[-4:-1] if len(df) >= 4 else df.iloc[:-1]
        downmove = bool(len(prior) >= 2 and _num(prior["close"].iloc[-1]) <= _num(prior["close"].iloc[0]))
        classic_injection = bool(
            fc["body_pct"] >= 55
            and fc["upper_wick_pct"] <= 12
            and lower_wick_to_body >= .30
        )
        small_tip_injection = bool(
            fc["body_pct"] >= 85
            and fc["upper_wick_pct"] <= 3
            and 0 < fc["lower_wick_pct"] <= 8
        )
        if (classic_injection or small_tip_injection) and (near_bottom or downmove):
            variant = "Small Tip" if small_tip_injection else "Classic Injection"
            add(
                "Injection-Pinbar (Bottom)", "CE", 92 if small_tip_injection else 84,
                f"{variant} structure at a recent bottom; candle colour is ignored",
            )
        if fc["lower_wick_pct"] >= 55 and fc["body_pct"] <= 35:
            add("Hammer / Bullish Pin Bar", "CE", 60, "Long lower wick indicates rejection of lower prices")
        if fc["upper_wick_pct"] >= 55 and fc["body_pct"] <= 35:
            add("Shooting Star / Bearish Pin Bar", "PE", 60, "Long upper wick indicates rejection of higher prices")
        if fc["body_pct"] >= 75 and fc["upper_wick_pct"] <= 12 and fc["lower_wick_pct"] <= 12:
            add("Bullish Marubozu" if c["close"] > c["open"] else "Bearish Marubozu", "CE" if c["close"] > c["open"] else "PE", 72, "Large directional body with minimal wicks")
        if fc["body_pct"] <= 12:
            add("Doji", "WAIT", 42, "Small real body signals indecision")
        if b["high"] < a["high"] and b["low"] > a["low"]:
            direction = "CE" if c["close"] > a["high"] else "PE" if c["close"] < a["low"] else "WAIT"
            add("Inside Bar Breakout" if direction != "WAIT" else "Inside Bar", direction, 62 if direction != "WAIT" else 45, "Price compressed inside the previous candle")

        if not patterns:
            patterns.append({"name": "No Priority Candle Pattern", "direction": "WAIT", "confidence": 25.0, "evidence": "No curated high-value candlestick pattern is active", "vwap_aligned": False})
        patterns.sort(key=lambda x: x["confidence"], reverse=True)
        primary = patterns[0]
        return EngineResult(self.name, primary["confidence"], _vote(primary["direction"]), [primary["evidence"]], {"primary": primary, "patterns": patterns})



    @staticmethod
    def _adapt_input(market_data: DecisionContext | Mapping[str, Any]) -> Mapping[str, Any]:
        """Normalize typed and legacy engine inputs."""
        if not isinstance(market_data, DecisionContext):
            return market_data
        return {"intelligence": market_data.market_snapshot.intelligence}


def build_historical_candle_pattern_table(candles: pd.DataFrame, trading_days: int = 2, evaluation_bars: int = 5) -> pd.DataFrame:
    """Scan and evaluate Smart Candle patterns in the latest trading sessions.

    Version 7.5.2 adds forward outcome tracking, confirmation scoring, pattern
    lifecycle status, and failure explanations. Forward evaluation never crosses
    the session boundary. Rows near the end of the latest session remain PENDING.
    """
    if not isinstance(candles, pd.DataFrame) or candles.empty:
        return pd.DataFrame()

    df = candles.copy()
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    elif isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index().rename(columns={df.index.name or "index": "timestamp"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        return pd.DataFrame()
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    for column in ("open", "high", "low", "close", "volume"):
        if column not in df.columns:
            return pd.DataFrame()
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    if df.empty:
        return pd.DataFrame()

    df["session_date"] = df["timestamp"].dt.date
    latest_sessions = sorted(df["session_date"].unique())[-max(int(trading_days), 1):]
    df = df[df["session_date"].isin(latest_sessions)].reset_index(drop=True)

    # Session-safe indicators used as historical confirmation evidence.
    groups = df.groupby("session_date", group_keys=False)
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"].fillna(0)
    df["vwap_hist"] = groups.apply(lambda g: pv.loc[g.index].cumsum() / df.loc[g.index, "volume"].fillna(0).cumsum().replace(0, np.nan), include_groups=False).reset_index(level=0, drop=True)
    df["ema9"] = groups["close"].transform(lambda x: x.ewm(span=9, adjust=False).mean())
    df["ema21"] = groups["close"].transform(lambda x: x.ewm(span=21, adjust=False).mean())
    prev_close = groups["close"].shift(1)
    tr = pd.concat([(df["high"]-df["low"]), (df["high"]-prev_close).abs(), (df["low"]-prev_close).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.groupby(df["session_date"]).transform(lambda x: x.rolling(14, min_periods=3).mean())
    df["avg_volume20"] = groups["volume"].transform(lambda x: x.shift(1).rolling(20, min_periods=3).mean())

    rows: list[dict[str, Any]] = []
    dna_engine = CandleDNAEngine()
    smart_engine = SmartCandlestickEngine()
    evaluation_bars = max(int(evaluation_bars), 1)

    for idx in range(len(df)):
        session_date = df.loc[idx, "session_date"]
        same_session_before = df.index[(df["session_date"] == session_date) & (df.index <= idx)]
        if len(same_session_before) < 3:
            continue
        window_start = max(int(same_session_before.min()), idx - 39)
        window_cols = ["timestamp", "open", "high", "low", "close", "volume", "atr14"]
        window = df.loc[window_start:idx, window_cols].copy().set_index("timestamp")
        context_vwap = _num(df.loc[idx, "vwap_hist"], _num(df.loc[idx, "close"]))
        market_data = {"intelligence": {"price": {"candles": window, "vwap": context_vwap}}}
        dna = dna_engine.analyze(market_data)
        smart = smart_engine.analyze(market_data)

        for pattern in smart.metadata.get("patterns", []) or []:
            name = str(pattern.get("name", ""))
            if not name or name == "No Priority Candle Pattern":
                continue
            direction = str(pattern.get("direction", "WAIT"))
            ts = df.loc[idx, "timestamp"]
            entry = _num(df.loc[idx, "close"])
            atr = max(_num(df.loc[idx, "atr14"], _num(df.loc[idx, "high"]-df.loc[idx, "low"])), 1e-9)

            future_idx = df.index[(df.index > idx) & (df["session_date"] == session_date)][:evaluation_bars]
            future = df.loc[future_idx]
            available = len(future)
            sign = 1.0 if direction == "CE" else -1.0 if direction == "PE" else 0.0
            after = {}
            for horizon in (1, 3, 5):
                key = f"After {horizon} Bars"
                if available >= horizon and sign:
                    after[key] = round(sign * (_num(future.iloc[horizon-1]["close"]) - entry), 2)
                else:
                    after[key] = np.nan

            if available and sign:
                if direction == "CE":
                    mfe = _num(future["high"].max()) - entry
                    mae = _num(future["low"].min()) - entry
                else:
                    mfe = entry - _num(future["low"].min())
                    mae = entry - _num(future["high"].max())
            else:
                mfe = mae = np.nan

            target_distance = atr
            stop_distance = atr * 0.60
            if direction == "WAIT":
                status = "WATCH"
            elif available < evaluation_bars:
                status = "PENDING"
            elif mfe >= target_distance and mae > -stop_distance:
                status = "CONFIRMED"
            elif mae <= -stop_distance:
                status = "FAILED"
            else:
                status = "INVALIDATED" if after.get("After 5 Bars", 0) < 0 else "UNRESOLVED"

            close = _num(df.loc[idx, "close"])
            vwap = _num(df.loc[idx, "vwap_hist"], close)
            ema9 = _num(df.loc[idx, "ema9"], close)
            ema21 = _num(df.loc[idx, "ema21"], close)
            rvol = _num(df.loc[idx, "volume"]) / max(_num(df.loc[idx, "avg_volume20"], df["volume"].mean()), 1.0)
            vwap_ok = (direction == "CE" and close >= vwap) or (direction == "PE" and close <= vwap)
            trend_ok = (direction == "CE" and ema9 >= ema21) or (direction == "PE" and ema9 <= ema21)
            volume_ok = rvol >= 1.2
            confirmation = _clip(_num(pattern.get("confidence")) * .55 + dna.score * .25 + (10 if vwap_ok else 0) + (6 if trend_ok else 0) + (4 if volume_ok else 0))
            confirmations = [label for label, ok in (("VWAP", vwap_ok), ("EMA trend", trend_ok), ("Relative volume", volume_ok)) if ok]
            conflicts = [label for label, ok in (("VWAP misalignment", vwap_ok), ("EMA trend conflict", trend_ok), ("Low relative volume", volume_ok)) if not ok]
            failure_reason = ""
            if status in {"FAILED", "INVALIDATED"}:
                failure_reason = "; ".join(conflicts) or "Price failed to follow through within the evaluation window"

            rows.append({
                "Pattern ID": f"{ts.strftime('%Y%m%d%H%M')}-{name.replace(' ', '-')}",
                "Timestamp": ts,
                "Date": ts.strftime("%Y-%m-%d"),
                "Time": ts.strftime("%H:%M"),
                "Pattern": name,
                "Direction": direction,
                "Status": status,
                "Reliability %": round(_num(pattern.get("confidence")), 1),
                "Institutional Confirmation %": round(confirmation, 1),
                "Confirmation Evidence": ", ".join(confirmations) or "Price-pattern evidence only",
                "DNA Score": round(dna.score, 1),
                "DNA Grade": dna.metadata.get("grade", "UNKNOWN"),
                "Entry": round(entry, 2),
                "Target (1 ATR)": round(entry + sign * target_distance, 2) if sign else np.nan,
                "Stop (0.6 ATR)": round(entry - sign * stop_distance, 2) if sign else np.nan,
                **after,
                "MFE Points": round(mfe, 2) if np.isfinite(mfe) else np.nan,
                "MAE Points": round(mae, 2) if np.isfinite(mae) else np.nan,
                "R Multiple": round(mfe / stop_distance, 2) if np.isfinite(mfe) else np.nan,
                "Body %": round(_num(dna.metadata.get("body_pct")), 1),
                "Upper Wick %": round(_num(dna.metadata.get("upper_wick_pct")), 1),
                "Lower Wick %": round(_num(dna.metadata.get("lower_wick_pct")), 1),
                "Range/ATR": round(_num(dna.metadata.get("range_atr")), 2),
                "Relative Volume": round(rvol, 2),
                "VWAP Aligned": bool(vwap_ok),
                "Failure Analysis": failure_reason,
                "Evidence": pattern.get("evidence", ""),
            })

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values("Timestamp", ascending=False).reset_index(drop=True)


def build_pattern_statistics(patterns: pd.DataFrame) -> pd.DataFrame:
    """Aggregate evaluated historical patterns into a compact scorecard."""
    if not isinstance(patterns, pd.DataFrame) or patterns.empty:
        return pd.DataFrame()
    evaluated = patterns[patterns["Status"].isin(["CONFIRMED", "FAILED", "INVALIDATED", "UNRESOLVED"])].copy()
    if evaluated.empty:
        return pd.DataFrame()
    evaluated["Win"] = evaluated["Status"].eq("CONFIRMED").astype(int)
    stats = evaluated.groupby(["Pattern", "Direction"], dropna=False).agg(
        Occurrences=("Pattern", "size"),
        Wins=("Win", "sum"),
        Average_DNA=("DNA Score", "mean"),
        Average_Confirmation=("Institutional Confirmation %", "mean"),
        Average_MFE=("MFE Points", "mean"),
        Average_MAE=("MAE Points", "mean"),
        Average_R=("R Multiple", "mean"),
    ).reset_index()
    stats["Win Rate %"] = stats["Wins"] / stats["Occurrences"] * 100
    stats = stats.rename(columns={
        "Average_DNA": "Avg DNA", "Average_Confirmation": "Avg Confirmation %",
        "Average_MFE": "Avg MFE", "Average_MAE": "Avg MAE", "Average_R": "Avg R"
    })
    for col in ("Avg DNA", "Avg Confirmation %", "Avg MFE", "Avg MAE", "Avg R", "Win Rate %"):
        stats[col] = stats[col].round(2)
    return stats.sort_values(["Win Rate %", "Occurrences"], ascending=[False, False]).reset_index(drop=True)


class InstitutionalStructureEngine(BaseEngine):
    name = "Institutional Structure"

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        market_data = self._adapt_input(market_data)
        df = _safe_df(market_data)
        if len(df) < 12:
            return EngineResult(self.name, 0, "WAIT", ["At least twelve candles are required"], {})
        recent = df.tail(min(40, len(df))).copy()
        price = market_data.get("intelligence", {}).get("price", {})
        atr = max(_num(price.get("atr"), recent["high"].sub(recent["low"]).tail(14).mean()), 1e-9)
        close = _num(recent["close"].iloc[-1])
        structures: list[dict[str, Any]] = []

        def add(name: str, direction: str, score: float, status: str, evidence: str, invalidation: str) -> None:
            structures.append({"name": name, "direction": direction, "confidence": round(_clip(score), 1), "status": status, "evidence": evidence, "invalidation": invalidation})

        # Flat base / rectangle: tight range and ATR contraction.
        base = recent.tail(15)
        width = _num(base["high"].max() - base["low"].min())
        width_atr = width / atr
        atr_now = _num(base.get("atr14", pd.Series(dtype=float)).tail(5).mean(), atr)
        atr_old = _num(recent.get("atr14", pd.Series(dtype=float)).tail(15).head(5).mean(), atr_now)
        contraction = 1 - atr_now / max(atr_old, 1e-9)
        if width_atr <= 4.5:
            top, bottom = _num(base["high"].max()), _num(base["low"].min())
            direction = "CE" if close > top else "PE" if close < bottom else "WAIT"
            status = "CONFIRMED" if direction != "WAIT" else "FORMING"
            score = 58 + max(0, 4.5 - width_atr) * 6 + max(contraction, 0) * 25
            add("Flat Base / Rectangle", direction, score, status, f"15-candle range is {width_atr:.2f}× ATR with {max(contraction, 0)*100:.0f}% ATR contraction", f"Sustained close beyond {bottom:.2f}–{top:.2f} opposite the expected direction")

        # W/M using two swing zones.
        lows = recent["low"].rolling(3, center=True).min() == recent["low"]
        highs = recent["high"].rolling(3, center=True).max() == recent["high"]
        low_idx = list(np.flatnonzero(lows.fillna(False).to_numpy()))
        high_idx = list(np.flatnonzero(highs.fillna(False).to_numpy()))
        if len(low_idx) >= 2:
            i, j = low_idx[-2], low_idx[-1]
            if j - i >= 3:
                l1, l2 = _num(recent["low"].iloc[i]), _num(recent["low"].iloc[j])
                neckline = _num(recent["high"].iloc[i:j+1].max())
                similarity = abs(l1-l2)/atr
                if similarity <= .8:
                    confirmed = close > neckline
                    add("W Pattern / Double Bottom", "CE" if confirmed else "WAIT", 62 + max(0, .8-similarity)*20 + (15 if confirmed else 0), "CONFIRMED" if confirmed else "FORMING", f"Two lows are within {similarity:.2f} ATR; neckline {neckline:.2f}", f"Close below {min(l1,l2):.2f}")
        if len(high_idx) >= 2:
            i, j = high_idx[-2], high_idx[-1]
            if j - i >= 3:
                h1, h2 = _num(recent["high"].iloc[i]), _num(recent["high"].iloc[j])
                neckline = _num(recent["low"].iloc[i:j+1].min())
                similarity = abs(h1-h2)/atr
                if similarity <= .8:
                    confirmed = close < neckline
                    add("M Pattern / Double Top", "PE" if confirmed else "WAIT", 62 + max(0, .8-similarity)*20 + (15 if confirmed else 0), "CONFIRMED" if confirmed else "FORMING", f"Two highs are within {similarity:.2f} ATR; neckline {neckline:.2f}", f"Close above {max(h1,h2):.2f}")

        # Flag: impulse then controlled counter-trend consolidation.
        if len(recent) >= 14:
            pole = recent.iloc[-14:-6]
            flag = recent.iloc[-6:]
            pole_move = _num(pole["close"].iloc[-1] - pole["open"].iloc[0])
            flag_move = _num(flag["close"].iloc[-1] - flag["open"].iloc[0])
            pole_strength = abs(pole_move) / atr
            retrace = abs(flag_move) / max(abs(pole_move), 1e-9)
            flag_high, flag_low = _num(flag["high"].max()), _num(flag["low"].min())
            if pole_strength >= 2.0 and retrace <= .55:
                if pole_move > 0 and flag_move <= 0:
                    confirmed = close >= flag_high
                    add("Bull Flag", "CE" if confirmed else "WAIT", 60 + min(pole_strength,5)*5 + (15 if confirmed else 0), "CONFIRMED" if confirmed else "FORMING", f"Bullish pole is {pole_strength:.1f} ATR and pullback retraces {retrace*100:.0f}%", f"Close below flag low {flag_low:.2f}")
                if pole_move < 0 and flag_move >= 0:
                    confirmed = close <= flag_low
                    add("Bear Flag", "PE" if confirmed else "WAIT", 60 + min(pole_strength,5)*5 + (15 if confirmed else 0), "CONFIRMED" if confirmed else "FORMING", f"Bearish pole is {pole_strength:.1f} ATR and recovery retraces {retrace*100:.0f}%", f"Close above flag high {flag_high:.2f}")

        # Liquidity sweep / spring / upthrust.
        prior = recent.iloc[-12:-1]
        last = recent.iloc[-1]
        prior_low, prior_high = _num(prior["low"].min()), _num(prior["high"].max())
        if _num(last["low"]) < prior_low and _num(last["close"]) > prior_low:
            add("Wyckoff Spring / Low Sweep", "CE", 78, "CONFIRMED", "Price swept prior lows and closed back inside the range", f"Close below {prior_low:.2f}")
        if _num(last["high"]) > prior_high and _num(last["close"]) < prior_high:
            add("Wyckoff Upthrust / High Sweep", "PE", 78, "CONFIRMED", "Price swept prior highs and closed back inside the range", f"Close above {prior_high:.2f}")

        # Volatility squeeze.
        ranges = recent["high"] - recent["low"]
        short_rng, long_rng = _num(ranges.tail(5).mean()), _num(ranges.tail(20).mean())
        squeeze = 1 - short_rng / max(long_rng, 1e-9)
        if squeeze >= .25:
            add("Volatility Squeeze", "WAIT", 55 + squeeze*45, "FORMING", f"Recent candle range contracted {squeeze*100:.0f}% versus the 20-candle average", "Range expansion without directional confirmation")

        if not structures:
            structures.append({"name":"No Institutional Structure","direction":"WAIT","confidence":20.0,"status":"INACTIVE","evidence":"No priority structure passed minimum geometry rules","invalidation":"Wait for a clearer base, reversal or continuation structure"})
        structures.sort(key=lambda x: x["confidence"], reverse=True)
        primary = structures[0]
        return EngineResult(self.name, primary["confidence"], _vote(primary["direction"]), [primary["evidence"]], {"primary": primary, "structures": structures})


    @staticmethod
    def _adapt_input(market_data: DecisionContext | Mapping[str, Any]) -> Mapping[str, Any]:
        """Normalize typed and legacy engine inputs."""
        if not isinstance(market_data, DecisionContext):
            return market_data
        return {"intelligence": market_data.market_snapshot.intelligence}


class InstitutionalFootprintEngine(BaseEngine):
    name = "Institutional Footprint"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        option = market_data.get("option_result", {}).get("summary", {})
        price = market_data.get("intelligence", {}).get("price", {})
        institutional = market_data.get("institutional") or {}
        cycle = getattr(market_data.get("cycle_result"), "metadata", {}) or {}
        call_change, put_change = _num(option.get("call_oi_change")), _num(option.get("put_oi_change"))
        denom = max(abs(call_change)+abs(put_change), 1.0)
        oi_bias = (put_change-call_change)/denom * 100
        close, vwap = _num(price.get("close")), _num(price.get("vwap"), _num(price.get("close")))
        df = _safe_df(market_data)
        rvol = 1.0
        if not df.empty:
            rvol = _num(df["volume"].iloc[-1]) / max(_num(df["volume"].tail(20).iloc[:-1].mean()),1.0)
        flow = _num(institutional.get("primary_strength"))
        directional = oi_bias*.40 + np.clip(flow,-100,100)*.30 + np.clip((close-vwap)/max(_num(price.get("atr")),1),-2,2)*15 + np.clip(rvol-1,-1,2)*10
        direction = "CE" if directional >= 12 else "PE" if directional <= -12 else "WAIT"
        activity = _clip(abs(directional)*.65 + min(rvol,4)*14 + abs(call_change+put_change)/denom*10)
        participant = "WHALE" if activity >= 85 else "SHARK" if activity >= 65 else "ACTIVE TRADER" if activity >= 45 else "NO LARGE FOOTPRINT"
        behaviour = "AGGRESSIVE BUYING" if direction == "CE" else "AGGRESSIVE SELLING" if direction == "PE" else "MIXED / ABSORPTION"
        return EngineResult(self.name, activity, _vote(direction), [
            f"Options OI bias contributes {oi_bias:+.1f} directional points.",
            f"Latest volume is {rvol:.2f}× recent average.",
            f"Cycle phase is {cycle.get('phase','Unknown')} and stored flow strength is {flow:+.1f}.",
        ], {"activity_score": activity, "participant": participant, "behaviour": behaviour, "direction": direction, "oi_bias": oi_bias, "relative_volume": rvol})


class FalseBreakoutEngine(BaseEngine):
    name = "False Breakout"

    def analyze(self, market_data: DecisionContext | Mapping[str, Any]) -> EngineResult:
        market_data = self._adapt_input(market_data)
        structure = getattr(market_data.get("structure_result"), "metadata", {}) or {}
        candle = getattr(market_data.get("candle_dna_result"), "metadata", {}) or {}
        footprint = getattr(market_data.get("footprint_result"), "metadata", {}) or {}
        manipulation = _num(getattr(market_data.get("cycle_result"), "metadata", {}).get("manipulation_score"))
        primary = structure.get("primary", {})
        confirmed = primary.get("status") == "CONFIRMED"
        weak_volume = _num(candle.get("relative_volume"),1) < 1.05
        conflict = confirmed and primary.get("direction") not in {footprint.get("direction"), "WAIT"}
        risk = _clip(manipulation*.45 + (25 if weak_volume else 0) + (35 if conflict else 0) + (10 if confirmed and _num(candle.get("body_pct")) < 35 else 0))
        label = "HIGH TRAP RISK" if risk >= 70 else "CAUTION" if risk >= 50 else "LOW"
        vote = "BLOCK" if risk >= 70 else "WAIT"
        reasons = []
        if weak_volume: reasons.append("Breakout participation is weak")
        if conflict: reasons.append("Pattern direction conflicts with institutional footprint")
        if manipulation >= 55: reasons.append("Manipulation engine is elevated")
        if not reasons: reasons.append("No major false-breakout conflict detected")
        return EngineResult(self.name, risk, vote, reasons, {"risk_score": risk, "label": label, "blocked": risk >= 70, "reasons": reasons})


    @staticmethod
    def _adapt_input(market_data: DecisionContext | Mapping[str, Any]) -> Mapping[str, Any]:
        """Normalize typed and legacy engine inputs."""
        if not isinstance(market_data, DecisionContext):
            return market_data
        results = market_data.engine_results
        return {
            "structure_result": results.get("institutional_structure"),
            "candle_dna_result": results.get("candle_dna"),
            "footprint_result": results.get("institutional_footprint"),
            "cycle_result": market_data.cycle_result,
        }


class InstitutionalConfirmationEngine(BaseEngine):
    name = "Institutional Confirmation"

    def analyze(self, market_data: dict[str, Any]) -> EngineResult:
        rec = market_data.get("recommendation", {})
        side = rec.get("side", "WAIT")
        inputs = [
            ("Footprint", market_data.get("footprint_result"), .28),
            ("Structure", market_data.get("structure_result"), .22),
            ("Smart Candle", market_data.get("smart_candle_result"), .14),
            ("Candle DNA", market_data.get("candle_dna_result"), .12),
            ("Pattern", market_data.get("pattern_result"), .12),
            ("Cycle", market_data.get("cycle_result"), .12),
        ]
        rows, score, aligned_weight, conflict_weight = [], 0.0, 0.0, 0.0
        for name, result, weight in inputs:
            if result is None: continue
            raw = _clip(_num(getattr(result, "score", 0)))
            vote = str(getattr(result, "vote", "WAIT"))
            aligned = vote in {side, "WAIT"}
            adjusted = raw if aligned else max(0, 100-raw)
            score += adjusted * weight
            aligned_weight += weight if vote == side else 0
            conflict_weight += weight if vote not in {side, "WAIT"} else 0
            rows.append({"engine":name,"vote":vote,"score":round(raw,1),"weight":weight*100,"aligned":aligned})
        false_breakout = market_data.get("false_breakout_result")
        trap = _num(getattr(false_breakout, "score", 0))
        score = _clip(score - trap*.25)
        status = "CONFIRMED" if score >= 80 and conflict_weight <= .14 and trap < 70 else "DEVELOPING" if score >= 60 else "REJECTED"
        vote = side if status == "CONFIRMED" and side in {"CE","PE"} else "WAIT"
        evidence = [f"{sum(1 for r in rows if r['vote']==side)} engines directly support {side}.", f"False-breakout risk is {trap:.0f}/100."]
        return EngineResult(self.name, score, vote, evidence, {"confirmation_score":score,"status":status,"rows":rows,"conflict_weight":conflict_weight*100,"false_breakout_risk":trap})
