"""
scanner/fetcher.py
Downloads OHLCV history for a single ticker via yfinance
and returns a clean, flat dict ready for filtering.

Each function is intentionally small so failures are easy to trace.
"""

import logging
import yfinance as yf
from scanner.config import HISTORY_DAYS

logger = logging.getLogger(__name__)


def _price_change(current: float, previous: float) -> float:
    """Percentage change between two prices, rounded to 2dp."""
    if previous == 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)


def _resolve_name(symbol: str, scraped_name: str, ticker: yf.Ticker) -> str:
    """
    Use scraped name if it looks valid.
    Fall back to yfinance info (one extra network call) only when necessary.
    """
    if scraped_name and scraped_name.lower() not in ("nan", "", symbol.lower()):
        return scraped_name
    try:
        info = ticker.info
        return info.get("longName") or info.get("shortName") or symbol
    except Exception:
        return symbol


def fetch_ticker(symbol: str, scraped_name: str) -> dict | None:
    """
    Fetch OHLCV history for `symbol` and compute:
      - current price + 1-day % change
      - volume ratio vs 9-day average
      - 5-day momentum %
      - direction (UP / DOWN)

    Returns None if data is unavailable or insufficient.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period=HISTORY_DAYS, interval="1d")

        if hist.empty or len(hist) < 2:
            logger.debug(f"{symbol}: insufficient history ({len(hist)} rows)")
            return None

        hist = hist.dropna(subset=["Close", "Volume"])
        if len(hist) < 2:
            return None

        latest = hist.iloc[-1]
        prev   = hist.iloc[-2]

        current_price = round(float(latest["Close"]), 2)
        prev_price    = round(float(prev["Close"]),   2)

        current_vol = int(latest["Volume"])
        avg_vol     = int(hist["Volume"].iloc[:-1].mean())  # exclude today from avg
        vol_ratio   = round(current_vol / avg_vol, 2) if avg_vol > 0 else 0.0

        one_day_chg  = _price_change(current_price, prev_price)
        five_day_chg = (
            _price_change(current_price, float(hist.iloc[-5]["Close"]))
            if len(hist) >= 5
            else one_day_chg
        )

        name = _resolve_name(symbol, scraped_name, ticker)

        return {
            "symbol":           symbol,
            "name":             name,
            "price":            current_price,
            "price_change_pct": one_day_chg,
            "five_day_change":  five_day_chg,
            "volume":           current_vol,
            "avg_volume":       avg_vol,
            "volume_ratio":     vol_ratio,
            "direction":        "UP" if one_day_chg > 0 else "DOWN",
        }

    except Exception as e:
        logger.warning(f"{symbol}: fetch error — {e}")
        return None