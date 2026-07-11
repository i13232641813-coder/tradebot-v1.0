"""Cross-market symbol validation tests."""

import pytest

from utils.validators import validate_security_symbol


@pytest.mark.parametrize(("value", "expected"), [
    ("000938", "000938"),
    (" aapl ", "AAPL"),
    ("brk-b", "BRK-B"),
])
def test_validate_security_symbol(value: str, expected: str) -> None:
    assert validate_security_symbol(value) == expected


@pytest.mark.parametrize("value", ["", "12345", "AAPL$", "700000"])
def test_validate_security_symbol_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        validate_security_symbol(value)
