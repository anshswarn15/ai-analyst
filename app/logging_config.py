"""Structured-ish logging: one line per event, key=value pairs, easy to grep or ship to a log stack."""
from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_datapilot_configured", False):
        root.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"))
    root.handlers = [handler]
    root.setLevel(level)
    root._datapilot_configured = True  # type: ignore[attr-defined]
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
