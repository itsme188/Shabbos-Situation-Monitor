"""
Shabbos Situation Monitor - Configuration

Edit these values to customize behavior.
"""

# Server settings
HOST = "0.0.0.0"  # Allows access from other devices on network
PORT = 8080
DEBUG = False

# Refresh interval (seconds)
REFRESH_INTERVAL = 300  # 5 minutes

# Twitter Accounts to Monitor (instead of list - more reliable)
TWITTER_ACCOUNTS = [
    "Faytuks",
    "no_itsmyturn",
    "manniefabian",
    "sentdefender",
    "JSchanzer",
    "IntelCrab",
    "Global_Mil_Info",
    "AuroraIntel",
    "IsraelRadar_",
    "JoeTruzman",
    "YoavLimor",
    "AmichaiStein1",
]

# Trump Truth Social
TRUMP_TRUTH_RSS = "https://trumpstruth.org/feed"
TRUMP_TWITTER_MIRROR = "TrumpDailyPosts"  # Fallback Twitter account

# Google News Middle East/Iran (more reliable than Reuters RSS)
REUTERS_MIDEAST_RSS = "https://news.google.com/rss/search?q=Iran+OR+Israel+Middle+East&hl=en-US&gl=US&ceid=US:en"

# Nitter instances to try (in order of reliability)
NITTER_INSTANCES = [
    "xcancel.com",
    "nitter.poast.org",
    "nitter.privacydev.net",
    "nitter.cz",
    "nitter.1d4.us",
    "nitter.kavin.rocks",
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

# BlueSky (AT Protocol) — open API, no auth needed for public posts
# Map Twitter usernames to BlueSky handles for accounts that cross-post
BLUESKY_HANDLES = {
    "sentdefender": "sentdefender.bsky.social",
    # Add more OSINT accounts as they join BlueSky
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

# Polymarket - Iran/Israel strike prediction market (multi-outcome, auto-soonest date)
POLYMARKET_EVENT_SLUG = "usisrael-strikes-iran-by"
POLYMARKET_API_URL = "https://gamma-api.polymarket.com/events"

# Shabbos timing - location & candle lighting
LOCATION_LAT = 40.7128    # New York City
LOCATION_LON = -74.0060
LOCATION_TZ = "America/New_York"
CANDLE_LIGHTING_OFFSET = 18  # minutes before sunset
HAVDALAH_OFFSET = 50         # minutes after Saturday sunset
SHABBOS_SNAPSHOT_FILE = "shabbos_snapshot.json"

# Cache persistence (survives server restarts)
CACHE_FILE = "feed_cache.json"
CACHE_MAX_AGE = 7200  # seconds (2 hours) - ignore cache files older than this

# Display settings
MAX_ITEMS_PER_FEED = 15

# Request settings
REQUEST_TIMEOUT = 15  # seconds - general
NITTER_TIMEOUT = 8    # seconds - shorter for Nitter (responds fast or not at all)

# twikit authentication (optional - for Iran search with like filter)
# Run `python setup_twikit.py` once to authenticate
TWIKIT_COOKIES_FILE = "twikit_cookies.json"

# AI Summary settings (requires ANTHROPIC_API_KEY environment variable)
AI_SUMMARY_INTERVAL = 3600     # seconds (1 hour)
AI_SUMMARY_HOURLY_MODEL = "claude-haiku-4-5-20251001"  # Fast/cheap for hourly summaries
AI_SUMMARY_OVERVIEW_MODEL = "claude-opus-4-6"           # Best quality for 12-hour overview
AI_SUMMARY_MAX_TOKENS = 1024
AI_SUMMARY_OVERVIEW_INTERVAL = 3  # hours between overview regeneration

AI_SUMMARY_HOURLY_PROMPT = """You are a concise news analyst monitoring the Middle East situation.
Analyze the provided feed data and produce a bullet-point summary of the key developments.
Rules:
- Maximum 8 bullet points
- Each bullet should be one clear sentence
- Focus on NEW developments, not background
- If multiple sources report the same event, note that
- Highlight any escalation/de-escalation signals
- Start each bullet with a category tag AND event time in ET: [Category] HH:MM - description
  Example: [Military] 14:30 - IDF confirmed strikes on targets in southern Lebanon
  Example: [Breaking] 19:45 - Al Jazeera reports Iranian retaliation underway
- The current time context is provided at the top of the feed data
- Convert all event times to ET (Eastern Time) for consistency
- Valid categories: Military, Diplomatic, Political, Breaking, Markets
- If nothing significant is happening, say so briefly
"""

AI_SUMMARY_OVERVIEW_PROMPT = """You are a concise news analyst. Given several hours of bullet-point summaries about the Middle East situation, write a single paragraph (3-5 sentences) that captures the big picture.

Rules:
- Summarize the overall trajectory: is the situation escalating, de-escalating, or stable?
- Mention the 2-3 most significant developments
- Note any major shifts or turning points
- Write in present tense for ongoing situations
- Keep it under 100 words
- Do NOT use bullet points — write a flowing paragraph
- All times should be in ET (Eastern Time)
"""
