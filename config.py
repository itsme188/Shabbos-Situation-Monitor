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

# OSINT Accounts to Monitor (fetched via Twitter/Nitter/BlueSky fallback chain)
TWITTER_ACCOUNTS = [
    "Faytuks",
    "no_itsmyturn",
    "manniefabian",
    "Osint613",
    "Intel_Sky",
    "JSchanzer",
    "IntelCrab",
    "Global_Mil_Info",
    "AuroraIntel",
    # "IsraelRadar_",   # JS-rendered page — unfetchable without headless browser
    "JoeTruzman",
    # "YoavLimor",      # JS-rendered page — unfetchable without headless browser
    "AmichaiStein1",
]

# Trump Truth Social
TRUMP_TRUTH_RSS = "https://trumpstruth.org/feed"
TRUMP_TWITTER_MIRROR = "TrumpDailyPosts"  # Fallback Twitter account

# Google News Middle East/Iran (more reliable than Reuters RSS)
REUTERS_MIDEAST_RSS = "https://news.google.com/rss/search?q=Iran+OR+Israel+Middle+East&hl=en-US&gl=US&ceid=US:en"

# Fallback: BBC World Middle East RSS (reliable, low rate-limit risk)
REUTERS_FALLBACK_RSS = "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"

# Nitter instances to try (in order of reliability)
# Most are dead as of Mar 2026 — xcancel.com is the only one that sometimes works
NITTER_INSTANCES = [
    "xcancel.com",
]

# Twitter fallback: Google News RSS when all Twitter/Nitter methods fail
GOOGLE_NEWS_TWITTER_FALLBACK = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
TWITTER_TOPIC_QUERIES = [
    "Israel Iran military",
    "IDF breaking news",
    "Middle East conflict today",
]
TWITTER_SYNDICATION_TIMEOUT = 8   # seconds (fail fast, move to Nitter)
TWITTER_ACCOUNT_TIMEOUT = 60      # seconds (global timeout for all methods per batch)

# xcancel.com requires this specific User-Agent for RSS feeds
XCANCEL_USER_AGENT = "mistique"

# TwStalker — Twitter viewer with server-rendered HTML (no JS needed)
TWSTALKER_BASE = "https://twstalker.com"
TWSTALKER_TIMEOUT = 10  # seconds — pages are large (~500KB)

# BlueSky (AT Protocol) — open API, no auth needed for public posts
# Map Twitter usernames to BlueSky handles for accounts that cross-post
BLUESKY_HANDLES = {
    "Faytuks": "faytuks.bsky.social",
    # Other accounts exist on BlueSky but rarely post there
}
BLUESKY_API_BASE = "https://public.api.bsky.app/xrpc"

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
PREDICTION_MARKETS = [
    {
        "name": "Nuclear Deal",
        "event_slug": "us-iran-nuclear-deal-before-2027",
        "market_slug": None,  # single-market event
        "type": "deescalation",
    },
    {
        "name": "US Forces in Iran",
        "event_slug": "us-forces-enter-iran-by",
        "market_slug": "us-forces-enter-iran-by-december-31-573-642-385-371-179",
        "type": "escalation",
    },
    {
        "name": "Ground Invasion",
        "event_slug": "will-the-us-invade-iran-before-2027",
        "market_slug": None,
        "type": "escalation",
    },
    {
        "name": "Ceasefire by June 30",
        "event_slug": "iran-x-israelus-conflict-ends-by",
        "market_slug": "iran-x-israelus-conflict-ends-by-june-30-813-454",
        "type": "deescalation",
    },
]
AI_SUMMARY_MARKET_THRESHOLD = 5  # min percentage-point change to mention in summary

# AI Summary settings (requires ANTHROPIC_API_KEY environment variable)
AI_SUMMARY_MAX_TOKENS = 1500

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
AI_SUMMARY_MORNING_MODEL = "claude-opus-4-6"             # Best quality for morning summary
AI_SUMMARY_REGULAR_MODEL = "claude-haiku-4-5-20251001"   # Fast/cheap for 2-hour summaries

AI_SUMMARY_MORNING_PROMPT = """You are a concise news analyst monitoring the Middle East situation with an eye on strategic implications and financial markets.
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
- End with a short paragraph titled "Market Outlook:" covering potential stock market, oil, and defense sector implications of the overnight developments
- If nothing significant happened overnight, say so briefly in one paragraph
"""

AI_SUMMARY_REGULAR_PROMPT = """You are a concise news analyst monitoring the Middle East situation with an eye on strategic implications and financial markets.
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
  Example: [Markets] Fri 4:15 PM - Oil futures spike 3% on escalation fears
- The current time context is provided at the top of the feed data
- Convert all event times to ET (Eastern Time) for consistency
- Valid categories: Military, Diplomatic, Political, Breaking, Markets, Strategic
- After the bullets, add a single line: [Market Signal] followed by a one-sentence assessment of potential stock market, oil, or defense sector implications
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
- Keep it concise — this is a quick status check before Shabbos begins
"""
