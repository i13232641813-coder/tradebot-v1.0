"""Market-data provider mapping tests that do not require network access."""

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
