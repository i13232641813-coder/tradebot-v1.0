"""Input validation helpers."""

import re


def validate_stock_code(value: str) -> str:
    """Return a normalized six-digit A-share code or raise ValueError."""
    code = value.strip()
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("股票代码必须是六位数字")
    return code


def validate_security_symbol(value: str) -> str:
    """Validate an A-share code or a US Yahoo ticker and normalize case."""
    symbol = value.strip().upper()
    if re.fullmatch(r"\d{6}", symbol):
        if symbol.startswith(("0", "1", "2", "3", "4", "5", "6", "8", "9")):
            return symbol
        raise ValueError("暂不支持该六位代码对应的 A 股交易所")
    if re.fullmatch(r"[A-Z][A-Z0-9-]{0,14}", symbol):
        return symbol
    raise ValueError("请输入六位 A 股代码或有效美股代码，例如 000938、AAPL、BRK-B")
