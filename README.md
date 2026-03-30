# Shabbos Situation Monitor

A hands-free, auto-refreshing local dashboard for monitoring Iran/Israel/Middle East developments during Shabbos and Yom Tov. Designed for zero interaction once started — AI-powered summaries, strategic analysis, and prediction market context delivered on a schedule.

## Dashboard

5-column layout with auto-scrolling columns:

| Strategic Analysis | Middle East | Times of Israel | Raw Feeds | AI Summary |
|---|---|---|---|---|
| FDD, CSIS, ISW articles with AI-generated summaries | Google News + BBC fallback | Liveblog + RSS | OSINT accounts + Trump (merged) | Hourly bullets + morning prose + market signals |

## Features

- **Strategic Analysis** — Think tank articles from FDD (RSS), CSIS, and ISW (direct scraping) with per-article AI summaries via Claude Haiku
- **AI Summary** — Schedule-aware generation: morning summary (Opus, prose), 2-hour bullet summaries (Haiku), candle-lighting summary (Opus, fires automatically at candle lighting time)
- **Market Lens** — Each AI summary includes a `[Market Signal]` line assessing stock/oil/defense implications. `[Strategic]` category for think tank insights.
- **Prediction Markets** — Polymarket odds for Iran risk scenarios (Nuclear Deal, US Forces, Ground Invasion, Ceasefire) fed into AI prompts
- **OSINT Feeds** — 11 Twitter/X accounts via 5-tier fallback (syndication, TwStalker, BlueSky, Nitter, Google News)
- **Yom Tov Detection** — Hebcal API auto-detects holiday dates, extends AI summary retention, disables auto-pause, adjusts refresh interval (15 min vs 10 min)
- **Reliability** — Exponential backoff on rate limits, crash-loop protection, caffeinate sleep prevention, AI toggle persistence across restarts, ThreadPoolExecutor timeout handling

## Quick Start (Mac)

```bash
cd ~/Desktop
git clone https://github.com/itsme188/Shabbos-Situation-Monitor.git
cd Shabbos-Situation-Monitor
./start.sh
```

Open **http://127.0.0.1:8080** in Safari. Toggle AI summary ON via the dashboard switch.

An AppleScript launcher app is included for one-click startup from the Desktop.

## Architecture

- **Flask** on Python 3, port 8080, binds 0.0.0.0
- **APScheduler** refreshes feeds every 10 minutes (15 during Yom Tov); AI summaries hourly at :05; candle-lighting check 4-8 PM daily
- **6 concurrent fetchers** via ThreadPoolExecutor: OSINT, Trump, Reuters/BBC, TOI, Think Tanks, Prediction Markets
- **feed_cache.json** persists across restarts (atomic writes, schema versioning, backoff state, AI toggle state)
- **start.sh** manages venv, auto-restart with crash-loop detection (max 10 in 10 min), caffeinate for macOS sleep prevention

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Main app (~2500 lines) — routes, scheduler, all fetchers, AI summary, Hebcal integration |
| `config.py` | All configuration — feed URLs, accounts, AI prompts, Polymarket markets, Yom Tov settings |
| `start.sh` | Production launcher with crash recovery, sleep prevention, port guards |
| `templates/index.html` | Dashboard template — 5-column grid, auto-scroll, day separators |
| `launcher.applescript` | macOS one-click startup (compiled into .app on Desktop) |

## AI Summary Schedule (ET)

| Time | Type | Model | Content |
|------|------|-------|---------|
| 1-7 AM | Quiet hours | — | No generation |
| 8 AM | Morning summary | Opus | Multi-paragraph prose covering overnight |
| 10 AM - 12 AM | 2-hour summaries | Haiku | 8 bullets max + `[Market Signal]` line |
| Candle lighting | Shabbos/Yom Tov summary | Opus | "Going into Shabbos" status check |

Valid categories: Military, Diplomatic, Political, Breaking, Markets, Strategic

## Configuration

Edit `config.py` to customize:

- `TWITTER_ACCOUNTS` — OSINT account list (11 accounts)
- `THINK_TANK_FEEDS` — RSS and scrape sources for strategic analysis
- `PREDICTION_MARKETS` — Polymarket event slugs for risk monitoring
- `REFRESH_INTERVAL` / `REFRESH_INTERVAL_YOM_TOV` — Feed update frequency
- `AI_SUMMARY_RETENTION_DAYS` — Days of AI summaries to keep (auto-extends during Yom Tov via Hebcal)
- `YOM_TOV_END` — Override auto-detection with manual ISO datetime, or `None` for Hebcal auto-detect
- `AI_SUMMARY_*_PROMPT` — Customize AI summary prompts (morning, regular, candle-lighting)

## Diagnostics

- **`/health`** — JSON status of all feeds (item count, last update, errors)
- **`/api/refresh-ai`** — Force immediate AI summary generation
- **`/api/toggle-ai`** — Toggle AI on/off
- **`server.log`** — Rotating log (50MB max, 5 backups)

## Tech Stack

- Python 3 / Flask / Jinja2
- APScheduler for background fetching
- Claude API (Anthropic) for AI summaries
- BeautifulSoup for HTML scraping
- feedparser for RSS
- Hebcal API for Jewish calendar
- Polymarket Gamma API for prediction markets

## License

MIT
