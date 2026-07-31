from __future__ import annotations

from typing import Any
from urllib.parse import quote

import pandas as pd
import requests


class UpstoxAPIError(RuntimeError):
    pass


class UpstoxClient:
    BASE_URL_V2 = "https://api.upstox.com/v2"
    BASE_URL_V3 = "https://api.upstox.com/v3"

    def __init__(self, access_token: str, timeout: int = 20) -> None:
        self.access_token = access_token.strip()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

    @staticmethod
    def _raise_for_api_error(response: requests.Response) -> None:
        if response.ok:
            return
        try:
            payload = response.json()
            errors = payload.get("errors") or []
            message = (
                errors[0].get("message")
                if errors and isinstance(errors[0], dict)
                else payload.get("message")
            )
        except ValueError:
            message = response.text
        raise UpstoxAPIError(f"HTTP {response.status_code}: {message or 'Request failed'}")

    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        response = requests.post(
            f"{self.BASE_URL_V2}/login/authorization/token",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "code": code.strip(),
                "client_id": client_id.strip(),
                "client_secret": client_secret.strip(),
                "redirect_uri": redirect_uri.strip(),
                "grant_type": "authorization_code",
            },
            timeout=self.timeout,
        )
        self._raise_for_api_error(response)
        return response.json()

    def get_option_expiries(self, instrument_key: str) -> list[str]:
        response = requests.get(
            f"{self.BASE_URL_V2}/option/contract",
            params={"instrument_key": instrument_key},
            headers=self._headers(),
            timeout=self.timeout,
        )
        self._raise_for_api_error(response)
        payload = response.json()
        expiries = sorted(
            {
                str(contract.get("expiry"))
                for contract in (payload.get("data") or [])
                if contract.get("expiry")
            }
        )
        if not expiries:
            raise UpstoxAPIError(f"No active option expiries found for {instrument_key}.")
        return expiries

    def get_option_chain(self, instrument_key: str, expiry_date: str) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.BASE_URL_V2}/option/chain",
            params={"instrument_key": instrument_key, "expiry_date": expiry_date},
            headers=self._headers(),
            timeout=self.timeout,
        )
        self._raise_for_api_error(response)
        payload = response.json()
        data = payload.get("data") or []
        if not data:
            raise UpstoxAPIError(
                f"No option-chain records returned for instrument_key={instrument_key}, "
                f"expiry_date={expiry_date}."
            )
        return data

    def get_historical_candles(
        self,
        instrument_key: str,
        from_date: str,
        to_date: str,
        interval: int = 5,
        unit: str = "minutes",
    ) -> pd.DataFrame:
        """Retrieve dated OHLC candles from Upstox Historical Candle V3.

        Dates must use YYYY-MM-DD. For minute intervals from 1 to 15, Upstox
        allows up to one month per request, which is more than enough for the
        two-trading-day pattern history used by the dashboard.
        """
        encoded_key = quote(instrument_key, safe="")
        url = (
            f"{self.BASE_URL_V3}/historical-candle/"
            f"{encoded_key}/{unit}/{interval}/{to_date}/{from_date}"
        )
        response = requests.get(url, headers=self._headers(), timeout=self.timeout)
        self._raise_for_api_error(response)
        payload = response.json()
        candles = (payload.get("data") or {}).get("candles") or []
        if not candles:
            raise UpstoxAPIError(
                f"No historical candles returned for {instrument_key} "
                f"between {from_date} and {to_date}."
            )
        return self.candles_to_dataframe(candles)

    def get_intraday_candles(
        self,
        instrument_key: str,
        interval: int = 5,
        unit: str = "minutes",
    ) -> pd.DataFrame:
        encoded_key = quote(instrument_key, safe="")
        url = (
            f"{self.BASE_URL_V3}/historical-candle/intraday/"
            f"{encoded_key}/{unit}/{interval}"
        )
        response = requests.get(url, headers=self._headers(), timeout=self.timeout)
        self._raise_for_api_error(response)
        payload = response.json()
        candles = (payload.get("data") or {}).get("candles") or []
        if not candles:
            raise UpstoxAPIError(f"No intraday candles returned for {instrument_key}.")
        return self.candles_to_dataframe(candles)

    @staticmethod
    def candles_to_dataframe(candles: list[list[Any]]) -> pd.DataFrame:
        rows = []
        for candle in candles:
            if len(candle) < 6:
                continue
            rows.append(
                {
                    "timestamp": candle[0],
                    "open": candle[1],
                    "high": candle[2],
                    "low": candle[3],
                    "close": candle[4],
                    "volume": candle[5],
                    "oi": candle[6] if len(candle) > 6 else 0,
                }
            )
        df = pd.DataFrame(rows)
        if df.empty:
            raise UpstoxAPIError("Candle response did not contain usable OHLC records.")
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        numeric = ["open", "high", "low", "close", "volume", "oi"]
        df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
        df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
        return df.sort_values("timestamp").reset_index(drop=True)

    @staticmethod
    def option_chain_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []

        def value(mapping: dict[str, Any], key: str, default: float = 0.0) -> float:
            raw = mapping.get(key, default)
            return default if raw is None else raw

        for item in records:
            call = item.get("call_options") or {}
            put = item.get("put_options") or {}
            cmd = call.get("market_data") or {}
            pmd = put.get("market_data") or {}
            cg = call.get("option_greeks") or {}
            pg = put.get("option_greeks") or {}

            call_ltp = value(cmd, "ltp")
            put_ltp = value(pmd, "ltp")
            call_close = value(cmd, "close_price")
            put_close = value(pmd, "close_price")
            call_oi = value(cmd, "oi")
            put_oi = value(pmd, "oi")
            call_prev_oi = value(cmd, "prev_oi")
            put_prev_oi = value(pmd, "prev_oi")

            rows.append({
                "expiry": item.get("expiry"),
                "spot": value(item, "underlying_spot_price"),
                "strike": value(item, "strike_price"),
                "strike_pcr": value(item, "pcr"),
                "call_instrument_key": call.get("instrument_key", ""),
                "call_ltp": call_ltp,
                "call_close": call_close,
                "call_price_change": call_ltp - call_close,
                "call_volume": value(cmd, "volume"),
                "call_oi": call_oi,
                "call_prev_oi": call_prev_oi,
                "call_oi_change": call_oi - call_prev_oi,
                "call_bid": value(cmd, "bid_price"),
                "call_ask": value(cmd, "ask_price"),
                "call_iv": value(cg, "iv"),
                "call_delta": value(cg, "delta"),
                "call_gamma": value(cg, "gamma"),
                "call_theta": value(cg, "theta"),
                "call_vega": value(cg, "vega"),
                "call_pop": value(cg, "pop"),
                "put_instrument_key": put.get("instrument_key", ""),
                "put_ltp": put_ltp,
                "put_close": put_close,
                "put_price_change": put_ltp - put_close,
                "put_volume": value(pmd, "volume"),
                "put_oi": put_oi,
                "put_prev_oi": put_prev_oi,
                "put_oi_change": put_oi - put_prev_oi,
                "put_bid": value(pmd, "bid_price"),
                "put_ask": value(pmd, "ask_price"),
                "put_iv": value(pg, "iv"),
                "put_delta": value(pg, "delta"),
                "put_gamma": value(pg, "gamma"),
                "put_theta": value(pg, "theta"),
                "put_vega": value(pg, "vega"),
                "put_pop": value(pg, "pop"),
            })

        df = pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)
        text_columns = {"expiry", "call_instrument_key", "put_instrument_key"}
        numeric = [column for column in df.columns if column not in text_columns]
        df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce").fillna(0)
        return df
