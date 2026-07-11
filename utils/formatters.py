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
