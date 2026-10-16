"""
Shabbos Situation Monitor - Configuration

Edit these values to customize behavior.
"""

# Server settings
HOST = "0.0.0.0"  # Allows access from other devices on network
PORT = 8080
DEBUG = False

# Refresh interval (seconds)
REFRESH_INTERVAL = 600       # 10 minutes (normal / Shabbos)
REFRESH_INTERVAL_YOM_TOV = 900  # 15 minutes (Yom Tov — longer to conserve resources)

# Live Wire column — breaking updates from Telegram channels + outlet RSS.
# Replaced Twitter scraping (Oct 2026): all free Twitter mirrors died.
# Telegram: public web preview at t.me/s/<channel>, no login needed.
# Every source below was verified live 2026-10-16 (posting within the last few hours).
# State/partisan propaganda channels (PressTV, Intel Slava, QudsN) deliberately excluded;
# NEXTA dropped (posts in Russian).
LIVE_WIRE_TELEGRAM = [
    {"channel": "manniefabian", "label": "Emanuel Fabian (TOI)", "region": "Israel"},
    {"channel": "englishabuali", "label": "Abu Ali Express", "region": "Israel"},
    {"channel": "idfofficial", "label": "IDF", "region": "Israel"},
    {"channel": "Osint613", "label": "Osint613", "region": "Israel"},
    {"channel": "Middle_East_Spectator", "label": "ME Spectator", "region": "Middle East"},
    {"channel": "warmonitors", "label": "War Monitor", "region": "World"},
    {"channel": "ClashReport", "label": "Clash Report", "region": "World"},
    {"channel": "OSINTdefender", "label": "OSINTdefender", "region": "World"},
    {"channel": "rnintel", "label": "Rerum Novarum", "region": "World"},
    {"channel": "kyivindependent_official", "label": "Kyiv Independent", "region": "Russia-Ukraine"},
    {"channel": "wartranslated", "label": "WarTranslated", "region": "Russia-Ukraine"},
    {"channel": "insiderpaper", "label": "Insider Paper", "region": "US"},
]

# Outlet RSS feeds — slower than Telegram but very stable
LIVE_WIRE_RSS = [
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "region": "Middle East"},
    {"name": "Iran International", "url": "https://www.iranintl.com/en/feed", "region": "Iran"},
    {"name": "The National", "url": "https://www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml", "region": "Gulf"},
    {"name": "Haaretz", "url": "https://www.haaretz.com/srv/haaretz-latest-headlines", "region": "Israel"},
    {"name": "JNS", "url": "https://www.jns.org/feed/", "region": "Israel"},
    {"name": "Arutz Sheva", "url": "https://www.israelnationalnews.com/Rss.aspx", "region": "Israel"},
    {"name": "Defense News", "url": "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml", "region": "US"},
    {"name": "The War Zone", "url": "https://www.twz.com/feed", "region": "US"},
]

# Keyword → region tags (first match wins; order matters — specific before broad)
LIVE_WIRE_REGION_KEYWORDS = [
    ("Yemen/Gulf", ["houthi", "yemen", "red sea", "saudi", "riyadh", "uae", "emirat", "qatar", "bahrain", "hormuz"]),
    ("Iran", ["iran", "tehran", "irgc", "khamenei"]),
    ("Lebanon", ["hezbollah", "lebanon", "beirut"]),
    ("Gaza", ["gaza", "hamas", "rafah", "khan younis"]),
    ("Israel", ["israel", "idf", "netanyahu", "jerusalem", "tel aviv", "west bank", "knesset"]),
    ("Syria", ["syria", "damascus"]),
    ("Russia-Ukraine", ["ukrain", "russia", "kyiv", "moscow", "kremlin", "putin", "zelensk", "donbas", "crimea"]),
    ("US", ["pentagon", "white house", "trump", "congress", "senate", "u.s.", "washington"]),
]

LIVE_WIRE_MAX_AGE_HOURS = 12   # drop anything older — this column is for "right now"
LIVE_WIRE_PER_SOURCE = 6       # cap per source so one chatty channel can't flood the column
LIVE_WIRE_PER_REGION = 12      # cap per region tag so one busy front can't crowd out the rest
LIVE_WIRE_MAX_ITEMS = 50       # total items shown
LIVE_WIRE_TIMEOUT = 45         # seconds for all sources together

# Trump Truth Social
TRUMP_TRUTH_RSS = "https://trumpstruth.org/feed"
TRUMP_TWITTER_MIRROR = "TrumpDailyPosts"  # Fallback Twitter account

# Google News Middle East/Iran (more reliable than Reuters RSS)
REUTERS_MIDEAST_RSS = "https://news.google.com/rss/search?q=Iran+OR+Israel+Middle+East+when:1d&hl=en-US&gl=US&ceid=US:en"

# Fallback: BBC World Middle East RSS (reliable, low rate-limit risk)
REUTERS_FALLBACK_RSS = "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"

# Nitter instances to try (in order of reliability)
# Most are dead as of Mar 2026 — xcancel.com is the only one that sometimes works
NITTER_INSTANCES = [
    "xcancel.com",
]

# Times of Israel
TOI_RSS_URL = "https://www.timesofisrael.com/feed/"
TOI_LIVEBLOG_URL = "https://www.timesofisrael.com/liveblog/"
# Try both zero-padded and non-padded day formats (TOI URL structure varies)
TOI_LIVEBLOG_DATE_PATTERNS = [
    "https://www.timesofisrael.com/liveblog-{month}-{day}-{year}/",
    "https://www.timesofisrael.com/liveblog-{month}-{day:02d}-{year}/",
]

# Shabbos timing - location & candle lighting
LOCATION_LAT = 40.7128    # New York City
LOCATION_LON = -74.0060
LOCATION_TZ = "America/New_York"
CANDLE_LIGHTING_OFFSET = 18  # minutes before sunset
HAVDALAH_OFFSET = 50         # minutes after Saturday sunset

# Yom Tov mode: set to end datetime for extended holidays, None for normal Shabbos
# Format: "YYYY-MM-DDTHH:MM" in ET. Shows "Yom Tov ends: ..." in header.
# Set before Yom Tov, reset to None after.
# Yom Tov detection: pulled automatically from Hebcal API
# Set to None to use automatic detection, or override with a manual ISO datetime string
YOM_TOV_END = None  # Auto-detected from Hebcal; override example: "2026-04-04T20:05"

# Cache persistence (survives server restarts)
CACHE_FILE = "feed_cache.json"
CACHE_MAX_AGE = 7200  # seconds (2 hours) - ignore cache files older than this

# Display settings
MAX_ITEMS_PER_FEED = 15
NEWS_FEED_MAX_AGE_HOURS = 36  # Skip news items older than this (Middle East, etc.)

# Request settings
REQUEST_TIMEOUT = 15  # seconds - general
NITTER_TIMEOUT = 8    # seconds - shorter for Nitter (responds fast or not at all)

# Think Tank Feeds — strategic analysis sources
THINK_TANK_FEEDS = [
    {
        "name": "FDD",
        "url": "https://www.fdd.org/feed/",
        "type": "rss",  # Direct RSS with content:encoded for rich article bodies
        "max_items": 8,
    },
    {
        "name": "CSIS",
        "url": "https://www.csis.org/analysis",
        "type": "scrape",  # Scrape analysis page for article links
        "max_items": 5,
        "link_pattern": "/analysis/",  # URL pattern to match article links
        "base_url": "https://www.csis.org",
    },
    {
        "name": "ISW",
        "url": "https://www.understandingwar.org/publications",
        "type": "scrape",  # Scrape publications page for article links
        "max_items": 3,
        "link_pattern": "/research/middle-east/iran",  # Only Iran-related articles
        "base_url": "https://understandingwar.org",
    },
]
THINK_TANK_MAX_AGE_HOURS = 36  # Skip articles older than this
THINK_TANK_SUMMARIZE = True    # AI-summarize each article (uses Haiku)
THINK_TANK_SUMMARY_MAX_NEW = 5  # Max new articles to summarize per cycle (rate limit)

# Prediction Markets — Polymarket Gamma API (no auth required)
# Used for AI summary context only (no UI display). Fetched every cycle.
POLYMARKET_API_BASE = "https://gamma-api.polymarket.com"
POLYMARKET_TIMEOUT = 10  # seconds per request
# Date-scoped markets expire — the fetcher skips closed markets, but refresh
# this list periodically (slugs verified live 2026-07-17; closed July 31
# markets removed 2026-10-16).
PREDICTION_MARKETS = [
    {
        "name": "Ground Invasion",
        "event_slug": "will-the-us-invade-iran-before-2027",
        "market_slug": None,
        "type": "escalation",
    },
    {
        "name": "Hormuz Normal by Dec 31",
        "event_slug": "strait-of-hormuz-traffic-returns-to-normal-by-december-31",
        "market_slug": None,
        "type": "deescalation",
    },
    {
        "name": "Regime Fall by 2027",
        "event_slug": "will-the-iranian-regime-fall-by-the-end-of-2026",
        "market_slug": None,
        "type": "escalation",
    },
]
AI_SUMMARY_MARKET_THRESHOLD = 5  # min percentage-point change to mention in summary

# Oil price context — background signal for AI summary significance weighting
# Fetched via Yahoo Finance chart API (no API key, no extra dependency)
OIL_TICKER = "CL=F"   # WTI Crude Futures (NYMEX)
OIL_FETCH_TIMEOUT = 10  # seconds

# AI Summary settings (requires ANTHROPIC_API_KEY environment variable)
AI_SUMMARY_MAX_TOKENS = 4000  # headroom: 5.5 models may spend tokens thinking before answering

# Multi-day retention: how many days of AI summaries to keep
# Set to 3 for 3-day Yom Tov, 1 for regular Shabbos
AI_SUMMARY_RETENTION_DAYS = 1  # Change to 3 before Yom Tov (Apr 2)
AI_SUMMARY_MAX_ENTRIES = 30  # ~8 summaries/day × 3 days + buffer

# Inactivity timeout (seconds) — auto-pauses AI when nobody views dashboard
# Disabled automatically when AI_SUMMARY_RETENTION_DAYS > 1 (Yom Tov mode)
AI_INACTIVITY_TIMEOUT = 1800  # 30 minutes

# Schedule (all hours in ET)
AI_SUMMARY_MORNING_HOUR = 8                              # 8 AM ET - comprehensive morning summary
AI_SUMMARY_REGULAR_HOURS = [10, 12, 14, 16, 18, 20, 22, 0]  # 2-hour summaries
AI_SUMMARY_QUIET_HOURS = range(1, 8)                     # 1 AM - 7 AM: no summaries

# Models
AI_SUMMARY_MORNING_MODEL = "claude-opus-5-5"             # Best quality for morning summary
AI_SUMMARY_REGULAR_MODEL = "claude-haiku-5-5"          # Fast/cheap for 2-hour summaries

AI_SUMMARY_MORNING_PROMPT = """You are a concise news analyst monitoring the Middle East situation.
Write a comprehensive summary of the key developments from the overnight period (roughly midnight to 8 AM ET).
Rules:
- Write 2-4 paragraphs in flowing prose (not bullet points)
- Cover the most significant developments chronologically
- Note the overall trajectory: escalation, de-escalation, or stable
- Highlight any breaking news that occurred while most US readers were asleep
- Mention 3-5 most important developments
- If think tank analysis articles are available, synthesize their strategic assessments into the narrative
- All times should be in ET (Eastern Time) using Day H:MM AM/PM format (e.g., Sat 3:15 AM)
- If prediction market odds are provided, mention any that shifted meaningfully (5+ percentage points) — these reflect how betting markets assess the probability of key events
- If oil market context is provided, use it to calibrate how significant events are (large price moves = markets reacting), but NEVER mention oil prices, market data, or financial implications in your output
- If nothing significant happened overnight, say so briefly in one paragraph
"""

AI_SUMMARY_REGULAR_PROMPT = """You are a concise news analyst monitoring the Middle East situation.
Analyze the provided feed data and produce a bullet-point summary of the key developments from the last 2 hours.
Rules:
- Maximum 8 bullet points
- Each bullet should be one clear sentence
- Focus on NEW developments, not background
- If multiple sources report the same event, note that
- Highlight any escalation/de-escalation signals
- If think tank analysis articles (from STRATEGIC ANALYSIS section) contain notable assessments, include them as [Strategic] bullets
- Start each bullet with a category tag AND event time in ET: [Category] Day H:MM AM/PM - description
  Example: [Military] Fri 2:30 PM - IDF confirmed strikes on targets in southern Lebanon
  Example: [Breaking] Fri 7:45 PM - Al Jazeera reports Iranian retaliation underway
  Example: [Strategic] Fri 3:00 PM - FDD analysis argues current escalation pattern mirrors 2024 April exchange
- The current time context is provided at the top of the feed data
- Convert all event times to ET (Eastern Time) for consistency
- Valid categories: Military, Diplomatic, Political, Breaking, Strategic
- If oil market context is provided, use it to calibrate how significant events are (large price moves = markets reacting), but NEVER mention oil prices, market data, or financial implications in your output
- If nothing significant is happening, say so briefly
"""

AI_SUMMARY_CANDLE_LIGHTING_PROMPT = """You are a concise news analyst monitoring the Middle East situation.
Write a brief "going into Shabbos" summary of where things stand right now.
Rules:
- Write 1-3 short paragraphs in flowing prose
- Focus on the current state of affairs and trajectory (escalating/de-escalating/stable)
- Mention the most significant developments from today
- If prediction market odds are provided, mention any that shifted meaningfully (5+ percentage points)
- If think tank analysis articles are available, note key strategic assessments
- All times should be in ET (Eastern Time) using Day H:MM AM/PM format
- If oil market context is provided, use it to calibrate how significant events are (large price moves = markets reacting), but NEVER mention oil prices, market data, or financial implications in your output
- Keep it concise — this is a quick status check before Shabbos begins
"""

# Situation Board — per-region status cards (replaces the Strategic Analysis column).
# Regenerated alongside every scheduled AI summary (and on manual refresh / startup).
SITUATION_BOARD_REGIONS = ["Israel", "Iran", "Yemen / Gulf", "Russia–Ukraine", "US Response"]

SITUATION_BOARD_PROMPT = """You maintain a situation board for someone glancing at a screen during Shabbos.
From the feed data, write one status card per region, in this order: {regions}.
Return ONLY a JSON array, no prose, no code fences. Each element:
{{
  "region": "<region name exactly as given>",
  "trend": "escalating" | "stable" | "de-escalating",
  "headline": "<the single most important current fact, max 12 words>",
  "summary": "<current state of play in 2 short sentences, max 45 words>",
  "last_event": "<most significant recent event, max 15 words>",
  "last_event_time": "<when it happened, ET, format Day H:MM AM/PM, e.g. Fri 3:27 PM; empty string if unknown>"
}}
Rules:
- Use only the feed data; never invent events. If a region has nothing new, say so plainly and mark it "stable".
- Prefer the newest information; the current time is at the top of the feed data.
- The STRATEGIC ANALYSIS section is background: use it to judge trajectory, don't cite it as news.
- If oil market context is provided, use it only to calibrate significance; never mention markets or prices.
- If a PREVIOUS BOARD is provided, judge "trend" relative to it.
"""

# Hourly weather strip at the bottom of the dashboard — Open-Meteo (free, no API key)
WEATHER_LABEL = "Lawrence, NY 11559"
WEATHER_LAT = 40.6157
WEATHER_LON = -73.7296
WEATHER_HOURS_SHOWN = 24
