"""Application-wide rotating file logging."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> None:
    """Configure logging once per Python process, with a safe console fallback."""
    root = logging.getLogger()
    if getattr(root, "_tradebot_configured", False):
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        log_path = Path(__file__).resolve().parent.parent / "tradebot.log"
        handler: logging.Handler = RotatingFileHandler(
            log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
    except OSError:
        handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root._tradebot_configured = True  # type: ignore[attr-defined]
