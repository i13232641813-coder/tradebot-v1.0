"""Historical market clock that exposes no bars after the simulation date."""

from __future__ import annotations

from datetime import date

import pandas as pd


class MarketClockError(ValueError):
    pass


EARLIEST_A_SHARE_HISTORY_DATE = date(1990, 1, 1)


def history_request_start(simulation_start: date) -> date:
    """Request the longest practical A-share history available from Yahoo."""
    if simulation_start < EARLIEST_A_SHARE_HISTORY_DATE:
        raise MarketClockError("模拟开始日期不能早于 1990-01-01")
    return EARLIEST_A_SHARE_HISTORY_DATE


class HistoricalMarketClock:
    def __init__(self, daily_bars: pd.DataFrame) -> None:
        if "date" not in daily_bars.columns:
            raise MarketClockError("历史行情缺少 date 字段")
        self._bars = daily_bars.copy()
        self._bars["date"] = pd.to_datetime(self._bars["date"], errors="coerce").dt.date
        self._bars = self._bars.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        if self._bars.empty:
            raise MarketClockError("历史行情为空")

    def normalize_start_date(self, requested: date) -> date:
        candidates = self._bars.loc[self._bars["date"] >= requested, "date"]
        if candidates.empty:
            raise MarketClockError("开始日期之后没有可用交易日")
        return candidates.iloc[0]

    def next_trading_date(self, current: date) -> date:
        candidates = self._bars.loc[self._bars["date"] > current, "date"]
        if candidates.empty:
            raise MarketClockError("已经到达可用历史行情的最后交易日")
        return candidates.iloc[0]

    def visible_bars(self, current: date) -> pd.DataFrame:
        """Return a defensive copy containing no future rows."""
        return self._bars.loc[self._bars["date"] <= current].copy().reset_index(drop=True)

    def bar_on(self, trading_date: date) -> pd.Series:
        rows = self._bars.loc[self._bars["date"] == trading_date]
        if rows.empty:
            raise MarketClockError(f"{trading_date} 没有日线行情")
        return rows.iloc[-1].copy()
