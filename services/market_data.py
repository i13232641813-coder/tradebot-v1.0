"""Replaceable market data providers for A-share daily history."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging

import akshare as ak
import numpy as np
import pandas as pd
import yfinance as yf

LOGGER = logging.getLogger(__name__)


class MarketDataError(RuntimeError):
    """Raised when trustworthy market data cannot be obtained."""


@dataclass(frozen=True)
class StockHistory:
    code: str
    name: str
    prices: pd.DataFrame


@dataclass(frozen=True)
class LatestQuote:
    """Latest available intraday quote with its source timestamp."""

    code: str
    price: float
    timestamp: datetime
    open: float
    high: float
    low: float
    volume: float
    source: str = "Yahoo Finance 1分钟行情"


class MarketDataProvider(ABC):
    """Replaceable market data provider contract."""

    @abstractmethod
    def get_stock_history(self, code: str, start: date, end: date) -> StockHistory:
        """Return normalized, forward-adjusted daily prices."""


class YahooMarketDataProvider(MarketDataProvider):
    """A-share daily history provider backed by Yahoo Finance."""

    REQUIRED = {"date", "open", "close", "high", "low", "volume"}

    @staticmethod
    def yahoo_symbol(code: str) -> str:
        """Map mainland codes to Yahoo suffixes and preserve US tickers."""
        if not code.isdigit():
            return code.upper()
        if code.startswith(("0", "1", "2", "3")):
            return f"{code}.SZ"
        if code.startswith(("5", "6", "9")):
            return f"{code}.SS"
        if code.startswith(("4", "8")):
            return f"{code}.BJ"
        raise MarketDataError("暂不支持该六位代码对应的 A 股交易所")

    def get_stock_history(self, code: str, start: date, end: date) -> StockHistory:
        symbol = self.yahoo_symbol(code)
        try:
            ticker = yf.Ticker(symbol)
            history_options = {
                "interval": "1d", "auto_adjust": True, "actions": False, "timeout": 15,
            }
            if start <= date(1990, 1, 1):
                # Yahoo rejects some valid A-shares when an artificial pre-listing
                # start date is supplied. period=max returns its earliest coverage.
                raw = ticker.history(period="max", **history_options)
                if raw is None or raw.empty:
                    # Some Yahoo sessions reject period=max. Preserve the normal
                    # bounded request as a fallback instead of returning fake data.
                    raw = ticker.history(
                        start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                        **history_options,
                    )
            else:
                # Yahoo treats end as exclusive, so include one extra calendar day.
                raw = ticker.history(
                    start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                    **history_options,
                )
        except Exception as exc:
            LOGGER.exception("Yahoo history request failed for %s", symbol)
            raise MarketDataError("Yahoo Finance 行情暂时不可用，请检查网络后重试") from exc
        if raw is None or raw.empty:
            raise MarketDataError("Yahoo Finance 未找到该股票行情，请确认代码或稍后重试")

        frame = raw.reset_index().rename(columns={
            "Date": "date", "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        missing = self.REQUIRED.difference(frame.columns)
        if missing:
            raise MarketDataError(f"Yahoo 行情字段发生变化，缺少：{', '.join(sorted(missing))}")
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.tz_localize(None)
        numeric = ["open", "high", "low", "close", "volume"]
        frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
        frame = frame.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date")
        if frame.empty:
            raise MarketDataError("Yahoo Finance 返回的行情数据无法解析")
        frame["amount"] = np.nan  # Yahoo daily history does not provide turnover amount.
        frame["change"] = frame["close"].diff()
        frame["change_pct"] = frame["close"].pct_change() * 100

        name = symbol
        try:
            info = ticker.get_info()
            name = str(info.get("shortName") or info.get("longName") or symbol)
        except Exception:
            # A valid history is still useful; never fail it solely because metadata failed.
            LOGGER.warning("Yahoo metadata unavailable for %s", symbol, exc_info=True)
        return StockHistory(code=code, name=name, prices=frame.reset_index(drop=True))

    def get_latest_quote(self, code: str) -> LatestQuote:
        """Return Yahoo's latest available one-minute quote (possibly delayed)."""
        symbol = self.yahoo_symbol(code)
        try:
            raw = yf.Ticker(symbol).history(
                period="5d", interval="1m", auto_adjust=False,
                actions=False, timeout=15,
            )
        except Exception as exc:
            LOGGER.exception("Yahoo intraday request failed for %s", symbol)
            raise MarketDataError("最新分钟行情暂时不可用，已保留日线数据") from exc
        if raw is None or raw.empty:
            raise MarketDataError("Yahoo Finance 暂无该股票的分钟行情")
        raw = raw.dropna(subset=["Close"]).sort_index()
        if raw.empty:
            raise MarketDataError("Yahoo Finance 分钟行情无法解析")
        last_timestamp = raw.index[-1]
        session = raw[raw.index.date == last_timestamp.date()]
        latest = session.iloc[-1]
        timestamp = last_timestamp.to_pydatetime()
        return LatestQuote(
            code=code,
            price=float(latest["Close"]),
            timestamp=timestamp,
            open=float(session.iloc[0]["Open"]),
            high=float(session["High"].max()),
            low=float(session["Low"].min()),
            volume=float(session["Volume"].sum()),
        )


class AkShareMarketDataProvider(MarketDataProvider):
    """A-share daily history provider backed by AkShare."""

    COLUMN_MAP = {
        "日期": "date", "开盘": "open", "收盘": "close", "最高": "high",
        "最低": "low", "成交量": "volume", "成交额": "amount",
        "涨跌额": "change", "涨跌幅": "change_pct",
    }
    REQUIRED = {"date", "open", "close", "high", "low", "volume"}

    def _stock_name(self, code: str) -> str:
        try:
            info = ak.stock_individual_info_em(symbol=code)
            if info.empty or not {"item", "value"}.issubset(info.columns):
                raise MarketDataError("股票基本信息为空或字段发生变化")
            names = info.loc[info["item"].astype(str).eq("股票简称"), "value"]
            return str(names.iloc[0]) if not names.empty else code
        except MarketDataError:
            raise
        except Exception as exc:
            LOGGER.exception("Failed to fetch stock name for %s", code)
            raise MarketDataError("无法获取股票名称，请稍后重试") from exc

    def get_stock_history(self, code: str, start: date, end: date) -> StockHistory:
        try:
            raw = ak.stock_zh_a_hist(
                symbol=code, period="daily", start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"), adjust="qfq",
            )
        except Exception as exc:
            LOGGER.exception("Failed to fetch history for %s", code)
            raise MarketDataError("行情服务暂时不可用，请检查网络后重试") from exc
        if raw is None or raw.empty:
            raise MarketDataError("未找到该股票的行情数据，请确认股票代码")
        frame = raw.rename(columns=self.COLUMN_MAP).copy()
        missing = self.REQUIRED.difference(frame.columns)
        if missing:
            raise MarketDataError(f"行情字段发生变化，缺少：{', '.join(sorted(missing))}")
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        numeric = [column for column in frame.columns if column != "date"]
        frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
        frame = frame.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date")
        if frame.empty:
            raise MarketDataError("行情数据无法解析")
        return StockHistory(code=code, name=self._stock_name(code), prices=frame.reset_index(drop=True))


def default_history_range() -> tuple[date, date]:
    """Use a buffer beyond one year to cover holidays and chart windows."""
    end = date.today()
    return end - timedelta(days=400), end


def full_history_range() -> tuple[date, date]:
    """Request the longest practical mainland/US equity history."""
    return date(1990, 1, 1), date.today()
