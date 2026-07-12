"""Global language setting tests."""

from streamlit.testing.v1 import AppTest
from utils.i18n import interval_code


def test_language_selector_switches_and_persists() -> None:
    app = AppTest.from_file("app.py").run(timeout=20)
    assert not app.exception
    app.selectbox[0].select("English").run(timeout=20)
    assert not app.exception
    assert any("A-share / US stock analysis" in item.value for item in app.caption)
    app.run(timeout=20)
    assert app.selectbox[0].value == "English"


def test_english_stock_summary_and_indicator_status() -> None:
    source = '''
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from components.stock_summary import render_stock_summary
from components.indicator_cards import render_status_cards
from services.indicators import IndicatorStatus
from services.market_data import LatestQuote, StockHistory
st.session_state["tradebot_language"] = "en"
prices = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-02"]), "open":[10,11], "high":[12,13], "low":[9,10], "close":[11,12], "volume":[1000,2000], "amount":[10000,24000]})
stock = StockHistory("000001", "Test", prices)
quote = LatestQuote("000001", 12.5, datetime(2026,1,2,7,0,tzinfo=timezone.utc), 11, 13, 10, 2000)
render_stock_summary(stock, quote)
render_status_cards([IndicatorStatus("趋势", "强势多头", "收盘价 > MA5 > MA10 > MA20")])
'''
    app = AppTest.from_string(source).run(timeout=20)
    assert not app.exception
    labels = [item.label for item in app.metric]
    assert "Latest Price" in labels
    assert "Intraday Volume" in labels
    assert any("Trend" in item.value and "Strong bullish" in item.value for item in app.markdown)


def test_english_interval_maps_to_internal_code() -> None:
    assert interval_code("Daily") == "日K"
    assert interval_code("Weekly") == "周K"
    assert interval_code("Monthly") == "月K"
