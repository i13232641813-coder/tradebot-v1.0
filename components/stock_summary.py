"""Stock overview cards."""

import pandas as pd
import streamlit as st

from services.market_data import LatestQuote, StockHistory
from utils.formatters import compact_cn, percent, price


def _currency(code: str) -> tuple[str, str]:
    """Return the display symbol and ISO currency for the selected market."""
    return ("¥", "CNY") if code.isdigit() else ("$", "USD")


def _market_price(value: object, symbol: str) -> str:
    formatted = price(value)
    return formatted if formatted == "-" else f"{symbol}{formatted}"


def render_stock_summary(stock: StockHistory, quote: LatestQuote | None = None) -> None:
    """Render an intraday quote when available and disclose its timestamp."""
    daily = stock.prices.iloc[-1]
    quote_date = quote.timestamp.date() if quote is not None else None
    daily_date = pd.Timestamp(daily["date"]).date()
    previous_close = (
        stock.prices.iloc[-2]["close"]
        if quote_date == daily_date and len(stock.prices) > 1
        else daily["close"]
    )
    currency_symbol, currency_code = _currency(stock.code)
    if quote is not None:
        change = quote.price - previous_close
        change_pct = change / previous_close * 100 if previous_close else pd.NA
        st.subheader(f"{stock.name} · {stock.code}")
        st.caption(
            f"最新分钟行情（可能延迟）｜时间：{quote.timestamp:%Y-%m-%d %H:%M %Z}｜"
            f"币种：{currency_code}｜数据源：{quote.source}｜日线指标截止：{daily['date']:%Y-%m-%d}"
        )
        first = st.columns(5)
        values = [quote.price, change, change_pct, quote.open, previous_close]
        labels = ["最新分钟价", "涨跌额", "涨跌幅", "今开", "前收盘"]
        for column, label, value in zip(first, labels, values):
            column.metric(label, percent(value) if label == "涨跌幅" else _market_price(value, currency_symbol))
        second = st.columns(4)
        second[0].metric("今日最高", _market_price(quote.high, currency_symbol))
        second[1].metric("今日最低", _market_price(quote.low, currency_symbol))
        second[2].metric("今日分钟成交量合计", compact_cn(quote.volume, "股"))
        second[3].metric("成交额", "-")
        return

    previous = stock.prices.iloc[-2]["close"] if len(stock.prices) > 1 else pd.NA
    change = daily.get("change", daily["close"] - previous if not pd.isna(previous) else pd.NA)
    change_pct = daily.get("change_pct", change / previous * 100 if not pd.isna(previous) else pd.NA)
    st.subheader(f"{stock.name} · {stock.code}")
    st.caption(f"前复权日线｜数据日期：{daily['date']:%Y-%m-%d}｜币种：{currency_code}｜价格口径：最近收盘（分钟行情不可用）")
    first = st.columns(5)
    for column, label, value in zip(first, ["最近收盘", "涨跌额", "涨跌幅", "今开", "昨收"], [daily["close"], change, change_pct, daily["open"], previous]):
        column.metric(label, percent(value) if label == "涨跌幅" else _market_price(value, currency_symbol))
    second = st.columns(4)
    second[0].metric("最高", _market_price(daily["high"], currency_symbol))
    second[1].metric("最低", _market_price(daily["low"], currency_symbol))
    second[2].metric("成交量", compact_cn(daily.get("volume"), "股"))
    second[3].metric("成交额", compact_cn(daily.get("amount"), "元"))
