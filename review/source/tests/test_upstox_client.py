from urllib.parse import urlparse

import pandas as pd

from upstox_client import UpstoxClient


ROW = ["2026-07-31T09:15:00+05:30", 100, 102, 99, 101, 1000, 50]


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.ok = status == 200

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _payload(candles):
    return {"status": "success", "data": {"candles": candles}}


def test_successful_v3_intraday_response(monkeypatch):
    urls = []
    monkeypatch.setattr("upstox_client.requests.get", lambda url, **_: urls.append(url) or Response(_payload([ROW])))

    result = UpstoxClient("secret").get_intraday_candles("NSE_INDEX|Nifty 50")

    assert len(result) == 1
    assert urlparse(urls[0]).path == "/v3/historical-candle/intraday/NSE_INDEX%7CNifty%2050/minutes/5"


def test_empty_intraday_uses_latest_historical_trading_day(monkeypatch):
    older = ["2026-07-30T15:25:00+05:30", 99, 100, 98, 99, 800, 40]
    responses = iter([Response(_payload([])), Response(_payload([older, ROW]))])
    monkeypatch.setattr("upstox_client.requests.get", lambda *_, **__: next(responses))

    result = UpstoxClient("secret").get_intraday_candles("NSE_INDEX|Nifty 50", interval=5)

    assert len(result) == 1
    assert result.iloc[0]["close"] == 101


def test_both_endpoints_empty_returns_typed_empty_frame(monkeypatch):
    monkeypatch.setattr("upstox_client.requests.get", lambda *_, **__: Response(_payload(None)))

    result = UpstoxClient("secret").get_intraday_candles("NSE_INDEX|Nifty 50")

    assert result.empty
    assert list(result.columns) == ["timestamp", "open", "high", "low", "close", "volume", "oi"]


def test_malformed_response_and_candle_rows_are_ignored(monkeypatch):
    responses = iter([Response(_payload([None, ["short"]])), Response(ValueError("bad json"))])
    monkeypatch.setattr("upstox_client.requests.get", lambda *_, **__: next(responses))

    assert UpstoxClient("secret").get_intraday_candles("NSE_INDEX|Nifty 50").empty


def test_invalid_instrument_response_falls_back_safely(monkeypatch, caplog):
    payload = {"status": "error", "errors": [{"errorCode": "UDAPI100011", "message": "Invalid Instrument key"}]}
    monkeypatch.setattr("upstox_client.requests.get", lambda *_, **__: Response(payload, 400))

    with caplog.at_level("INFO"):
        result = UpstoxClient("do-not-log-me").get_intraday_candles("INVALID")

    assert result.empty
    assert "UDAPI100011" in caplog.text
    assert "Invalid Instrument key" in caplog.text
    assert "do-not-log-me" not in caplog.text


def test_error_mapping_logs_code_and_message_and_returns_empty(monkeypatch, caplog):
    payload = {"errors": {"errorCode": "E-MAP", "message": "Mapped error"}}
    monkeypatch.setattr("upstox_client.requests.get", lambda *_, **__: Response(payload, 400))

    with caplog.at_level("INFO"):
        result = UpstoxClient("secret").get_historical_candles("INVALID", "2026-01-01", "2026-01-01")

    assert result.empty
    assert "error_code=E-MAP" in caplog.text
    assert "error_message=Mapped error" in caplog.text


def test_missing_message_and_empty_errors_use_safe_defaults(monkeypatch, caplog):
    responses = iter((Response({"errors": [{"errorCode": "E-NO-MESSAGE"}]}, 400),
                      Response({"errors": []}, 400)))
    monkeypatch.setattr("upstox_client.requests.get", lambda *_, **__: next(responses))
    client = UpstoxClient("secret")

    with caplog.at_level("INFO"):
        assert client.get_historical_candles("INVALID", "2026-01-01", "2026-01-01").empty
        assert client.get_historical_candles("INVALID", "2026-01-01", "2026-01-01").empty

    assert "error_code=E-NO-MESSAGE error_message=" in caplog.text
    assert "error_code= error_message=" in caplog.text


def test_top_level_message_is_used_and_multiline_is_single_line(monkeypatch, caplog):
    payload = {"errorCode": "E-TOP", "message": "Invalid\nInstrument\tkey"}
    monkeypatch.setattr("upstox_client.requests.get", lambda *_, **__: Response(payload, 400))

    with caplog.at_level("INFO"):
        UpstoxClient("secret").get_historical_candles("INVALID", "2026-01-01", "2026-01-01")

    assert "error_code=E-TOP" in caplog.text
    assert "error_message=Invalid Instrument key" in caplog.text
    assert "Invalid\nInstrument" not in caplog.text


def test_long_message_is_truncated_and_token_values_are_redacted(monkeypatch, caplog):
    token = "sensitive-access-token"
    message = f"Bearer {token} access_token={token} " + "x" * 500
    monkeypatch.setattr("upstox_client.requests.get", lambda *_, **__: Response({"message": message}, 400))

    with caplog.at_level("INFO"):
        result = UpstoxClient(token).get_historical_candles("INVALID", "2026-01-01", "2026-01-01")

    assert result.empty
    assert token not in caplog.text
    logged_message = caplog.text.split("error_message=", 1)[1].split(" candle_count=", 1)[0]
    assert len(logged_message) <= 256
    assert logged_message.endswith("...")


def test_invalid_intraday_still_uses_historical_fallback(monkeypatch):
    urls = []
    responses = iter((Response({"errors": [{"message": "Invalid Instrument key"}]}, 400),
                      Response(_payload([ROW]))))
    monkeypatch.setattr("upstox_client.requests.get", lambda url, **_: urls.append(url) or next(responses))

    result = UpstoxClient("secret").get_intraday_candles("INVALID")

    assert len(result) == 1
    assert "/historical-candle/intraday/" in urls[0]
    assert "/historical-candle/INVALID/minutes/5/" in urls[1]


def test_preencoded_instrument_key_is_not_double_encoded(monkeypatch):
    urls = []
    monkeypatch.setattr("upstox_client.requests.get", lambda url, **_: urls.append(url) or Response(_payload([ROW])))

    UpstoxClient("secret").get_intraday_candles("NSE_INDEX%7CNifty%2050")

    assert "%257C" not in urls[0]
    assert "NSE_INDEX%7CNifty%2050" in urls[0]
