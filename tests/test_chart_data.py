"""Visible-window filtering, axis fitting and candlestick figure tests."""

import numpy as np
import pandas as pd
import pytest

from components.candlestick_chart import create_candlestick_figure
from services.chart_data import (
    ChartDataError,
    aggregate_ohlcv,
    calculate_price_axis_range,
    calculate_volume_axis_range,
    filter_data_by_period,
)
from services.indicators import calculate_indicators


def history(size: int = 300) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=size, freq="B")
    trend = np.linspace(10, 40, size)
    close = trend + np.sin(np.arange(size) / 5)
    raw = pd.DataFrame({
        "date": dates, "open": close - 0.2, "high": close + 0.7,
        "low": close - 0.8, "close": close,
        "volume": np.linspace(1_000_000, 8_000_000, size),
    })
    return calculate_indicators(raw)


def test_period_filter_uses_cached_full_indicators_then_slices() -> None:
    full = history()
    one_month = filter_data_by_period(full, "1M")
    three_months = filter_data_by_period(full, "3M")
    one_year = filter_data_by_period(full, "1Y")
    assert 20 <= len(one_month) <= 24
    assert len(one_month) < len(three_months) < len(one_year)
    matching = full.loc[full["date"] == one_month.iloc[0]["date"], "ma60"].iloc[0]
    assert one_month.iloc[0]["ma60"] == pytest.approx(matching)


def test_price_and_volume_axes_fit_only_visible_window() -> None:
    full = history()
    one_month = filter_data_by_period(full, "1M")
    one_year = filter_data_by_period(full, "1Y")
    month_price = calculate_price_axis_range(one_month)
    year_price = calculate_price_axis_range(one_year)
    assert month_price[0] > year_price[0]
    assert month_price[0] < float(one_month["low"].min())
    assert month_price[1] > float(one_month["high"].max())
    assert calculate_volume_axis_range(one_month)[1] == pytest.approx(one_month["volume"].max() * 1.1)


def test_figure_has_stable_height_independent_axes_and_no_duplicate_traces() -> None:
    visible = filter_data_by_period(history(), "3M")
    figure = create_candlestick_figure(visible, "3M", "test")
    names = [trace.name for trace in figure.data]
    assert len(names) == len(set(names))
    assert figure.layout.height == 720
    assert figure.layout.xaxis.rangeslider.visible is False
    assert tuple(figure.layout.yaxis.range) == pytest.approx(calculate_price_axis_range(visible))
    assert tuple(figure.layout.yaxis2.range) == pytest.approx(calculate_volume_axis_range(visible))
    assert len(figure.data[0].x) == len(visible)


def test_empty_and_invalid_period_are_rejected() -> None:
    with pytest.raises(ChartDataError):
        filter_data_by_period(pd.DataFrame(), "1M")
    with pytest.raises(ChartDataError):
        filter_data_by_period(history(), "ALL")


def test_extended_periods_and_max() -> None:
    full = history(1600)
    three_years = filter_data_by_period(full, "3Y")
    five_years = filter_data_by_period(full, "5Y")
    maximum = filter_data_by_period(full, "MAX")
    assert len(three_years) < len(five_years) < len(maximum)
    assert len(maximum) == len(full)
    assert maximum.iloc[0]["date"] == full.iloc[0]["date"]


def test_weekly_and_monthly_ohlcv_aggregation() -> None:
    daily = pd.DataFrame({
        "date": pd.to_datetime([
            "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
            "2026-01-12", "2026-01-13",
        ]),
        "open": [10, 11, 12, 13, 14, 20, 21],
        "high": [12, 13, 14, 15, 16, 22, 23],
        "low": [9, 8, 11, 10, 13, 19, 18],
        "close": [11, 12, 13, 14, 15, 21, 22],
        "volume": [100, 200, 300, 400, 500, 600, 700],
        "amount": [1000, 2000, 3000, 4000, 5000, 6000, 7000],
    })
    weekly = aggregate_ohlcv(daily, "周K")
    first = weekly.iloc[0]
    assert first["date"] == pd.Timestamp("2026-01-09")
    assert first["open"] == 10
    assert first["high"] == 16
    assert first["low"] == 8
    assert first["close"] == 15
    assert first["volume"] == 1500
    assert first["amount"] == 15000
    monthly = aggregate_ohlcv(daily, "月K")
    assert len(monthly) == 1
    assert monthly.iloc[0]["open"] == 10
    assert monthly.iloc[0]["close"] == 22
    assert monthly.iloc[0]["volume"] == 2800


def test_aggregation_date_never_moves_beyond_last_real_bar() -> None:
    daily = history(8).loc[:, ["date", "open", "high", "low", "close", "volume"]]
    weekly = aggregate_ohlcv(daily, "周K")
    monthly = aggregate_ohlcv(daily, "月K")
    assert weekly["date"].max() == daily["date"].max()
    assert monthly["date"].max() == daily["date"].max()


def test_all_missing_amount_stays_missing_after_aggregation() -> None:
    daily = history(8).loc[:, ["date", "open", "high", "low", "close", "volume"]]
    daily["amount"] = np.nan
    weekly = aggregate_ohlcv(daily, "周K")
    assert weekly["amount"].isna().all()
