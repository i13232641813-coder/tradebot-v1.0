"""Market-data provider mapping tests that do not require network access."""

from datetime import date

import pandas as pd
import pytest

from services.market_data import MarketDataError, YahooMarketDataProvider


@pytest.mark.parametrize(("code", "symbol"), [
    ("000938", "000938.SZ"),
    ("600584", "600584.SS"),
    ("688001", "688001.SS"),
    ("430047", "430047.BJ"),
    ("AAPL", "AAPL"),
    ("brk-b", "BRK-B"),
])
def test_yahoo_symbol_mapping(code: str, symbol: str) -> None:
    assert YahooMarketDataProvider.yahoo_symbol(code) == symbol


def test_yahoo_symbol_rejects_unknown_prefix() -> None:
    with pytest.raises(MarketDataError):
        YahooMarketDataProvider.yahoo_symbol("700000")


def test_listing_history_uses_yahoo_max_period(monkeypatch) -> None:
    calls = []

    class FakeTicker:
        def history(self, **kwargs):
            calls.append(kwargs)
            return pd.DataFrame({
                "Open": [10.0], "High": [11.0], "Low": [9.0],
                "Close": [10.5], "Volume": [1000],
            }, index=pd.DatetimeIndex(["2000-01-04"], name="Date"))

        def get_info(self):
            return {"shortName": "Test"}

    monkeypatch.setattr("services.market_data.yf.Ticker", lambda symbol: FakeTicker())
    history = YahooMarketDataProvider().get_stock_history(
        "000938", date(1990, 1, 1), date(2026, 1, 1)
    )
    assert calls[0]["period"] == "max"
    assert "start" not in calls[0]
    assert len(history.prices) == 1
