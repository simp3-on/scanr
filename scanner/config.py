"""
scanner/config.py
All tunable constants in one place.
"""

FILTER_CONFIG = {
    "strict": {
        "min_price_change":    3.0,   # % 1-day move required
        "min_volume_ratio":    2.0,   # today's vol / avg vol
        "min_price":           5.0,   # USD / local currency floor
        "max_price":        5000.0,
        "require_both_signals": True, # PRICE_MOVE AND VOL_SPIKE
    },
    "relaxed": {
        "min_price_change":    1.5,
        "min_volume_ratio":    1.3,
        "min_price":           1.0,
        "max_price":        5000.0,
        "require_both_signals": False, # any single signal qualifies
    },
}

# How long to cache the scraped universe (seconds)
UNIVERSE_CACHE_TTL = 3600

# Threading
MAX_FETCH_WORKERS = 25

# How many days of history to pull per ticker
HISTORY_DAYS = "15d"