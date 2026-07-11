"""Display formatting edge cases."""

import numpy as np

from utils.formatters import compact_cn, percent, price


def test_missing_values_display_dash() -> None:
    assert price(np.nan) == "-"
    assert percent(np.nan) == "-"
    assert compact_cn(np.nan) == "-"


def test_numeric_formats() -> None:
    assert price(12.345) == "12.35"
    assert percent(-1.234) == "-1.23%"
    assert compact_cn(12345, "股") == "1.23万股"
