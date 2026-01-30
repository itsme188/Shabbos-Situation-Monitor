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

# Times of Israel
TOI_RSS_URL = "https://www.timesofisrael.com/feed/"
TOI_LIVEBLOG_URL = "https://www.timesofisrael.com/liveblog/"

# Polymarket - Iran strike prediction markets
POLYMARKET_EVENT_SLUG = "what-will-the-usisrael-target-in-iran-by-january-31"
POLYMARKET_API_URL = "https://gamma-api.polymarket.com/events"

# Display settings
MAX_ITEMS_PER_FEED = 15

# Request settings
REQUEST_TIMEOUT = 15  # seconds

# twikit authentication (optional - for Iran search with like filter)
# Run `python setup_twikit.py` once to authenticate
TWIKIT_COOKIES_FILE = "twikit_cookies.json"
