"""
scanner/universe.py
Fetches and caches stock universes from Wikipedia index pages.
No API keys required — uses pd.read_html on public index constituent tables.

Supported markets:
  us  — S&P 500 (fallback: Nasdaq-100)
  eu  — FTSE 100, DAX 40, CAC 40, AEX, IBEX 35, FTSE MIB, OMX 30
  all — US + EU combined
"""

import time
import logging
import requests
import pandas as pd
from io import StringIO
from scanner.config import UNIVERSE_CACHE_TTL

logger = logging.getLogger(__name__)

# In-memory cache: { market_key: (timestamp, {symbol: name}) }
_cache: dict[str, tuple[float, dict]] = {}

# Wikipedia blocks requests without a browser User-Agent
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


def _read_html(url: str) -> list:
    """Fetch a URL with a browser User-Agent and parse all tables."""
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


# ── Internal helpers ─────────────────────────────────────────────────────────

def _scrape_wiki_table(url: str, suffix: str) -> dict[str, str]:
    """
    Generic Wikipedia index table scraper.
    Looks for columns named ticker/symbol and company/name,
    appends `suffix` (e.g. '.DE') to form valid yfinance symbols.
    Returns {symbol: company_name}.
    """
    try:
        tables = _read_html(url)
    except Exception as e:
        logger.warning(f"read_html failed for {url}: {e}")
        return {}

    for df in tables:
        ticker_col = _find_col(df, ("ticker", "tidm", "symbol", "abbrev", "epic"))
        name_col   = _find_col(df, ("company", "name", "security", "component", "constituen"))

        if ticker_col is None or name_col is None:
            continue

        result = {}
        for _, row in df.iterrows():
            raw  = str(row[ticker_col]).strip()
            name = str(row[name_col]).strip()

            if not raw or raw.lower() in ("nan", "—", "-", ""):
                continue

            sym  = raw.replace(".", "-").upper()
            full = sym + suffix if not sym.endswith(suffix.lstrip(".")) else sym

            if name and name.lower() != "nan":
                result[full] = name

        if len(result) > 5:
            return result

    return {}


def _find_col(df: pd.DataFrame, keywords: tuple) -> str | None:
    """Return the first column name whose lowercase version contains any keyword."""
    for col in df.columns:
        if any(k in str(col).lower() for k in keywords):
            return col
    return None


# ── Public fetchers ──────────────────────────────────────────────────────────

def fetch_sp500() -> dict[str, str]:
    """S&P 500 constituents from Wikipedia. Returns {symbol: name}."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        tables = _read_html(url)
        df = tables[0]
        result = {
            str(row["Symbol"]).strip().replace(".", "-"): str(row["Security"]).strip()
            for _, row in df.iterrows()
        }
        logger.info(f"S&P 500: {len(result)} tickers")
        return result
    except Exception as e:
        logger.error(f"S&P 500 fetch failed: {e}")
        return {}


def fetch_nasdaq100() -> dict[str, str]:
    """Nasdaq-100 from Wikipedia — used as US fallback."""
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    try:
        tables = _read_html(url)
        for df in tables:
            ticker_col = _find_col(df, ("ticker", "symbol"))
            name_col   = _find_col(df, ("company", "name", "security"))
            if ticker_col is None or name_col is None:
                continue
            result = {
                str(row[ticker_col]).strip().replace(".", "-"): str(row[name_col]).strip()
                for _, row in df.iterrows()
                if str(row[ticker_col]).strip().lower() not in ("nan", "")
            }
            if len(result) > 50:
                logger.info(f"Nasdaq-100: {len(result)} tickers")
                return result
    except Exception as e:
        logger.error(f"Nasdaq-100 fetch failed: {e}")
    return {}


EU_INDICES = [
    ("https://en.wikipedia.org/wiki/FTSE_100_Index", ".L"),
    ("https://en.wikipedia.org/wiki/DAX",            ".DE"),
    ("https://en.wikipedia.org/wiki/CAC_40",         ".PA"),
    ("https://en.wikipedia.org/wiki/AEX_index",      ".AS"),
    ("https://en.wikipedia.org/wiki/IBEX_35",        ".MC"),
    ("https://en.wikipedia.org/wiki/FTSE_MIB",       ".MI"),
    ("https://en.wikipedia.org/wiki/OMX_Stockholm_30", ".ST"),
]


def fetch_eu() -> dict[str, str]:
    """Scrape all EU index pages. Returns combined {symbol: name}."""
    all_stocks: dict[str, str] = {}
    for url, suffix in EU_INDICES:
        batch = _scrape_wiki_table(url, suffix)
        logger.info(f"EU [{suffix}]: {len(batch)} tickers from {url.split('/')[-1]}")
        all_stocks.update(batch)
    logger.info(f"EU total: {len(all_stocks)} tickers")
    return all_stocks


# ── Cache-aware public API ───────────────────────────────────────────────────

def get_universe(market: str) -> dict[str, str]:
    """
    Return {symbol: name} for the given market.
    Results are cached for UNIVERSE_CACHE_TTL seconds.

    Args:
        market: 'us' | 'eu' | 'all'
    """
    now = time.time()
    cached = _cache.get(market)
    if cached and (now - cached[0]) < UNIVERSE_CACHE_TTL:
        logger.debug(f"Universe cache hit: market={market} ({len(cached[1])} tickers)")
        return cached[1]

    logger.info(f"Refreshing universe: market={market}")

    if market == "us":
        universe = fetch_sp500()
        if len(universe) < 50:
            logger.warning("S&P 500 returned < 50 tickers, falling back to Nasdaq-100")
            universe.update(fetch_nasdaq100())

    elif market == "eu":
        universe = fetch_eu()

    else:  # "all"
        us = fetch_sp500()
        if len(us) < 50:
            us.update(fetch_nasdaq100())
        universe = {**us, **fetch_eu()}

    _cache[market] = (now, universe)
    return universe


def cache_status() -> dict:
    """Return current cache state — useful for /api/health endpoint."""
    return {
        market: {
            "count":      len(data),
            "age_seconds": round(time.time() - ts),
            "stale":      (time.time() - ts) > UNIVERSE_CACHE_TTL,
        }
        for market, (ts, data) in _cache.items()
    }