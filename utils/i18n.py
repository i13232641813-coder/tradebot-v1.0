"""Small session-scoped internationalization helpers for Streamlit pages."""

from __future__ import annotations

import streamlit as st

LANGUAGE_OPTIONS = {"简体中文": "zh-CN", "English": "en"}


def current_language() -> str:
    """Return the active language, defaulting to Simplified Chinese."""
    return st.session_state.get("tradebot_language", "zh-CN")


def tr(chinese: str, english: str) -> str:
    """Select one of two explicit translations."""
    return english if current_language() == "en" else chinese


STATUS_TRANSLATIONS = {
    "趋势": "Trend", "强势多头": "Strong bullish", "弱势空头": "Strong bearish",
    "震荡或趋势不明确": "Sideways / unclear trend", "多头": "Bullish", "空头": "Bearish",
    "方向不明确": "Unclear direction", "数据不足": "Insufficient data", "偏热": "Overheated",
    "偏弱或超卖": "Weak / oversold", "中性": "Neutral", "成交量": "Volume",
    "明显放量": "High volume", "明显缩量": "Low volume", "成交量正常": "Normal volume",
    "位于上轨之外": "Above upper band", "位于下轨之外": "Below lower band",
    "位于区间内": "Inside bands", "波动率": "Volatility", "较高": "High",
    "较低": "Low", "中等": "Medium", "客观数值": "Current values",
    "收盘价 > MA5 > MA10 > MA20": "Close > MA5 > MA10 > MA20",
    "收盘价 < MA5 < MA10 < MA20": "Close < MA5 < MA10 < MA20",
    "均线排列未满足固定多头或空头条件": "Moving averages do not match the fixed bullish or bearish rules",
    "DIF 位于 DEA 上方，柱体为正": "DIF is above DEA and the histogram is positive",
    "DIF 位于 DEA 下方，柱体为负": "DIF is below DEA and the histogram is negative",
    "当前未满足固定多头或空头条件": "The fixed bullish or bearish conditions are not met",
    "至少需要 15 个有效交易日": "At least 15 valid sessions are required",
    "至少需要 20 个有效交易日": "At least 20 valid sessions are required",
    "至少需要 21 个有效交易日": "At least 21 valid sessions are required",
    "收盘价高于布林带上轨": "Close is above the upper Bollinger Band",
    "收盘价低于布林带下轨": "Close is below the lower Bollinger Band",
    "收盘价位于布林带上下轨之间": "Close is between the Bollinger Bands",
}


def status_text(value: str) -> str:
    """Translate deterministic indicator status text, including numeric prefixes."""
    if current_language() != "en":
        return value
    if value in STATUS_TRANSLATIONS:
        return STATUS_TRANSLATIONS[value]
    replacements = {
        "当前值：": "Current value: ",
        "当前成交量为 20 日均量的 ": "Current volume is ",
        " 倍": "x the 20-session average",
        "20 日年化历史波动率：": "20-session annualized historical volatility: ",
    }
    result = value
    for source, target in replacements.items():
        result = result.replace(source, target)
    return result


def interval_labels() -> list[str]:
    return ["Daily", "Weekly", "Monthly"] if current_language() == "en" else ["日K", "周K", "月K"]


def interval_code(label: str) -> str:
    return {"Daily": "日K", "Weekly": "周K", "Monthly": "月K"}.get(label, label)


def language_selector() -> None:
    """Render the same global language setting on every independent page."""
    current = current_language()
    labels = list(LANGUAGE_OPTIONS)
    default_label = next(label for label, code in LANGUAGE_OPTIONS.items() if code == current)
    st.session_state.setdefault("tradebot_language_label", default_label)

    def sync_language() -> None:
        st.session_state["tradebot_language"] = LANGUAGE_OPTIONS[st.session_state["tradebot_language_label"]]

    st.selectbox(
        tr("语言 / Language", "Language / 语言"), labels,
        key="tradebot_language_label", on_change=sync_language,
    )
    sync_language()
