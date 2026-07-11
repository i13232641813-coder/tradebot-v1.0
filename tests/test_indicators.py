"""Core technical indicator tests."""

import numpy as np
import pandas as pd

from services.indicators import calculate_indicators, latest_statuses


def sample_prices(size: int = 100) -> pd.DataFrame:
    close = pd.Series(np.linspace(10, 30, size)) + np.sin(np.arange(size) / 4)
    return pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=size, freq="B"),
        "open": close - 0.2, "high": close + 0.5, "low": close - 0.5,
        "close": close, "volume": np.linspace(10_000, 20_000, size),
    })


def test_macd_columns_length_and_warmup() -> None:
    result = calculate_indicators(sample_prices())
    assert len(result) == 100
    assert {"dif", "dea", "macd_hist"}.issubset(result.columns)
    assert result["dif"].iloc[:25].isna().all()
    assert result["macd_hist"].iloc[-1] == 2 * (result["dif"].iloc[-1] - result["dea"].iloc[-1])


def test_rsi_wilder_bounds_and_nan_handling() -> None:
    result = calculate_indicators(sample_prices())
    assert "rsi14" in result
    assert result["rsi14"].iloc[:14].isna().all()
    assert result["rsi14"].dropna().between(0, 100).all()


def test_boll_columns_and_warmup() -> None:
    result = calculate_indicators(sample_prices())
    assert {"boll_upper", "boll_mid", "boll_lower"}.issubset(result.columns)
    assert result["boll_mid"].iloc[:19].isna().all()
    assert (result["boll_upper"].dropna() >= result["boll_mid"].dropna()).all()
    assert (result["boll_lower"].dropna() <= result["boll_mid"].dropna()).all()


def test_short_history_does_not_raise() -> None:
    result = calculate_indicators(sample_prices(8))
    statuses = latest_statuses(result)
    assert len(result) == 8
    assert statuses["rsi"].state == "数据不足"
