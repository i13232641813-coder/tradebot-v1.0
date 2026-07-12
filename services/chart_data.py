"""Pure data preparation helpers for responsive financial charts."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

PERIOD_OFFSETS = {
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6),
    "1Y": pd.DateOffset(years=1),
    "3Y": pd.DateOffset(years=3),
    "5Y": pd.DateOffset(years=5),
    "MAX": None,
}

INTERVAL_RULES = {"日K": None, "周K": "W-FRI", "月K": "ME"}


class ChartDataError(ValueError):
    pass


def filter_data_by_period(
    frame: pd.DataFrame,
    period: str,
    end_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return a sorted visible slice ending at the latest allowed date."""
    if frame.empty:
        raise ChartDataError("没有可用于绘图的行情数据")
    if period not in PERIOD_OFFSETS:
        raise ChartDataError(f"不支持的图表周期：{period}")
    if "date" not in frame.columns:
        raise ChartDataError("行情缺少 date 字段")
    dates = pd.to_datetime(frame["date"], errors="coerce")
    valid_dates = dates.dropna()
    if valid_dates.empty:
        raise ChartDataError("行情日期全部无效")
    allowed_end = pd.Timestamp(end_date) if end_date is not None else valid_dates.max()
    offset = PERIOD_OFFSETS[period]
    start = valid_dates.min() if offset is None else allowed_end - offset
    mask = dates.between(start, allowed_end, inclusive="both")
    visible = frame.loc[mask].copy()
    visible["date"] = dates.loc[mask]
    visible = visible.sort_values("date").reset_index(drop=True)
    if visible.empty:
        raise ChartDataError(f"{period} 周期内没有可用行情")
    return visible


def aggregate_ohlcv(frame: pd.DataFrame, interval: str) -> pd.DataFrame:
    """Aggregate full daily history into correct weekly or monthly OHLCV bars."""
    if interval not in INTERVAL_RULES:
        raise ChartDataError(f"不支持的K线粒度：{interval}")
    if frame.empty:
        raise ChartDataError("没有可聚合的行情数据")
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ChartDataError(f"行情缺少聚合字段：{', '.join(sorted(missing))}")
    daily = frame.copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    daily = daily.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if interval == "日K":
        return daily
    rule = INTERVAL_RULES[interval]
    indexed = daily.set_index("date", drop=False)
    aggregation = {
        "date": "max", "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": lambda values: values.sum(min_count=1),
    }
    if "amount" in indexed.columns:
        aggregation["amount"] = lambda values: values.sum(min_count=1)
    result = indexed.resample(rule).agg(aggregation)
    result = result.dropna(subset=["date", "open", "high", "low", "close"]).reset_index(drop=True)
    result["change"] = result["close"].diff()
    result["change_pct"] = result["close"].pct_change() * 100
    return result


def calculate_price_axis_range(
    visible: pd.DataFrame,
    enabled_overlays: Sequence[str] = ("ma5", "ma10", "ma20", "ma60"),
) -> tuple[float, float]:
    """Calculate a padded price axis from only the currently visible rows."""
    candidates: list[np.ndarray] = []
    for column in ("low", "high", *enabled_overlays):
        if column in visible.columns:
            values = pd.to_numeric(visible[column], errors="coerce").to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            if finite.size:
                candidates.append(finite)
    if not candidates:
        raise ChartDataError("当前周期没有有效价格数据")
    combined = np.concatenate(candidates)
    visible_min = float(combined.min())
    visible_max = float(combined.max())
    close = pd.to_numeric(visible.get("close"), errors="coerce").dropna()
    latest_close = abs(float(close.iloc[-1])) if not close.empty else max(abs(visible_max), 1.0)
    padding = max((visible_max - visible_min) * 0.05, latest_close * 0.005, 1e-8)
    return visible_min - padding, visible_max + padding


def calculate_volume_axis_range(visible: pd.DataFrame) -> tuple[float, float]:
    """Calculate an independent volume axis from the visible rows."""
    if "volume" not in visible.columns:
        raise ChartDataError("行情缺少 volume 字段")
    volume = pd.to_numeric(visible["volume"], errors="coerce")
    finite = volume[np.isfinite(volume) & (volume >= 0)]
    if finite.empty:
        raise ChartDataError("当前周期没有有效成交量数据")
    maximum = float(finite.max())
    return 0.0, maximum * 1.1 if maximum > 0 else 1.0


def non_trading_dates(visible: pd.DataFrame) -> list[str]:
    """Return missing calendar dates so holidays do not create wide gaps."""
    dates = pd.DatetimeIndex(pd.to_datetime(visible["date"], errors="coerce").dropna().dt.normalize().unique())
    if dates.empty:
        return []
    calendar = pd.date_range(dates.min(), dates.max(), freq="D")
    missing = calendar.difference(dates)
    return [item.strftime("%Y-%m-%d") for item in missing]
