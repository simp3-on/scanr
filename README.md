# SCANR

A real-time stock market scanner built with Flask. Scans thousands of tickers across US and European markets for technical signals, streaming live progress to the frontend via Server-Sent Events.

---

## What it does

SCANR pulls live market data from the Polygon.io API and runs each ticker through a configurable set of technical filters. Results are streamed back to the browser in real time as they're computed — no waiting for a full scan to finish before you see anything.

**Supported markets:**
- 🇺🇸 US — NYSE + NASDAQ (~8,000 tickers)
- 🇪🇺 EU — FTSE, DAX, CAC 40, AEX, IBEX 35, FTSE MIB, OMX 30

**Signal columns (16 total):**

| # | Column | Description |
|---|--------|-------------|
| 1 | Ticker | Symbol with Finviz link |
| 2 | Name | Company name |
| 3 | Price | Current price |
| 4 | Change % | Daily price change |
| 5 | Volume | Current session volume |
| 6 | Avg Volume | 30-day average volume |
| 7 | Vol Ratio | Current vs average volume |
| 8 | Market Cap | Market capitalisation |
| 9–15 | Intraday signals | RSI, MACD, Bollinger Bands, etc. *(requires Polygon paid tier)* |
| 16 | Signals | Summary of triggered conditions |

---

## Tech stack

- **Backend:** Python, Flask
- **Data:** Polygon.io REST API
- **Streaming:** Server-Sent Events (SSE)
- **Concurrency:** `concurrent.futures.ThreadPoolExecutor`
- **Frontend:** Vanilla JS, HTML/CSS
- **Deployment:** Render (via GitHub)

---

## Project structure

```
scanr/
├── app.py              # Flask entry point, SSE route, API endpoints
├── scanner/
│   ├── config.py       # Filter thresholds and constants
│   ├── universe.py     # Market index scraping and ticker cache
│   ├── fetcher.py      # Per-ticker data fetch via Polygon.io
│   └── filters.py      # Signal detection and filter logic
├── static/             # Frontend assets (CSS, JS)
├── index.html          # UI
├── requirements.txt
└── Procfile            # Render deployment config
```

---

## API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/scan?mode=&market=&direction=` | Stream scan results as SSE |
| `GET /api/market-hours` | US and EU market open/closed status |
| `GET /api/universe?market=` | Ticker universe info and sample |
| `GET /api/health` | Health check + cache status |

**Scan parameters:**

- `mode` — `relaxed` or `strict` (filter sensitivity)
- `market` — `us`, `eu`, or `all`
- `direction` — `long`, `short`, or `both`

**SSE event types streamed during a scan:**

```json
{ "type": "universe", "total": 8000 }
{ "type": "progress", "done": 420, "total": 8000, "elapsed": 3.1, "eta": 55 }
{ "type": "result", "results": [...], "count": 34, "scanned": 8000 }
{ "type": "error", "message": "..." }
```

---

## Running locally

**Requirements:** Python 3.10+, a [Polygon.io](https://polygon.io) API key

```bash
git clone https://github.com/simp3-on/scanr.git
cd scanr
pip install -r requirements.txt
```

Set your API key as an environment variable:

```bash
export POLYGON_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Open `http://localhost:5000` in your browser.

---

## Deployment

The app is deployed on [Render](https://render.com) via GitHub. The `Procfile` configures the web process:

```
web: gunicorn app:app
```

Columns 9–15 (intraday signals) require a Polygon.io paid plan. On the free tier, those columns will be empty but the scanner still works for all other signals.

---

## Notes

- The EU universe is scraped from Wikipedia index pages and cached in memory on first load.
- Market hours endpoint covers regular trading hours only — no public holiday detection.
- Ticker symbols link directly to Finviz for fast research.
