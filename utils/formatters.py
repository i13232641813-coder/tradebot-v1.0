"""Consistent display formatting."""

from numbers import Number
import pandas as pd


def price(value: object) -> str:
    return "-" if pd.isna(value) else f"{float(value):.2f}"


def percent(value: object) -> str:
    return "-" if pd.isna(value) else f"{float(value):.2f}%"


def compact_cn(value: object, unit: str = "") -> str:
    if pd.isna(value) or not isinstance(value, Number):
        return "-"
    number = float(value)
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:.2f}亿{unit}"
    if abs(number) >= 10_000:
        return f"{number / 10_000:.2f}万{unit}"
    return f"{number:,.0f}{unit}"


def currency_compact(value: object, symbol: str = "¥") -> str:
    """Format large currency values compactly so metric cards never truncate."""
    if pd.isna(value) or not isinstance(value, Number):
        return "-"
    number = float(value)
    absolute = abs(number)
    if absolute >= 100_000_000:
        return f"{symbol}{number / 100_000_000:.2f}亿"
    if absolute >= 10_000:
        return f"{symbol}{number / 10_000:.2f}万"
    return f"{symbol}{number:,.2f}"


def currency_full(value: object, symbol: str = "¥") -> str:
    """Return the non-abbreviated amount for tooltips and detailed tables."""
    return "-" if pd.isna(value) else f"{symbol}{float(value):,.2f}"
