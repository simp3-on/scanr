"""
app.py — Flask entry point.

  scanner/config.py   — constants and filter thresholds
  scanner/universe.py — Wikipedia index scraping + cache
  scanner/fetcher.py  — yfinance OHLCV download per ticker
  scanner/filters.py  — signal detection and filter logic

Run:
  python app.py
"""

import json
import logging
import queue
import threading
from datetime import datetime
import concurrent.futures

from flask import Flask, jsonify, request, Response, stream_with_context, send_from_directory
from flask_cors import CORS

from scanner.config   import FILTER_CONFIG, MAX_FETCH_WORKERS
from scanner.universe import get_universe, cache_status
from scanner.fetcher  import fetch_ticker
from scanner.filters  import passes_filter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static")
CORS(app)


# ── SSE helpers ───────────────────────────────────────────────────────────────

def sse_event(data: dict) -> str:
    """Format a dict as a Server-Sent Event string."""
    return f"data: {json.dumps(data)}\n\n"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/scan")
def scan():
    """
    Streams scan progress as Server-Sent Events, then sends final results.

    Event types:
      {"type": "universe",  "total": 503}
      {"type": "progress",  "done": 42, "total": 503, "elapsed": 3.1}
      {"type": "result",    "results": [...], "count": 18, ...}
      {"type": "error",     "message": "..."}
    """
    mode      = request.args.get("mode",      "relaxed").lower()
    market    = request.args.get("market",    "us").lower()
    direction = request.args.get("direction", "both").lower()

    if mode not in FILTER_CONFIG:
        def err():
            yield sse_event({"type": "error", "message": "Invalid mode."})
        return Response(stream_with_context(err()), mimetype="text/event-stream")

    if market not in ("us", "eu", "all"):
        def err():
            yield sse_event({"type": "error", "message": "Invalid market."})
        return Response(stream_with_context(err()), mimetype="text/event-stream")

    def generate():
        universe = get_universe(market)
        if not universe:
            yield sse_event({"type": "error", "message": "Failed to load stock universe."})
            return

        total = len(universe)
        yield sse_event({"type": "universe", "total": total})

        results   = []
        done      = 0
        start     = datetime.utcnow().timestamp()
        q         = queue.Queue()

        # Worker: fetch + filter, push result to queue
        def worker(sym, name):
            stock = fetch_ticker(sym, name)
            q.put(stock)

        # Submit all fetches
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS)
        for sym, name in universe.items():
            executor.submit(worker, sym, name)
        executor.shutdown(wait=False)

        # Stream progress as results come in
        while done < total:
            try:
                stock = q.get(timeout=60)
            except queue.Empty:
                break

            done += 1

            if stock:
                ok, signals = passes_filter(stock, mode, direction)
                if ok:
                    stock["signals"]     = signals
                    stock["filter_mode"] = mode
                    results.append(stock)

            elapsed   = round(datetime.utcnow().timestamp() - start, 1)
            remaining = total - done
            # Estimate seconds remaining based on current rate
            rate      = done / elapsed if elapsed > 0 else 1
            eta       = round(remaining / rate) if rate > 0 else 0

            # Send progress every tick
            yield sse_event({
                "type":    "progress",
                "done":    done,
                "total":   total,
                "elapsed": elapsed,
                "eta":     eta,
            })

        results.sort(key=lambda x: abs(x["price_change_pct"]), reverse=True)

        yield sse_event({
            "type":      "result",
            "results":   results,
            "count":     len(results),
            "mode":      mode,
            "market":    market,
            "scanned":   total,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":  "no-cache",
            "X-Accel-Buffering": "no",   # disables nginx buffering if behind proxy
        }
    )


@app.route("/api/market-hours")
def market_hours():
    """
    Returns open/closed status for US and EU markets based on UTC time.
    Does not account for public holidays — just regular trading hours + weekends.

    US  — NYSE/NASDAQ: 13:30–20:00 UTC (09:30–16:00 ET, no DST adjustment here)
    EU  — covers approximate overlap of LSE/Xetra/Euronext: 08:00–16:30 UTC
    """
    now       = datetime.utcnow()
    weekday   = now.weekday()   # 0=Mon, 6=Sun
    h, m      = now.hour, now.minute
    time_mins = h * 60 + m     # minutes since midnight UTC

    def market_status(open_utc, close_utc, pre_mins=30):
        """
        open_utc / close_utc: (hour, minute) tuples in UTC.
        Returns: "open" | "pre" | "post" | "closed" | "weekend"
        """
        if weekday >= 5:
            return "weekend"
        open_mins  = open_utc[0]  * 60 + open_utc[1]
        close_mins = close_utc[0] * 60 + close_utc[1]
        if open_mins <= time_mins < close_mins:
            return "open"
        if open_mins - pre_mins <= time_mins < open_mins:
            return "pre"
        if close_mins <= time_mins < close_mins + pre_mins:
            return "post"
        return "closed"

    us_status = market_status((13, 30), (20, 0))
    eu_status = market_status((7,  0),  (16, 30))

    def label(status):
        return {
            "open":    "Open",
            "pre":     "Pre-Market",
            "post":    "After-Hours",
            "closed":  "Closed",
            "weekend": "Weekend — Closed",
        }[status]

    return jsonify({
        "utc_time": now.strftime("%H:%M UTC"),
        "weekday":  now.strftime("%A"),
        "us": {"status": us_status, "label": label(us_status), "hours": "09:30–16:00 ET"},
        "eu": {"status": eu_status, "label": label(eu_status), "hours": "08:00–16:30 UTC"},
    })


@app.route("/api/universe")
def universe_info():
    market   = request.args.get("market", "us").lower()
    universe = get_universe(market)
    return jsonify({
        "market": market,
        "count":  len(universe),
        "sample": dict(list(universe.items())[:10]),
    })


@app.route("/api/health")
def health():
    return jsonify({
        "status":         "ok",
        "universe_cache": cache_status(),
        "timestamp":      datetime.utcnow().isoformat() + "Z",
    })


@app.route("/")
def index():
    return send_from_directory(".", "index.html")



if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)