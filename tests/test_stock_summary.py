"""Latest quote data structure behavior."""

from datetime import datetime

from components.stock_summary import _currency, _market_price
from services.market_data import LatestQuote


def test_latest_quote_preserves_timestamp_and_price() -> None:
    quote = LatestQuote("000938", 38.18, datetime(2026, 7, 10, 14, 59), 37.0, 38.5, 36.8, 1000)
    assert quote.price == 38.18
    assert quote.timestamp.minute == 59


def test_market_currency_units() -> None:
    assert _currency("000938") == ("¥", "CNY")
    assert _currency("AAPL") == ("$", "USD")
    assert _market_price(35.68, "¥") == "¥35.68"
    assert _market_price(315.29, "$") == "$315.29"
