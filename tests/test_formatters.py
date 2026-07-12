"""Display formatting edge cases."""

import numpy as np

from utils.formatters import compact_cn, currency_compact, currency_full, percent, price


def test_missing_values_display_dash() -> None:
    assert price(np.nan) == "-"
    assert percent(np.nan) == "-"
    assert compact_cn(np.nan) == "-"


def test_numeric_formats() -> None:
    assert price(12.345) == "12.35"
    assert percent(-1.234) == "-1.23%"
    assert compact_cn(12345, "股") == "1.23万股"


def test_large_currency_uses_compact_units() -> None:
    assert currency_compact(100_000) == "¥10.00万"
    assert currency_compact(123_456_789) == "¥1.23亿"
    assert currency_compact(-25_000) == "¥-2.50万"
    assert currency_full(100_000) == "¥100,000.00"
