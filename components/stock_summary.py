"""Stock overview cards."""

import pandas as pd
import streamlit as st

from services.market_data import LatestQuote, StockHistory
from utils.formatters import compact_cn, percent, price
from utils.i18n import current_language, tr


def _currency(code: str) -> tuple[str, str]:
    """Return the display symbol and ISO currency for the selected market."""
    return ("¥", "CNY") if code.isdigit() else ("$", "USD")


def _market_price(value: object, symbol: str) -> str:
    formatted = price(value)
    return formatted if formatted == "-" else f"{symbol}{formatted}"


def _volume(value: object) -> str:
    if current_language() != "en":
        return compact_cn(value, "股")
    if pd.isna(value):
        return "-"
    number = float(value)
    if abs(number) >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B shares"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.2f}M shares"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.2f}K shares"
    return f"{number:,.0f} shares"


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
            f"{tr('最新分钟行情（可能延迟）','Latest minute quote (may be delayed)')}｜"
            f"{tr('时间','Time')}: {quote.timestamp:%Y-%m-%d %H:%M %Z}｜"
            f"{tr('币种','Currency')}: {currency_code}｜{tr('数据源','Source')}: Yahoo Finance 1m｜"
            f"{tr('日线指标截止','Daily indicators through')}: {daily['date']:%Y-%m-%d}"
        )
        first = st.columns(5)
        values = [quote.price, change, change_pct, quote.open, previous_close]
        labels = [tr("最新分钟价","Latest Price"), tr("涨跌额","Change"), tr("涨跌幅","Change %"), tr("今开","Open"), tr("前收盘","Prev Close")]
        for column, label, value in zip(first, labels, values):
            column.metric(label, percent(value) if label == tr("涨跌幅","Change %") else _market_price(value, currency_symbol))
        second = st.columns(4)
        second[0].metric(tr("今日最高","Day High"), _market_price(quote.high, currency_symbol))
        second[1].metric(tr("今日最低","Day Low"), _market_price(quote.low, currency_symbol))
        second[2].metric(tr("今日分钟成交量合计","Intraday Volume"), _volume(quote.volume))
        second[3].metric(tr("成交额","Turnover"), "-")
        return

    previous = stock.prices.iloc[-2]["close"] if len(stock.prices) > 1 else pd.NA
    change = daily.get("change", daily["close"] - previous if not pd.isna(previous) else pd.NA)
    change_pct = daily.get("change_pct", change / previous * 100 if not pd.isna(previous) else pd.NA)
    st.subheader(f"{stock.name} · {stock.code}")
    st.caption(f"{tr('前复权日线','Adjusted daily data')}｜{tr('数据日期','Data date')}: {daily['date']:%Y-%m-%d}｜{tr('币种','Currency')}: {currency_code}｜{tr('最近收盘（分钟行情不可用）','Latest close (minute quote unavailable)')}")
    first = st.columns(5)
    for column, label, value in zip(first, [tr("最近收盘","Latest Close"),tr("涨跌额","Change"),tr("涨跌幅","Change %"),tr("今开","Open"),tr("昨收","Prev Close")], [daily["close"], change, change_pct, daily["open"], previous]):
        column.metric(label, percent(value) if label == tr("涨跌幅","Change %") else _market_price(value, currency_symbol))
    second = st.columns(4)
    second[0].metric(tr("最高","High"), _market_price(daily["high"], currency_symbol))
    second[1].metric(tr("最低","Low"), _market_price(daily["low"], currency_symbol))
    second[2].metric(tr("成交量","Volume"), _volume(daily.get("volume")))
    second[3].metric(tr("成交额","Turnover"), compact_cn(daily.get("amount"), tr("元"," CNY")))
