"""
scanner/filters.py
Signal detection and filter application.

Signals:
  PRICE_MOVE  — 1-day % change exceeds threshold
  VOL_SPIKE   — today's volume is X× the rolling average
  MOMENTUM    — 5-day cumulative move exceeds 1.5× the price threshold

Modes (defined in config.py):
  relaxed — any single signal qualifies
  strict  — PRICE_MOVE AND VOL_SPIKE both required
"""

import logging
from scanner.config import FILTER_CONFIG

logger = logging.getLogger(__name__)

SIGNAL_PRICE_MOVE = "PRICE_MOVE"
SIGNAL_VOL_SPIKE  = "VOL_SPIKE"
SIGNAL_MOMENTUM   = "MOMENTUM"


def detect_signals(stock: dict, mode: str) -> list[str]:
    """
    Evaluate which signals are present for a stock.

    Args:
        stock: output dict from fetcher.fetch_ticker()
        mode:  'strict' | 'relaxed'

    Returns:
        List of signal strings (may be empty).
    """
    cfg     = FILTER_CONFIG[mode]
    signals = []

    if abs(stock["price_change_pct"]) >= cfg["min_price_change"]:
        signals.append(SIGNAL_PRICE_MOVE)

    if stock["volume_ratio"] >= cfg["min_volume_ratio"]:
        signals.append(SIGNAL_VOL_SPIKE)

    if abs(stock["five_day_change"]) >= cfg["min_price_change"] * 1.5:
        signals.append(SIGNAL_MOMENTUM)

    return signals


def passes_filter(stock: dict, mode: str, direction: str = "both") -> tuple[bool, list[str]]:
    """
    Determine whether a stock passes price range, signal, and direction filters.

    Args:
        stock:     output dict from fetcher.fetch_ticker()
        mode:      'strict' | 'relaxed'
        direction: 'up' | 'down' | 'both'

    Returns:
        (passes: bool, signals: list[str])
    """
    cfg = FILTER_CONFIG[mode]

    # Price range gate
    if not (cfg["min_price"] <= stock["price"] <= cfg["max_price"]):
        return False, []

    signals = detect_signals(stock, mode)

    # Signal gate
    if cfg["require_both_signals"]:
        ok = SIGNAL_PRICE_MOVE in signals and SIGNAL_VOL_SPIKE in signals
    else:
        ok = len(signals) >= 1

    if not ok:
        return False, signals

    # Direction gate
    if direction == "up"   and stock["direction"] != "UP":
        return False, signals
    if direction == "down" and stock["direction"] != "DOWN":
        return False, signals

    return True, signals