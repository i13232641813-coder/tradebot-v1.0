"""Technical indicators and deterministic, explainable status rules."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IndicatorStatus:
    """A neutral description derived from the latest indicator values."""

    title: str
    state: str
    detail: str


def calculate_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with all supported fixed technical indicators appended."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"缺少指标计算字段：{', '.join(sorted(missing))}")

    data = frame.copy()
    close = pd.to_numeric(data["close"], errors="coerce")
    high = pd.to_numeric(data["high"], errors="coerce")
    low = pd.to_numeric(data["low"], errors="coerce")
    volume = pd.to_numeric(data["volume"], errors="coerce")

    for window in (5, 10, 20, 60):
        data[f"ma{window}"] = close.rolling(window, min_periods=window).mean()
    for window in (5, 10, 20):
        data[f"vol_ma{window}"] = volume.rolling(window, min_periods=window).mean()

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    data["dif"] = ema12 - ema26
    data["dea"] = data["dif"].ewm(span=9, adjust=False, min_periods=9).mean()
    data["macd_hist"] = 2 * (data["dif"] - data["dea"])

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss
    data["rsi14"] = 100 - (100 / (1 + rs))
    data.loc[(avg_loss == 0) & (avg_gain > 0), "rsi14"] = 100.0
    data.loc[(avg_loss == 0) & (avg_gain == 0), "rsi14"] = 50.0

    low9 = low.rolling(9, min_periods=9).min()
    high9 = high.rolling(9, min_periods=9).max()
    spread = (high9 - low9).replace(0, np.nan)
    data["rsv"] = (close - low9) / spread * 100
    data["k"] = data["rsv"].ewm(alpha=1 / 3, adjust=False, min_periods=1).mean()
    data["d"] = data["k"].ewm(alpha=1 / 3, adjust=False, min_periods=1).mean()
    data["j"] = 3 * data["k"] - 2 * data["d"]

    data["boll_mid"] = close.rolling(20, min_periods=20).mean()
    std20 = close.rolling(20, min_periods=20).std(ddof=0)
    data["boll_upper"] = data["boll_mid"] + 2 * std20
    data["boll_lower"] = data["boll_mid"] - 2 * std20

    log_return = np.log(close / close.shift(1))
    data["volatility20"] = log_return.rolling(20, min_periods=20).std(ddof=1) * math.sqrt(252)
    return data


def latest_statuses(data: pd.DataFrame) -> dict[str, IndicatorStatus]:
    """Apply fixed rules to the latest row without issuing trading advice."""
    if data.empty:
        return {}
    row = data.iloc[-1]

    if _all_finite(row, "close", "ma5", "ma10", "ma20") and row["close"] > row["ma5"] > row["ma10"] > row["ma20"]:
        trend = IndicatorStatus("趋势", "强势多头", "收盘价 > MA5 > MA10 > MA20")
    elif _all_finite(row, "close", "ma5", "ma10", "ma20") and row["close"] < row["ma5"] < row["ma10"] < row["ma20"]:
        trend = IndicatorStatus("趋势", "弱势空头", "收盘价 < MA5 < MA10 < MA20")
    else:
        trend = IndicatorStatus("趋势", "震荡或趋势不明确", "均线排列未满足固定多头或空头条件")

    if _all_finite(row, "dif", "dea", "macd_hist") and row["dif"] > row["dea"] and row["macd_hist"] > 0:
        macd = IndicatorStatus("MACD", "多头", "DIF 位于 DEA 上方，柱体为正")
    elif _all_finite(row, "dif", "dea", "macd_hist") and row["dif"] < row["dea"] and row["macd_hist"] < 0:
        macd = IndicatorStatus("MACD", "空头", "DIF 位于 DEA 下方，柱体为负")
    else:
        macd = IndicatorStatus("MACD", "方向不明确", "当前未满足固定多头或空头条件")

    rsi_value = row.get("rsi14")
    if pd.isna(rsi_value):
        rsi = IndicatorStatus("RSI", "数据不足", "至少需要 15 个有效交易日")
    elif rsi_value >= 70:
        rsi = IndicatorStatus("RSI", "偏热", f"当前值：{rsi_value:.2f}")
    elif rsi_value <= 30:
        rsi = IndicatorStatus("RSI", "偏弱或超卖", f"当前值：{rsi_value:.2f}")
    else:
        rsi = IndicatorStatus("RSI", "中性", f"当前值：{rsi_value:.2f}")

    ratio = row["volume"] / row["vol_ma20"] if pd.notna(row.get("vol_ma20")) and row["vol_ma20"] else np.nan
    if pd.isna(ratio):
        volume = IndicatorStatus("成交量", "数据不足", "至少需要 20 个有效交易日")
    elif ratio >= 1.5:
        volume = IndicatorStatus("成交量", "明显放量", f"当前成交量为 20 日均量的 {ratio:.2f} 倍")
    elif ratio <= 0.7:
        volume = IndicatorStatus("成交量", "明显缩量", f"当前成交量为 20 日均量的 {ratio:.2f} 倍")
    else:
        volume = IndicatorStatus("成交量", "成交量正常", f"当前成交量为 20 日均量的 {ratio:.2f} 倍")

    if not _all_finite(row, "close", "boll_upper", "boll_lower"):
        boll = IndicatorStatus("BOLL", "数据不足", "至少需要 20 个有效交易日")
    elif row["close"] > row["boll_upper"]:
        boll = IndicatorStatus("BOLL", "位于上轨之外", "收盘价高于布林带上轨")
    elif row["close"] < row["boll_lower"]:
        boll = IndicatorStatus("BOLL", "位于下轨之外", "收盘价低于布林带下轨")
    else:
        boll = IndicatorStatus("BOLL", "位于区间内", "收盘价位于布林带上下轨之间")

    volatility_value = row.get("volatility20")
    if pd.isna(volatility_value):
        volatility = IndicatorStatus("波动率", "数据不足", "至少需要 21 个有效交易日")
    else:
        level = "较高" if volatility_value >= 0.4 else "较低" if volatility_value <= 0.15 else "中等"
        volatility = IndicatorStatus("波动率", level, f"20 日年化历史波动率：{volatility_value:.2%}")
    return {"trend": trend, "macd": macd, "rsi": rsi, "volume": volume, "boll": boll, "volatility": volatility}


def _all_finite(row: pd.Series, *columns: str) -> bool:
    return all(column in row and pd.notna(row[column]) and np.isfinite(row[column]) for column in columns)
