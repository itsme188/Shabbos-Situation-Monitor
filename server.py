"""
Shabbos Situation Monitor - Main Server

A local server that fetches news from multiple sources and serves
an auto-refreshing dashboard for hands-free monitoring.

Run with: python server.py
Or use: ./start.sh
"""

import json
import logging
import os
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional
from email.utils import parsedate_to_datetime
from html import unescape
from zoneinfo import ZoneInfo
import re

# Rate limiter for twstalker — limits concurrent requests to avoid 429s
_twstalker_semaphore = threading.Semaphore(2)

from astral import LocationInfo
from astral.sun import sun

from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import feedparser
from bs4 import BeautifulSoup

# Conditional import: anthropic SDK is optional (graceful degradation)
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Load .env file if present (so API key doesn't need terminal export)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                _key = _key.strip()
                _val = _val.strip().strip('"').strip("'")
                if _key and _val:
                    # Use direct set — setdefault won't override empty values
                    # (Claude Code sets ANTHROPIC_API_KEY="" in env)
                    if not os.environ.get(_key):
                        os.environ[_key] = _val

# Runtime toggle for AI summary (can be flipped via dashboard without restart)
ai_summary_enabled = False  # Off by default — toggle on via dashboard to avoid wasting API credits

# Inactivity tracking: auto-pause AI summaries if nobody views the dashboard
_last_dashboard_view = None  # Set when someone loads the dashboard

from config import (
    HOST, PORT, DEBUG, REFRESH_INTERVAL,
    TWITTER_ACCOUNTS, TRUMP_TRUTH_RSS, TRUMP_TWITTER_MIRROR,
    REUTERS_MIDEAST_RSS, REUTERS_FALLBACK_RSS,
    NITTER_INSTANCES, NITTER_TIMEOUT, TOI_RSS_URL, TOI_LIVEBLOG_URL,
    TOI_LIVEBLOG_DATE_PATTERNS,
    GOOGLE_NEWS_TWITTER_FALLBACK, TWITTER_TOPIC_QUERIES,
    TWITTER_SYNDICATION_TIMEOUT, TWITTER_ACCOUNT_TIMEOUT, XCANCEL_USER_AGENT,
    BLUESKY_HANDLES, BLUESKY_API_BASE,
    TWSTALKER_BASE, TWSTALKER_TIMEOUT,
    MAX_ITEMS_PER_FEED, REQUEST_TIMEOUT,
    LOCATION_LAT, LOCATION_LON, LOCATION_TZ,
    CANDLE_LIGHTING_OFFSET, HAVDALAH_OFFSET,
    CACHE_FILE, CACHE_MAX_AGE,
    AI_SUMMARY_MAX_TOKENS,
    AI_SUMMARY_MORNING_HOUR, AI_SUMMARY_REGULAR_HOURS, AI_SUMMARY_QUIET_HOURS,
    AI_SUMMARY_MORNING_MODEL, AI_SUMMARY_REGULAR_MODEL,
    AI_SUMMARY_MORNING_PROMPT, AI_SUMMARY_REGULAR_PROMPT,
    AI_SUMMARY_RETENTION_DAYS, AI_SUMMARY_MAX_ENTRIES, AI_INACTIVITY_TIMEOUT,
    THINK_TANK_FEEDS,
    YOM_TOV_END,
)

# Setup logging with rotation
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_log_fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)
logger.addHandler(_console_handler)

_file_handler = RotatingFileHandler(
    'server.log', maxBytes=50 * 1024 * 1024, backupCount=5
)
_file_handler.setFormatter(_log_fmt)
logger.addHandler(_file_handler)

# Log anthropic SDK status
if not HAS_ANTHROPIC:
    logger.warning("anthropic package not installed - AI summary feature disabled")

# Flask app
app = Flask(__name__)

# Global cache for all feeds
cache: Dict = {
    "twitter_list": {"items": [], "last_updated": None, "error": None},
    "trump": {"items": [], "last_updated": None, "error": None},
    "reuters": {"items": [], "last_updated": None, "error": None},
    "toi_liveblog": {"items": [], "last_updated": None, "error": None},
    "think_tanks": {"items": [], "last_updated": None, "error": None},
    "ai_summary": {
        "items": [],
        "last_updated": None,
        "error": None,
        "summaries": [],          # Accumulated summary blocks (morning + 2-hour)
        "morning_summary": None,  # Latest morning summary (multi-paragraph, displayed specially)
    },
}


# ============ CACHE PERSISTENCE ============

def save_cache_to_disk() -> None:
    """Persist the feed cache to disk so restarts don't lose data.

    Uses atomic write (write to temp file, then rename) to avoid
    corrupted files if the process is killed mid-write.
    """
    try:
        serializable = {}
        for feed_name, feed_data in cache.items():
            entry = {
                "items": feed_data["items"],
                "last_updated": feed_data["last_updated"].isoformat() if feed_data["last_updated"] else None,
                "error": feed_data["error"],
            }
            # AI summary has extra fields to persist
            if feed_name == "ai_summary":
                entry["summaries"] = feed_data.get("summaries", [])
                entry["morning_summary"] = feed_data.get("morning_summary")
            serializable[feed_name] = entry
        # Build backoff state for persistence across crash-restarts
        backoff_state = {
            "toi_backoff_until": _toi_backoff_until.isoformat() if _toi_backoff_until else None,
            "toi_backoff_minutes": _toi_backoff_minutes,
            "xcancel_backoff_until": _xcancel_backoff_until.isoformat() if _xcancel_backoff_until else None,
            "xcancel_backoff_minutes": _xcancel_backoff_minutes,
            "trump_backoff_until": _trump_backoff_until.isoformat() if _trump_backoff_until else None,
            "trump_backoff_minutes": _trump_backoff_minutes,
            "reuters_backoff_until": _reuters_backoff_until.isoformat() if _reuters_backoff_until else None,
            "reuters_backoff_minutes": _reuters_backoff_minutes,
        }
        # Atomic write: write to temp file in same directory, then rename
        dir_name = os.path.dirname(os.path.abspath(CACHE_FILE))
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({
                    "saved_at": datetime.now().isoformat(),
                    "schema_version": 1,
                    "feeds": serializable,
                    "backoff_state": backoff_state,
                "ai_summary_enabled": ai_summary_enabled,
                }, f)
            os.replace(tmp_path, CACHE_FILE)
        except Exception:
            # Clean up temp file if rename failed
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        logger.debug("Cache saved to disk")
    except Exception as e:
        logger.warning(f"Failed to save cache to disk: {e}")


def load_cache_from_disk() -> bool:
    """Load cached feed data from disk on startup.

    Returns True if cache was loaded, False otherwise.
    Only loads if the cache file is less than CACHE_MAX_AGE seconds old.
    """
    try:
        if not os.path.exists(CACHE_FILE):
            return False
        with open(CACHE_FILE) as f:
            data = json.load(f)
        saved_at = datetime.fromisoformat(data["saved_at"])
        age = (datetime.now() - saved_at).total_seconds()
        if age > CACHE_MAX_AGE:
            logger.info(f"Cache file is {age/60:.0f}m old (>{CACHE_MAX_AGE/60:.0f}m limit), ignoring")
            return False
        feeds = data.get("feeds", {})
        loaded_count = 0
        for feed_name, feed_data in feeds.items():
            if feed_name in cache and feed_data.get("items"):
                cache[feed_name]["items"] = feed_data["items"]
                cache[feed_name]["error"] = feed_data.get("error")
                if feed_data.get("last_updated"):
                    cache[feed_name]["last_updated"] = datetime.fromisoformat(feed_data["last_updated"])
                # Restore AI summary history
                if feed_name == "ai_summary":
                    cache[feed_name]["summaries"] = feed_data.get("summaries", [])
                    cache[feed_name]["morning_summary"] = feed_data.get("morning_summary")
                loaded_count += 1
        # Restore backoff state so crash-restarts don't re-hammer rate-limited services
        _restore_backoff_state(data)
        # Restore AI summary enabled state so crash-restarts don't lose the toggle
        global ai_summary_enabled
        if data.get("ai_summary_enabled") is not None:
            ai_summary_enabled = data["ai_summary_enabled"]
            logger.info(f"Restored AI summary enabled state: {ai_summary_enabled}")
        # Prune AI summaries from previous days
        _prune_old_summaries()
        logger.info(f"Loaded {loaded_count} feeds from disk cache ({age/60:.1f}m old)")
        return loaded_count > 0
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as e:
        logger.debug(f"Could not load cache from disk: {e}")
        return False


def _restore_backoff_state(data: dict) -> None:
    """Restore backoff globals from persisted cache state.

    Called once at startup from load_cache_from_disk(). Prevents crash-restarts
    from immediately re-hammering services that were being rate-limited.
    """
    global _toi_backoff_until, _toi_backoff_minutes
    global _xcancel_backoff_until, _xcancel_backoff_minutes
    global _trump_backoff_until, _trump_backoff_minutes
    global _reuters_backoff_until, _reuters_backoff_minutes

    bs = data.get("backoff_state", {})
    if not bs:
        return

    now = datetime.now()
    restored = []

    for name, until_key, minutes_key, default_minutes in [
        ("TOI", "toi_backoff_until", "toi_backoff_minutes", 5),
        ("xcancel", "xcancel_backoff_until", "xcancel_backoff_minutes", 5),
        ("Trump", "trump_backoff_until", "trump_backoff_minutes", 5),
        ("Reuters", "reuters_backoff_until", "reuters_backoff_minutes", 5),
    ]:
        until_str = bs.get(until_key)
        minutes_val = bs.get(minutes_key, default_minutes)
        if until_str:
            until_dt = datetime.fromisoformat(until_str)
            if until_dt > now:
                remaining = (until_dt - now).total_seconds() / 60
                restored.append(f"{name}({remaining:.0f}m)")
                # Set the globals dynamically
                globals()[f"_{until_key}"] = until_dt
                globals()[f"_{minutes_key}"] = minutes_val
            # If expired, leave globals at defaults (None / 5)

    if restored:
        logger.info(f"Restored active backoff state: {', '.join(restored)}")


# ============ SHABBOS TIME CALCULATIONS ============

_tz = ZoneInfo(LOCATION_TZ)
_observer = LocationInfo(
    latitude=LOCATION_LAT, longitude=LOCATION_LON, timezone=LOCATION_TZ
).observer


def get_shabbos_times() -> Dict:
    """Calculate candle lighting & havdalah for the current/upcoming Shabbos.

    Finds the most recent Friday, computes sunset-based times, and if
    we're already past havdalah, advances to next week.
    """
    now = datetime.now(_tz)
    today = now.date()

    # Find the most recent Friday (weekday 4) including today
    days_since_friday = (today.weekday() - 4) % 7
    friday = today - timedelta(days=days_since_friday)
    saturday = friday + timedelta(days=1)

    fri_sunset = sun(_observer, date=friday, tzinfo=_tz)["sunset"]
    sat_sunset = sun(_observer, date=saturday, tzinfo=_tz)["sunset"]

    candle_lighting = fri_sunset - timedelta(minutes=CANDLE_LIGHTING_OFFSET)
    havdalah = sat_sunset + timedelta(minutes=HAVDALAH_OFFSET)

    # If we're past this Shabbos, look ahead to next week
    if now > havdalah:
        friday = friday + timedelta(days=7)
        saturday = friday + timedelta(days=1)
        fri_sunset = sun(_observer, date=friday, tzinfo=_tz)["sunset"]
        sat_sunset = sun(_observer, date=saturday, tzinfo=_tz)["sunset"]
        candle_lighting = fri_sunset - timedelta(minutes=CANDLE_LIGHTING_OFFSET)
        havdalah = sat_sunset + timedelta(minutes=HAVDALAH_OFFSET)

    return {
        "candle_lighting": candle_lighting,
        "havdalah": havdalah,
        "friday_date": friday,
        "candle_lighting_display": candle_lighting.strftime("%-I:%M %p"),
        "havdalah_display": havdalah.strftime("%-I:%M %p"),
    }


def is_shabbos() -> bool:
    """Check if we're currently in the Shabbos window."""
    times = get_shabbos_times()
    now = datetime.now(_tz)
    return times["candle_lighting"] <= now <= times["havdalah"]


# Nitter instance health tracking
nitter_health: Dict[str, Dict] = {
    instance: {"failures": 0, "last_success": None, "last_failure": None}
    for instance in NITTER_INSTANCES
}


def get_healthy_nitter_instances() -> List[str]:
    """Return Nitter instances sorted by health, best first."""
    def score(instance):
        h = nitter_health[instance]
        last_ok = h["last_success"].timestamp() if h["last_success"] else 0
        return (h["failures"], -last_ok)
    return sorted(NITTER_INSTANCES, key=score)


def record_nitter_success(instance: str):
    nitter_health[instance]["failures"] = 0
    nitter_health[instance]["last_success"] = datetime.now()


def record_nitter_failure(instance: str):
    nitter_health[instance]["failures"] += 1
    nitter_health[instance]["last_failure"] = datetime.now()


# Exponential backoff state for xcancel rate limiting (429s)
_xcancel_backoff_until: Optional[datetime] = None
_xcancel_backoff_minutes: int = 5  # Starting backoff; doubles on consecutive 429s, caps at 30

# Exponential backoff state for Trump feed (trumpstruth.org) rate limiting
_trump_backoff_until: Optional[datetime] = None
_trump_backoff_minutes: int = 5

# Exponential backoff state for Reuters/Google News rate limiting
_reuters_backoff_until: Optional[datetime] = None
_reuters_backoff_minutes: int = 5


# Nitter error patterns - these appear as RSS entry content when the instance
# is broken but still returns valid RSS XML with an error message as the entry
NITTER_ERROR_PATTERNS = [
    "whitelisted",
    "rate limited",
    "not available",
    "instance has been",
    "error fetching",
]


def _is_nitter_error_content(text: str) -> bool:
    """Check if text looks like a Nitter error message rather than a real tweet."""
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in NITTER_ERROR_PATTERNS)


# ============ UTILITY FUNCTIONS ============

def format_timestamp(timestamp_str: str, source_tz: str = None) -> str:
    """Convert various timestamp formats to readable display in ET.

    Args:
        timestamp_str: ISO 8601, RSS (RFC 2822), or other timestamp string.
        source_tz: If the parsed datetime is naive (no offset), assume this
                   timezone. E.g. "Asia/Jerusalem" for TOI liveblog.
    """
    if not timestamp_str:
        return ""
    try:
        # Try parsing ISO format
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        try:
            # Try RSS format (parsedate_to_datetime imported at module level)
            dt = parsedate_to_datetime(timestamp_str)
        except (ValueError, TypeError):
            return timestamp_str[:16] if timestamp_str else ""

    # Localize naive datetimes if source timezone is known
    if dt.tzinfo is None and source_tz:
        dt = dt.replace(tzinfo=ZoneInfo(source_tz))

    # Convert timezone-aware datetimes to ET for display
    if dt.tzinfo is not None:
        dt = dt.astimezone(ZoneInfo("America/New_York"))

    return dt.strftime('%a %-I:%M %p')


def clean_html(html_text: str) -> str:
    """Remove HTML tags and decode entities."""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return unescape(text)


def extract_text_with_links(html_text: str) -> str:
    """Remove HTML tags but preserve link URLs inline.

    For each <a href="URL">text</a>, outputs "text [URL]" so the
    destination is visible in plain-text display.
    """
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        link_text = a_tag.get_text(strip=True)
        if href and href != link_text:
            a_tag.replace_with(f"{link_text} [{href}]")
        else:
            a_tag.replace_with(link_text or href or "")
    text = soup.get_text(separator=" ", strip=True)
    # Strip bare truthsocial.com URLs — they're opaque post links that add no
    # readable content.  The entry's link field already has the canonical URL.
    text = re.sub(r'\[?https?://(?:www\.)?truthsocial\.com/\S+\]?', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return unescape(text)


class RateLimitError(Exception):
    """Raised when a request gets a 429 response."""
    pass


def safe_request(url: str, timeout: int = REQUEST_TIMEOUT, raise_on_429: bool = False) -> Optional[requests.Response]:
    """Make a request with error handling.

    Args:
        raise_on_429: If True, raises RateLimitError on 429 instead of returning None.
                      Callers that need backoff logic should set this.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.get(url, timeout=timeout, headers=headers)
        if response.status_code == 429:
            logger.warning(f"Rate limited (429) by {url}")
            if raise_on_429:
                raise RateLimitError(f"429 from {url}")
            return None
        response.raise_for_status()
        return response
    except RateLimitError:
        raise
    except Exception as e:
        logger.warning(f"Request failed for {url}: {e}")
        return None


# ============ TWITTER ACCOUNTS FETCHER ============

# Track which fetch method last succeeded per account (optimization: try it first)
_twitter_method_cache: Dict[str, str] = {}


def fetch_twitter_accounts() -> None:
    """Fetch tweets from monitored Twitter accounts via web scraping."""
    logger.info("Fetching Twitter accounts...")

    all_items = []
    account_status = {}

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(fetch_single_twitter_account, username): username
            for username in TWITTER_ACCOUNTS
        }
        for future in as_completed(futures, timeout=TWITTER_ACCOUNT_TIMEOUT):
            username = futures[future]
            try:
                items = future.result()
                all_items.extend(items)
                account_status[username] = len(items) > 0
            except Exception as e:
                logger.warning(f"Twitter fetch for @{username} failed: {e}")
                account_status[username] = False

    if all_items:
        all_items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        cache["twitter_list"] = {
            "items": all_items[:MAX_ITEMS_PER_FEED],
            "last_updated": datetime.now(),
            "error": None,
            "account_status": account_status,
            "source": "twitter",
        }
        logger.info(f"Got {len(all_items)} total items from Twitter accounts")
    else:
        # 5th fallback: Google News RSS for the monitored topics
        logger.info("All Twitter methods failed, trying Google News fallback...")
        gnews_items = _fetch_twitter_google_news_fallback()
        if gnews_items:
            all_items = gnews_items
            cache["twitter_list"] = {
                "items": gnews_items[:MAX_ITEMS_PER_FEED],
                "last_updated": datetime.now(),
                "error": "Feeds unavailable — showing news via Google News",
                "account_status": account_status,
                "source": "google_news",
            }
            logger.info(f"Got {len(gnews_items)} items from Google News fallback")
        else:
            cache["twitter_list"]["account_status"] = account_status
            cache["twitter_list"]["source"] = "none"
            if not cache["twitter_list"]["items"]:
                cache["twitter_list"]["error"] = "Could not fetch any OSINT feeds"
            logger.warning("All Twitter account fetches failed (including Google News)")


def _fetch_twitter_google_news_fallback() -> List[Dict]:
    """Fallback: fetch related news from Google News RSS when Twitter is unavailable."""
    all_items = []
    for query in TWITTER_TOPIC_QUERIES:
        url = GOOGLE_NEWS_TWITTER_FALLBACK.format(query=query.replace(" ", "+"))
        response = safe_request(url, timeout=10)
        if response:
            feed = feedparser.parse(response.content)
            for entry in feed.entries[:3]:
                # Google News titles use format "Headline - Source Name"
                title = entry.get("title", "")
                source = "News"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0]
                    source = parts[1] if len(parts) > 1 else "News"
                all_items.append({
                    "author": source,
                    "text": title[:300] + ("..." if len(title) > 300 else ""),
                    "timestamp": entry.get("published", ""),
                    "timestamp_display": format_timestamp(entry.get("published", "")),
                    "link": entry.get("link", ""),
                })
    return all_items


def _fetch_via_syndication(username: str) -> List[Dict]:
    """Method 1: Twitter syndication API (fastest when available)."""
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        response = requests.get(url, timeout=TWITTER_SYNDICATION_TIMEOUT, headers=headers)
        if response.status_code == 200:
            return parse_twitter_syndication(response.text, username)
    except Exception as e:
        logger.debug(f"Syndication failed for @{username}: {e}")
    return []


def _fetch_via_bluesky(username: str) -> List[Dict]:
    """Method 2: BlueSky AT Protocol API (public, no auth needed)."""
    bsky_handle = BLUESKY_HANDLES.get(username)
    if not bsky_handle:
        return []  # This account isn't on BlueSky
    try:
        url = f"{BLUESKY_API_BASE}/app.bsky.feed.getAuthorFeed?actor={bsky_handle}&limit=10"
        response = requests.get(url, timeout=8)
        response.raise_for_status()
        data = response.json()

        items = []
        for entry in data.get("feed", []):
            post = entry.get("post", {})
            record = post.get("record", {})
            text = record.get("text", "").strip()
            if not text:
                continue
            created_at = record.get("createdAt", "")
            items.append({
                "author": username,
                "text": text[:300] + ("..." if len(text) > 300 else ""),
                "timestamp": created_at,
                "timestamp_display": format_timestamp(created_at),
                "link": f"https://bsky.app/profile/{bsky_handle}",
            })
        if items:
            logger.info(f"BlueSky got {len(items)} posts for @{username}")
        return items
    except Exception as e:
        logger.debug(f"BlueSky failed for @{username}: {e}")
        return []


def _fetch_via_twstalker(username: str) -> List[Dict]:
    """Method 3: TwStalker HTML scraping (reliable, server-rendered).

    Uses curl subprocess because twstalker blocks Python requests via TLS fingerprinting.
    """
    url = f"{TWSTALKER_BASE}/{username}"
    try:
        with _twstalker_semaphore:
            result = subprocess.run(
                ["curl", "-s", "--connect-timeout", "8", "--max-time", str(TWSTALKER_TIMEOUT),
                 "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                 url],
                capture_output=True, text=True, timeout=TWSTALKER_TIMEOUT + 5,
            )
        html = result.stdout
        if not html or len(html) < 1000:
            return []
        return parse_twstalker_profile(html, username)
    except Exception as e:
        logger.debug(f"TwStalker failed for @{username}: {e}")
        return []


def _relative_to_iso(relative_str: str) -> str:
    """Convert a relative timestamp like '3 hours ago' to an approximate ISO string.

    Used for TwStalker results which only provide relative times.
    The resulting timestamps are approximate (±1 unit) but sufficient for sort ordering.
    """
    if not relative_str:
        return ""
    m = re.match(r'(\d+)\s+(second|minute|hour|day|week|month)s?\s+ago', relative_str, re.I)
    if not m:
        return ""
    amount, unit = int(m.group(1)), m.group(2).lower()
    delta_map = {
        "second": timedelta(seconds=amount),
        "minute": timedelta(minutes=amount),
        "hour": timedelta(hours=amount),
        "day": timedelta(days=amount),
        "week": timedelta(weeks=amount),
        "month": timedelta(days=amount * 30),
    }
    approx_time = datetime.now() - delta_map.get(unit, timedelta(0))
    return approx_time.isoformat()


def parse_twstalker_profile(html: str, username: str) -> List[Dict]:
    """Parse TwStalker profile page for tweets."""
    items = []
    # Split by activity-group1 blocks (each is a tweet)
    blocks = re.split(r'<div class="activity-group1">', html)

    for block in blocks[1:]:  # Skip pre-content
        if len(items) >= 5:
            break
        try:
            # Extract tweet link and ID
            link_match = re.search(r'href="(/([^/]+)/status/(\d+))"', block)
            if not link_match:
                continue
            original_author = link_match.group(2)
            link = f"https://twitter.com{link_match.group(1)}"

            # Extract relative timestamp
            time_match = re.search(
                r'(\d+ (?:seconds?|minutes?|hours?|days?|weeks?|months?) ago)',
                block,
            )
            timestamp_display = time_match.group(1) if time_match else ""

            # Extract text: strip HTML tags, SVGs, scripts
            clean = re.sub(r'<script[^>]*>.*?</script>', '', block, flags=re.S)
            clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.S)
            clean = re.sub(r'<svg[^>]*>.*?</svg>', '', clean, flags=re.S)
            clean = re.sub(r'<[^>]+>', '\n', clean)
            clean = unescape(clean)

            # Filter to lines that look like tweet content
            lines = [l.strip() for l in clean.split('\n') if l.strip()]
            text_lines = [
                l for l in lines
                if len(l) > 20
                and 'ago' not in l.lower()
                and not re.match(r'^[\d,\.]+$', l)
                and not l.startswith('http')
            ]
            text = ' '.join(text_lines[:3]).strip()
            if not text:
                continue  # Skip media-only tweets

            text = (lambda t: t[:300] + ("..." if len(t) > 300 else ""))(text)

            # Show original author if it's a retweet
            author = username
            if original_author.lower() != username.lower():
                text = f"RT @{original_author}: {text}"

            items.append({
                "author": author,
                "text": text,
                "timestamp": _relative_to_iso(timestamp_display),  # Approximate ISO for sorting
                "timestamp_display": timestamp_display,
                "link": link,
            })
        except Exception:
            continue

    return items


def _fetch_via_nitter_html(username: str) -> List[Dict]:
    """Method 5: Nitter HTML scraping (last resort)."""
    for instance in get_healthy_nitter_instances()[:4]:
        # Respect xcancel backoff from RSS 429s
        if "xcancel" in instance and _xcancel_backoff_until and datetime.now() < _xcancel_backoff_until:
            continue
        try:
            nitter_url = f"https://{instance}/{username}"
            response = safe_request(nitter_url, timeout=NITTER_TIMEOUT)
            if response:
                items = parse_nitter_profile(response.text, username)
                if items:
                    record_nitter_success(instance)
                    return items
            record_nitter_failure(instance)
        except Exception as e:
            record_nitter_failure(instance)
            logger.debug(f"Nitter {instance} failed for @{username}: {e}")
            continue
    return []


def fetch_single_twitter_account(username: str) -> List[Dict]:
    """Fetch tweets from a single account via multiple fallback methods."""
    logger.info(f"Fetching @{username}...")

    # Define methods in priority order
    methods = [
        ("syndication", lambda: _fetch_via_syndication(username)),
        ("twstalker", lambda: _fetch_via_twstalker(username)),
        ("bluesky", lambda: _fetch_via_bluesky(username)),
        ("nitter_rss", lambda: fetch_twitter_via_nitter_rss(username)),
        ("nitter_html", lambda: _fetch_via_nitter_html(username)),
    ]

    # Try last-successful method first (optimization)
    last_ok = _twitter_method_cache.get(username)
    if last_ok:
        methods.sort(key=lambda m: 0 if m[0] == last_ok else 1)

    for method_name, method_fn in methods:
        try:
            items = method_fn()
            if items:
                _twitter_method_cache[username] = method_name
                logger.info(f"Got {len(items)} tweets from @{username} via {method_name}")
                return items
        except Exception as e:
            logger.debug(f"{method_name} failed for @{username}: {e}")
            continue

    logger.warning(f"All methods failed for @{username}")
    return []


def fetch_twitter_via_nitter_rss(username: str) -> List[Dict]:
    """Try fetching tweets via Nitter RSS feeds (more reliable than HTML scraping)."""
    global _xcancel_backoff_until, _xcancel_backoff_minutes

    for instance in get_healthy_nitter_instances()[:3]:
        try:
            rss_url = f"https://{instance}/{username}/rss"
            # xcancel.com requires "mistique" User-Agent for RSS access
            if "xcancel" in instance:
                # Skip if in backoff period from a previous 429
                if _xcancel_backoff_until and datetime.now() < _xcancel_backoff_until:
                    logger.debug(f"xcancel: skipping @{username}, backoff active")
                    continue
                try:
                    response = requests.get(
                        rss_url,
                        timeout=NITTER_TIMEOUT,
                        headers={"User-Agent": XCANCEL_USER_AGENT},
                    )
                    if response.status_code == 429:
                        _xcancel_backoff_until = datetime.now() + timedelta(minutes=_xcancel_backoff_minutes)
                        logger.warning(f"xcancel rate-limited (429), backing off for {_xcancel_backoff_minutes}m")
                        _xcancel_backoff_minutes = min(_xcancel_backoff_minutes * 2, 30)
                        record_nitter_failure(instance)
                        continue
                    response.raise_for_status()
                    # Reset backoff on success
                    _xcancel_backoff_until = None
                    _xcancel_backoff_minutes = 5
                except requests.exceptions.HTTPError:
                    logger.debug(f"xcancel RSS failed for @{username}: HTTP error")
                    record_nitter_failure(instance)
                    continue
                except Exception as e:
                    logger.debug(f"xcancel RSS failed for @{username}: {e}")
                    record_nitter_failure(instance)
                    continue
            else:
                response = safe_request(rss_url, timeout=NITTER_TIMEOUT)
            if response:
                feed = feedparser.parse(response.content)
                if feed.entries:
                    # Check first entry for error content (e.g. "RSS reader not yet whitelisted")
                    first_text = clean_html(
                        feed.entries[0].get("title", "") or feed.entries[0].get("description", "")
                    )
                    if _is_nitter_error_content(first_text):
                        logger.warning(f"Nitter RSS {instance} returned error content: {first_text[:80]}")
                        record_nitter_failure(instance)
                        continue

                    record_nitter_success(instance)
                    items = []
                    for entry in feed.entries[:5]:
                        items.append({
                            "author": username,
                            "text": (lambda t: t[:300] + ("..." if len(t) > 300 else ""))(clean_html(entry.get("title", "") or entry.get("description", ""))),
                            "timestamp": entry.get("published", ""),
                            "timestamp_display": format_timestamp(entry.get("published", "")),
                            "link": entry.get("link", f"https://twitter.com/{username}"),
                        })
                    if items:
                        return items
            record_nitter_failure(instance)
        except Exception:
            record_nitter_failure(instance)
            continue
    return []


def parse_twitter_syndication(html: str, username: str) -> List[Dict]:
    """Parse Twitter's syndication timeline response."""
    items = []
    soup = BeautifulSoup(html, "html.parser")

    # Twitter syndication uses specific classes for tweets
    tweets = soup.select(".timeline-Tweet")

    for tweet in tweets[:5]:  # Limit per account
        try:
            text_elem = tweet.select_one(".timeline-Tweet-text")
            time_elem = tweet.select_one("time")

            if text_elem:
                items.append({
                    "author": username,
                    "text": (lambda t: t[:300] + ("..." if len(t) > 300 else ""))(text_elem.get_text(strip=True)),
                    "timestamp": time_elem.get("datetime", "") if time_elem else "",
                    "timestamp_display": time_elem.get_text(strip=True) if time_elem else "",
                    "link": f"https://twitter.com/{username}",
                })
        except Exception:
            continue

    return items


def parse_nitter_profile(html: str, username: str) -> List[Dict]:
    """Parse Nitter profile page HTML."""
    items = []
    soup = BeautifulSoup(html, "html.parser")

    tweets = soup.select(".timeline-item")

    for tweet in tweets:
        # Skip pinned tweets
        if tweet.select_one(".pinned"):
            continue

        if len(items) >= 5:  # Limit per account
            break
        try:
            content_elem = tweet.select_one(".tweet-content")
            time_elem = tweet.select_one(".tweet-date a")

            if content_elem:
                items.append({
                    "author": username,
                    "text": content_elem.get_text(strip=True),
                    "timestamp": time_elem.get("title", "") if time_elem else "",
                    "timestamp_display": time_elem.get_text(strip=True) if time_elem else "",
                    "link": f"https://twitter.com/{username}",
                })
        except Exception:
            continue

    return items


# ============ TRUMP TRUTH SOCIAL FETCHER ============

def fetch_trump() -> None:
    """Fetch Trump's Truth Social posts via RSS."""
    global _trump_backoff_until, _trump_backoff_minutes

    # Respect rate-limit backoff
    if _trump_backoff_until and datetime.now() < _trump_backoff_until:
        remaining = (_trump_backoff_until - datetime.now()).total_seconds() / 60
        logger.info(f"Trump: skipping fetch, rate-limit backoff active ({remaining:.0f}m remaining)")
        return

    logger.info("Fetching Trump Truth Social...")

    # Primary: trumpstruth.org RSS feed
    got_rate_limited = False
    try:
        response = safe_request(TRUMP_TRUTH_RSS, raise_on_429=True)
    except RateLimitError:
        response = None
        got_rate_limited = True

    if response:
        feed = feedparser.parse(response.content)
        if feed.entries:
            items = []
            for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                # Get content - try multiple fields
                content = entry.get("summary", "") or entry.get("description", "") or entry.get("title", "")
                _raw = extract_text_with_links(content)
                text = (_raw[:500] + ("..." if len(_raw) > 500 else "")).strip()

                # Skip empty posts (media-only, retruths with no text)
                if not text:
                    continue

                items.append({
                    "author": "realDonaldTrump",
                    "text": text,
                    "timestamp": entry.get("published", ""),
                    "timestamp_display": format_timestamp(entry.get("published", "")),
                    "link": entry.get("link", ""),
                })

            cache["trump"] = {
                "items": items,
                "last_updated": datetime.now(),
                "error": None,
            }
            # Reset backoff on success
            _trump_backoff_until = None
            _trump_backoff_minutes = 5
            logger.info(f"Got {len(items)} Trump posts from Truth Social RSS")
            return

    if got_rate_limited:
        _trump_backoff_until = datetime.now() + timedelta(minutes=_trump_backoff_minutes)
        logger.warning(f"Trump feed rate-limited, backing off for {_trump_backoff_minutes}m")
        _trump_backoff_minutes = min(_trump_backoff_minutes * 2, 30)

    # Fallback: Try Twitter mirror account via Nitter
    # (Nitter uses a different host, so Trump backoff doesn't block it)
    logger.info("Trying Twitter mirror fallback for Trump...")
    for instance in get_healthy_nitter_instances()[:4]:
        url = f"https://{instance}/{TRUMP_TWITTER_MIRROR}/rss"
        response = safe_request(url, timeout=NITTER_TIMEOUT)
        if response:
            feed = feedparser.parse(response.content)
            if feed.entries:
                # Check for Nitter error content
                first_text = clean_html(
                    feed.entries[0].get("title", "") or feed.entries[0].get("description", "")
                )
                if _is_nitter_error_content(first_text):
                    logger.warning(f"Nitter RSS {instance} returned error for Trump: {first_text[:80]}")
                    record_nitter_failure(instance)
                    continue

                items = []
                for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                    title = entry.get("title", "")
                    text = clean_html(title)[:400].strip()
                    if not text:
                        continue
                    items.append({
                        "author": "TrumpDailyPosts",
                        "text": text,
                        "timestamp": entry.get("published", ""),
                        "timestamp_display": format_timestamp(entry.get("published", "")),
                        "link": entry.get("link", ""),
                    })

                cache["trump"] = {
                    "items": items,
                    "last_updated": datetime.now(),
                    "error": "Using Twitter mirror (Truth Social RSS unavailable)",
                }
                logger.info(f"Got {len(items)} Trump posts from Twitter mirror")
                return

    # All methods failed
    if not cache["trump"]["items"]:
        cache["trump"]["error"] = "Could not fetch Trump posts"
    logger.warning("All methods failed for Trump feed")


# ============ REUTERS MIDDLE EAST FETCHER ============

def fetch_reuters() -> None:
    """Fetch Middle East news via RSS with fallback sources."""
    global _reuters_backoff_until, _reuters_backoff_minutes

    # Respect rate-limit backoff
    if _reuters_backoff_until and datetime.now() < _reuters_backoff_until:
        remaining = (_reuters_backoff_until - datetime.now()).total_seconds() / 60
        logger.info(f"Reuters: skipping fetch, rate-limit backoff active ({remaining:.0f}m remaining)")
        return

    logger.info("Fetching Middle East news...")

    # Try sources in order: primary Google News, then BBC fallback
    sources = [
        (REUTERS_MIDEAST_RSS, "Google News"),
        (REUTERS_FALLBACK_RSS, "BBC World"),
    ]

    for url, source_name in sources:
        try:
            response = safe_request(url, raise_on_429=True)
        except RateLimitError:
            _reuters_backoff_until = datetime.now() + timedelta(minutes=_reuters_backoff_minutes)
            logger.warning(f"Reuters/{source_name} rate-limited, backing off for {_reuters_backoff_minutes}m")
            _reuters_backoff_minutes = min(_reuters_backoff_minutes * 2, 30)
            continue

        if response:
            feed = feedparser.parse(response.content)
            if feed.entries:
                items = []
                for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                    items.append({
                        "title": entry.get("title", ""),
                        "summary": clean_html(entry.get("summary", ""))[:250],
                        "timestamp": entry.get("published", ""),
                        "timestamp_display": format_timestamp(entry.get("published", "")),
                        "link": entry.get("link", ""),
                    })

                error_msg = None if source_name == "Google News" else f"Primary source unavailable — showing {source_name}"
                cache["reuters"] = {
                    "items": items,
                    "last_updated": datetime.now(),
                    "error": error_msg,
                }
                # Reset backoff on success
                _reuters_backoff_until = None
                _reuters_backoff_minutes = 5
                logger.info(f"Got {len(items)} items from {source_name}")
                return

    # All sources failed
    if not cache["reuters"]["items"]:
        cache["reuters"]["error"] = "Could not fetch news feed (all sources failed)"
    logger.warning("All news sources failed for Middle East feed")


# ============ TIMES OF ISRAEL FETCHER ============

# Exponential backoff state for TOI rate limiting (429s)
_toi_backoff_until: Optional[datetime] = None
_toi_backoff_minutes: int = 5  # Starting backoff; doubles on consecutive 429s, caps at 30

def fetch_toi() -> None:
    """Fetch Times of Israel from RSS and liveblog."""
    global _toi_backoff_until, _toi_backoff_minutes

    # Skip if we're in a backoff period from a previous 429
    if _toi_backoff_until and datetime.now() < _toi_backoff_until:
        remaining = (_toi_backoff_until - datetime.now()).total_seconds() / 60
        logger.info(f"TOI: skipping fetch, rate-limit backoff active ({remaining:.0f}m remaining)")
        return

    logger.info("Fetching Times of Israel...")
    rss_items = []
    liveblog_items = []
    got_rate_limited = False

    # Fetch RSS feed (always, independent of liveblog)
    try:
        response = safe_request(TOI_RSS_URL, raise_on_429=True)
    except RateLimitError:
        response = None
        got_rate_limited = True
    if response:
        feed = feedparser.parse(response.content)
        for entry in feed.entries[:10]:
            rss_items.append({
                "title": entry.get("title", ""),
                "summary": clean_html(entry.get("summary", ""))[:200],
                "timestamp": entry.get("published", ""),
                "timestamp_display": format_timestamp(entry.get("published", "")),
                "link": entry.get("link", ""),
                "source": "rss",
            })
        logger.info(f"Got {len(rss_items)} items from TOI RSS")

    # Build list of liveblog URLs to try — date-specific FIRST, base URL last.
    # The base /liveblog/ URL points to a stale 2020 archive page, so it must
    # only be tried as a last resort after current date-specific URLs.
    # Use Israel time since TOI publishes on Israel schedule.
    liveblog_urls = []
    try:
        now_israel = datetime.now(ZoneInfo("Asia/Jerusalem"))
        yesterday_israel = now_israel - timedelta(days=1)
        for dt in [now_israel, yesterday_israel]:
            for pattern in TOI_LIVEBLOG_DATE_PATTERNS:
                date_url = pattern.format(
                    month=dt.strftime("%B").lower(),
                    day=dt.day,
                    year=dt.year,
                )
                if date_url not in liveblog_urls:
                    liveblog_urls.append(date_url)
    except Exception as e:
        logger.debug(f"Error building liveblog date URLs: {e}")
    liveblog_urls.append(TOI_LIVEBLOG_URL)  # Stale fallback — last resort

    # Try each liveblog URL until one works (stop on rate limit)
    for url in liveblog_urls:
        try:
            response = safe_request(url, raise_on_429=True)
        except RateLimitError:
            got_rate_limited = True
            break  # Stop trying more URLs — we're rate-limited
        if response:
            soup = BeautifulSoup(response.content, "html.parser")
            liveblog_items = parse_toi_liveblog(soup, url)
            if liveblog_items:
                logger.info(f"Got {len(liveblog_items)} liveblog items from {url}")
                break

    if not liveblog_items:
        logger.warning(f"TOI liveblog: no items from any URL. Tried: {liveblog_urls}")

    # Activate exponential backoff on 429
    if got_rate_limited:
        _toi_backoff_until = datetime.now() + timedelta(minutes=_toi_backoff_minutes)
        logger.warning(f"TOI rate-limited, backing off for {_toi_backoff_minutes}m")
        _toi_backoff_minutes = min(_toi_backoff_minutes * 2, 30)  # Double up to 30m cap

    # Combine: liveblog items first, then RSS
    items = liveblog_items + rss_items

    if items:
        cache["toi_liveblog"] = {
            "items": items[:MAX_ITEMS_PER_FEED],
            "last_updated": datetime.now(),
            "error": None if liveblog_items else "Liveblog unavailable, showing RSS only",
        }
        # Reset backoff on successful fetch
        if not got_rate_limited:
            _toi_backoff_until = None
            _toi_backoff_minutes = 5
    else:
        # Both liveblog and RSS failed — preserve last-good items rather than
        # showing an empty column (stale data beats no data on Shabbos)
        old_items = cache["toi_liveblog"].get("items", [])
        if old_items:
            cache["toi_liveblog"]["error"] = "Showing cached content (fetch failed)"
            logger.warning("TOI fetch failed, preserving %d cached items", len(old_items))
        else:
            cache["toi_liveblog"]["error"] = "Could not fetch TOI content"


def parse_toi_liveblog(soup, source_url: str = "") -> List[Dict]:
    """Parse Times of Israel liveblog page."""
    items = []

    # Try various selectors for liveblog entries
    selectors = [
        ".liveblog-entry",
        ".live-update",
        "article.update",
        ".lb-item",
        "[data-liveblog-entry]",
        ".timeline-entry",
        # Additional selectors for potential TOI redesigns
        ".liveblog__entry",
        ".live-blog-entry",
        "[data-entry-id]",
        ".blog-entry",
    ]

    entries = []
    for selector in selectors:
        entries = soup.select(selector)
        if entries:
            logger.info(f"TOI liveblog matched selector '{selector}' ({len(entries)} entries)")
            break

    # Structural fallback: find containers holding liveblog_entry links
    if not entries:
        entry_links = soup.select('a[href*="liveblog_entry"], a[href*="liveblog-entry"]')
        if entry_links:
            seen_parents = set()
            for link in entry_links:
                parent = link.find_parent(["article", "div", "section", "li"])
                if parent and id(parent) not in seen_parents:
                    seen_parents.add(id(parent))
                    entries.append(parent)
            if entries:
                logger.info(f"TOI liveblog: structural fallback found {len(entries)} entries via liveblog_entry links")

    if not entries:
        page_title = soup.title.string if soup.title else "N/A"
        body = soup.find("body")
        body_classes = body.get("class", []) if body else []
        logger.warning(
            f"TOI liveblog: no selectors matched. Title: {page_title}, "
            f"URL: {source_url}, body classes: {body_classes}"
        )
        return []

    for entry in entries[:10]:
        try:
            time_elem = entry.select_one("time, .timestamp, .time, .lb-time, .entry-time, [datetime]")
            content_elem = entry.select_one(".content, .entry-content, p, .lb-content, .entry-text")
            title_elem = entry.select_one("h2, h3, h4, .entry-title, .headline")

            if content_elem or title_elem:
                raw_dt = time_elem.get("datetime", "") if time_elem else ""
                items.append({
                    "title": title_elem.get_text(strip=True) if title_elem else "",
                    "summary": content_elem.get_text(strip=True)[:250] if content_elem else "",
                    "timestamp": raw_dt,
                    "timestamp_display": format_timestamp(raw_dt, source_tz="Asia/Jerusalem") if raw_dt else "LIVE",
                    "link": source_url or TOI_LIVEBLOG_URL,
                    "source": "liveblog",
                })
        except Exception as e:
            logger.debug(f"Error parsing liveblog entry: {e}")
            continue

    return items


# ============ THINK TANK FETCHER ============

def fetch_think_tanks() -> None:
    """Fetch strategic analysis articles from think tank RSS feeds (FDD, CSIS, ISW)."""
    logger.info("Fetching think tank articles...")
    all_items = []
    errors = []

    for feed_def in THINK_TANK_FEEDS:
        try:
            response = safe_request(feed_def["url"], raise_on_429=True)
        except RateLimitError:
            errors.append(f"{feed_def['name']}: rate limited")
            continue

        if not response:
            errors.append(f"{feed_def['name']}: no response")
            continue

        try:
            feed = feedparser.parse(response.content)
        except Exception as e:
            errors.append(f"{feed_def['name']}: parse error: {e}")
            continue

        for entry in feed.entries[:feed_def["max_items"]]:
            # For direct RSS (FDD): use content:encoded if available (richer than summary)
            content = ""
            if feed_def["type"] == "rss" and entry.get("content"):
                content = clean_html(entry["content"][0].get("value", ""))[:500]
            elif entry.get("summary"):
                content = clean_html(entry["summary"])[:300]

            # Extract source from Google News title format: "Title - Source"
            title = entry.get("title", "")
            source = feed_def["name"]
            if feed_def["type"] == "google_news" and " - " in title:
                title, source = title.rsplit(" - ", 1)

            ts_display = format_timestamp(entry.get("published", ""))

            all_items.append({
                "title": title.strip(),
                "summary": content,
                "timestamp": entry.get("published", ""),
                "timestamp_display": ts_display,
                "link": entry.get("link", ""),
                "source": source.strip(),
                "author": entry.get("author", entry.get("dc_creator", "")),
            })

    if all_items:
        # Sort by timestamp (newest first)
        all_items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        all_items = all_items[:MAX_ITEMS_PER_FEED]
        cache["think_tanks"] = {
            "items": all_items,
            "last_updated": datetime.now(),
            "error": "; ".join(errors) if errors else None,
        }
        logger.info(f"Think tanks: fetched {len(all_items)} articles ({'; '.join(errors)}" if errors else f"Think tanks: fetched {len(all_items)} articles")
    elif errors:
        # Preserve last-good items on total failure
        if not cache["think_tanks"]["items"]:
            cache["think_tanks"]["error"] = "; ".join(errors)
        logger.warning(f"Think tanks: all sources failed: {'; '.join(errors)}")


# ============ AI SUMMARY FETCHER ============


def _parse_ai_bullets(summary_text: str) -> tuple:
    """Parse AI-generated summary text into structured bullet points.

    Returns:
        (bullets, market_signal): bullets is a list of dicts, market_signal is
        a string (or None) extracted from the [Market Signal] line.
    """
    bullets = []
    market_signal = None
    time_pattern = re.compile(r'^\[([^\]]+)\]\s*(?:[A-Z][a-z]{2}\s+)?(\d{1,2}:\d{2}(?:\s*[AaPp][Mm])?)\s*[-\u2013\u2014]\s*(.+)$')
    gen_time = datetime.now(ZoneInfo("America/New_York")).strftime("%a %-I:%M %p")

    for line in summary_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        cleaned = line.lstrip("-*\u2022 ").strip()
        if not cleaned:
            continue

        # Extract [Market Signal] line separately
        if cleaned.startswith("[Market Signal]"):
            market_signal = cleaned.replace("[Market Signal]", "").strip().lstrip(":-–— ").strip()
            continue

        match = time_pattern.match(cleaned)
        if match:
            category, event_time, description = match.groups()
            bullets.append({
                "text": f"[{category}] {description.strip()}",
                "timestamp_display": event_time,
                "category": category,
            })
        elif cleaned.startswith("["):
            bullets.append({
                "text": cleaned,
                "timestamp_display": gen_time,
                "category": "",
            })

    if not bullets:
        bullets = [{
            "text": summary_text[:500] + ("..." if len(summary_text) > 500 else ""),
            "timestamp_display": gen_time,
            "category": "",
        }]

    # Sort bullets chronologically by timestamp_display
    def _sort_key_for_time(display_str):
        """Convert display timestamp to sortable 24hr string."""
        try:
            clean = re.sub(r'^[A-Z][a-z]{2}\s+', '', display_str)
            dt_parsed = datetime.strptime(clean.strip(), "%I:%M %p")
            return dt_parsed.strftime("%H:%M")
        except ValueError:
            return display_str  # Old 24hr format still sorts ok

    bullets.sort(key=lambda b: _sort_key_for_time(b.get("timestamp_display", "99:99")))
    return bullets, market_signal


def _prune_old_summaries() -> None:
    """Remove AI summaries older than AI_SUMMARY_RETENTION_DAYS (ET timezone).

    Called at startup, before generation, and on dashboard load to ensure
    stale entries beyond the retention window never accumulate or display.
    Retention of 1 = today only (regular Shabbos). Retention of 3 = 3-day Yom Tov.
    """
    today_et = datetime.now(ZoneInfo("America/New_York")).date()

    summaries = cache["ai_summary"].get("summaries", [])
    if summaries:
        filtered = []
        for entry in summaries:
            try:
                gen_dt = datetime.fromisoformat(entry.get("generated_at", ""))
                # generated_at is naive server-local time (ET)
                gen_date = gen_dt.date()
                if (today_et - gen_date).days < AI_SUMMARY_RETENTION_DAYS:
                    filtered.append(entry)
            except (ValueError, TypeError):
                filtered.append(entry)  # Keep unparseable entries (defensive)

        if len(filtered) < len(summaries):
            logger.info(f"Pruned {len(summaries) - len(filtered)} old AI summaries (keeping {len(filtered)} within {AI_SUMMARY_RETENTION_DAYS}-day window)")
            cache["ai_summary"]["summaries"] = filtered

    # Clear morning summary if outside retention window
    morning = cache["ai_summary"].get("morning_summary")
    if morning:
        try:
            gen_dt = datetime.fromisoformat(morning.get("generated_at", ""))
            if (today_et - gen_dt.date()).days >= AI_SUMMARY_RETENTION_DAYS:
                cache["ai_summary"]["morning_summary"] = None
                logger.info(f"Cleared stale morning summary from {gen_dt.date()}")
        except (ValueError, TypeError):
            pass

    # Clear items array if no summaries remain
    if not cache["ai_summary"].get("summaries"):
        cache["ai_summary"]["items"] = []


def _build_feed_digest() -> str:
    """Gather all current feed content into a text digest for AI summarization."""
    now_et = datetime.now(ZoneInfo("America/New_York"))
    now_israel = datetime.now(ZoneInfo("Asia/Jerusalem"))

    feed_text_parts = [
        f"Current time: {now_et.strftime('%a %-I:%M %p')} ET (New York) / "
        f"{now_israel.strftime('%H:%M')} Israel time"
    ]

    for feed_name, feed_data in cache.items():
        if feed_name == "ai_summary":
            continue
        items = feed_data.get("items", [])
        if not items:
            continue

        # Label sections distinctly so the LLM knows the source type
        label_map = {
            "think_tanks": "STRATEGIC ANALYSIS (Think Tanks — FDD, CSIS, ISW)",
            "twitter_list": "OSINT FEEDS",
            "trump": "TRUMP STATEMENTS",
            "reuters": "MIDDLE EAST NEWS",
            "toi_liveblog": "TIMES OF ISRAEL",
        }
        feed_text_parts.append(f"\n--- {label_map.get(feed_name, feed_name.upper())} ---")
        for item in items[:10]:
            parts = []
            if item.get("author"):
                parts.append(f"@{item['author']}")
            if item.get("timestamp_display"):
                parts.append(f"[{item['timestamp_display']}]")
            if item.get("title"):
                parts.append(item["title"])
            if item.get("text"):
                parts.append(item["text"][:200])
            if item.get("summary"):
                parts.append(item["summary"][:200])
            if item.get("question"):
                parts.append(f"Market: {item['question']} ({item.get('probability', '?')}%)")
            feed_text_parts.append(" | ".join(parts))

    return "\n".join(feed_text_parts) if len(feed_text_parts) > 1 else ""


def _generate_morning_summary(api_key: str) -> None:
    """Generate comprehensive morning summary covering overnight data (Opus).

    Retries once on transient API errors (connection, server) with a 30s delay.
    Auth errors fail immediately (not retry-able without human intervention).
    """
    logger.info("Generating morning AI summary (Opus)...")

    feed_digest = _build_feed_digest()
    if not feed_digest:
        cache["ai_summary"]["error"] = "No feed data available to summarize"
        return

    max_retries = 2
    for attempt in range(max_retries):
        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=AI_SUMMARY_MORNING_MODEL,
                max_tokens=AI_SUMMARY_MAX_TOKENS,
                system=AI_SUMMARY_MORNING_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Here is the current feed data. Summarize overnight developments:\n\n{feed_digest}",
                }],
            )

            summary_text = message.content[0].text.strip()
            gen_time = datetime.now()
            gen_et = datetime.now(ZoneInfo("America/New_York"))

            morning_entry = {
                "type": "morning",
                "text": summary_text,
                "generated_at": gen_time.isoformat(),
                "generated_at_display": gen_et.strftime("%a %-I:%M %p ET"),
                "hour_label": "Morning Summary",
                "bullets": [],
            }

            # Store as morning summary (displayed specially in template)
            cache["ai_summary"]["morning_summary"] = morning_entry

            # Also prepend to summaries list for history
            summaries = cache["ai_summary"].get("summaries", [])
            summaries.insert(0, morning_entry)
            cache["ai_summary"]["summaries"] = summaries[:AI_SUMMARY_MAX_ENTRIES]

            cache["ai_summary"]["items"] = []
            cache["ai_summary"]["last_updated"] = gen_time
            cache["ai_summary"]["error"] = None

            logger.info("Morning AI summary generated (Opus)")
            return  # Success

        except anthropic.AuthenticationError as e:
            logger.error(f"AI summary: authentication error — check API key: {e}")
            cache["ai_summary"]["error"] = "API key invalid — check .env file"
            return  # Don't retry auth errors

        except (anthropic.APIConnectionError, anthropic.InternalServerError, anthropic.RateLimitError) as e:
            if attempt < max_retries - 1:
                logger.warning(f"Morning AI summary: transient error (attempt {attempt + 1}), retrying in 30s: {e}")
                time.sleep(30)
            else:
                logger.warning(f"Morning AI summary error after {max_retries} attempts: {e}")
                if not cache["ai_summary"].get("summaries") and not cache["ai_summary"]["items"]:
                    cache["ai_summary"]["error"] = f"Summary unavailable: {str(e)[:80]}"

        except Exception as e:
            logger.warning(f"Morning AI summary error: {e}")
            if not cache["ai_summary"].get("summaries") and not cache["ai_summary"]["items"]:
                cache["ai_summary"]["error"] = f"Summary unavailable: {str(e)[:80]}"
            return  # Unknown error — don't retry


def _generate_regular_summary(api_key: str) -> None:
    """Generate 2-hour summary using Haiku.

    Retries once on transient API errors (connection, server) with a 30s delay.
    Auth errors fail immediately (not retry-able without human intervention).
    """
    logger.info("Generating 2-hour AI summary (Haiku)...")

    feed_digest = _build_feed_digest()
    if not feed_digest:
        cache["ai_summary"]["error"] = "No feed data available to summarize"
        return

    max_retries = 2
    for attempt in range(max_retries):
        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model=AI_SUMMARY_REGULAR_MODEL,
                max_tokens=AI_SUMMARY_MAX_TOKENS,
                system=AI_SUMMARY_REGULAR_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Here are the current feed items. Summarize the key developments:\n\n{feed_digest}",
                }],
            )

            summary_text = message.content[0].text
            bullets, market_signal = _parse_ai_bullets(summary_text)

            gen_time = datetime.now()
            gen_et = datetime.now(ZoneInfo("America/New_York"))
            hour_end = gen_et.replace(minute=0, second=0, microsecond=0)
            hour_start = hour_end - timedelta(hours=2)

            summary_entry = {
                "type": "regular",
                "generated_at": gen_time.isoformat(),
                "generated_at_display": gen_et.strftime("%a %-I:%M %p ET"),
                "hour_label": f"{hour_start.strftime('%-I:%M')}-{hour_end.strftime('%-I:%M %p')} ET",
                "bullets": bullets,
                "market_signal": market_signal,
            }

            summaries = cache["ai_summary"].get("summaries", [])
            summaries.insert(0, summary_entry)
            cache["ai_summary"]["summaries"] = summaries[:AI_SUMMARY_MAX_ENTRIES]

            cache["ai_summary"]["items"] = bullets
            cache["ai_summary"]["last_updated"] = gen_time
            cache["ai_summary"]["error"] = None

            logger.info(f"2-hour AI summary: {len(bullets)} bullets, {len(summaries)} total in history")
            return  # Success

        except anthropic.AuthenticationError as e:
            logger.error(f"AI summary: authentication error — check API key: {e}")
            cache["ai_summary"]["error"] = "API key invalid — check .env file"
            return  # Don't retry auth errors

        except (anthropic.APIConnectionError, anthropic.InternalServerError, anthropic.RateLimitError) as e:
            if attempt < max_retries - 1:
                logger.warning(f"AI summary: transient error (attempt {attempt + 1}), retrying in 30s: {e}")
                time.sleep(30)
            else:
                logger.warning(f"AI summary error after {max_retries} attempts: {e}")
                if not cache["ai_summary"].get("summaries") and not cache["ai_summary"]["items"]:
                    cache["ai_summary"]["error"] = f"Summary unavailable: {str(e)[:80]}"

        except Exception as e:
            logger.warning(f"AI summary error: {e}")
            if not cache["ai_summary"].get("summaries") and not cache["ai_summary"]["items"]:
                cache["ai_summary"]["error"] = f"Summary unavailable: {str(e)[:80]}"
            return  # Unknown error — don't retry


def fetch_ai_summary(force: bool = False) -> None:
    """Generate AI summary based on time-of-day schedule.

    Schedule (all times ET):
    - 1 AM - 7 AM: quiet hours, no summaries generated
    - 8 AM: morning summary (Opus, multi-paragraph, covers overnight)
    - 10 AM, 12 PM, 2 PM, 4 PM, 6 PM, 8 PM, 10 PM, 12 AM: 2-hour summaries (Haiku)
    """
    global ai_summary_enabled

    if not ai_summary_enabled:
        cache["ai_summary"]["error"] = "AI summary paused (toggle on dashboard)"
        return

    # Auto-pause if nobody has viewed the dashboard recently
    # Skip during multi-day Yom Tov mode — nobody views dashboard but summaries must keep generating
    if AI_SUMMARY_RETENTION_DAYS <= 1 and _last_dashboard_view is not None:
        idle_seconds = (datetime.now() - _last_dashboard_view).total_seconds()
        if idle_seconds > AI_INACTIVITY_TIMEOUT:
            ai_summary_enabled = False
            cache["ai_summary"]["error"] = "AI summary auto-paused (no viewers for 30 min). Toggle on to resume."
            logger.info(f"AI summary auto-paused: no dashboard views for {idle_seconds / 60:.0f} min")
            return

    if not HAS_ANTHROPIC:
        cache["ai_summary"]["error"] = "anthropic package not installed"
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        cache["ai_summary"]["error"] = "ANTHROPIC_API_KEY not set — add key to .env file"
        logger.warning("AI summary skipped: ANTHROPIC_API_KEY not set")
        return

    # Prune AI summaries from previous days before generating new ones
    _prune_old_summaries()

    # Determine current hour in ET
    now_et = datetime.now(ZoneInfo("America/New_York"))
    current_hour = now_et.hour

    # Quiet hours: 1 AM - 7 AM — do nothing (unless forced)
    if not force and current_hour in AI_SUMMARY_QUIET_HOURS:
        logger.info(f"AI summary: quiet hours ({current_hour}:00 ET), skipping")
        # Set an informational message so the UI explains the pause
        if not cache["ai_summary"].get("summaries"):
            cache["ai_summary"]["error"] = "Quiet hours (1\u20137 AM ET) \u2014 next update at 8 AM"
        return

    # Determine summary type
    if current_hour == AI_SUMMARY_MORNING_HOUR:
        _generate_morning_summary(api_key)
    elif force or current_hour in AI_SUMMARY_REGULAR_HOURS:
        _generate_regular_summary(api_key)
    else:
        logger.debug(f"AI summary: hour {current_hour} not on schedule, skipping")


# ============ MAIN UPDATE FUNCTION ============

def update_all_feeds() -> None:
    """Update all feeds concurrently - called by scheduler."""
    logger.info("=" * 50)
    logger.info("Starting feed update cycle")
    start = datetime.now()

    fetchers = {
        "twitter": fetch_twitter_accounts,
        "trump": fetch_trump,
        "reuters": fetch_reuters,
        "toi": fetch_toi,
        "think_tanks": fetch_think_tanks,
    }

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fn): name
            for name, fn in fetchers.items()
        }
        completed_names = set()
        try:
            for future in as_completed(futures, timeout=120):
                name = futures[future]
                completed_names.add(name)
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Fetcher {name} raised exception: {e}")
        except TimeoutError:
            timed_out = [name for f, name in futures.items() if name not in completed_names]
            logger.error(f"Feed update timed out after 120s. Timed-out fetchers: {', '.join(timed_out)}")
            # Cancel remaining futures (best-effort — running threads can't be interrupted)
            for f in futures:
                f.cancel()

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"Feed update cycle complete in {elapsed:.1f}s")

    # Persist cache to disk after every update cycle
    save_cache_to_disk()

    logger.info("=" * 50)


# ============ FLASK ROUTES ============

@app.route("/")
def dashboard():
    """Main dashboard page."""
    global _last_dashboard_view
    _last_dashboard_view = datetime.now()
    _prune_old_summaries()

    shabbos_times = None
    try:
        shabbos_times = get_shabbos_times()
    except Exception as e:
        logger.debug(f"Shabbos times computation failed: {e}")

    # Compute Yom Tov end display string
    yom_tov_end_display = None
    if YOM_TOV_END:
        try:
            yt_dt = datetime.fromisoformat(YOM_TOV_END)
            yom_tov_end_display = yt_dt.strftime("%a %-I:%M %p")
        except (ValueError, TypeError):
            yom_tov_end_display = YOM_TOV_END  # Fallback to raw string

    # Merge OSINT + Trump feeds into a single "Raw Feeds" list, sorted by timestamp
    raw_items = []
    for item in cache["twitter_list"]["items"][:10]:
        raw_items.append({**item, "feed_source": "osint"})
    for item in cache["trump"]["items"][:8]:
        raw_items.append({**item, "feed_source": "trump"})
    # Sort by timestamp descending (newest first) — ISO strings sort lexicographically
    raw_items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return render_template(
        "index.html",
        cache=cache,
        merged_raw_feeds=raw_items,
        generated_at=datetime.now(),
        refresh_interval=REFRESH_INTERVAL,
        shabbos_times=shabbos_times,
        ai_summary_enabled=ai_summary_enabled,
        has_anthropic=HAS_ANTHROPIC,
        has_api_key=bool(os.environ.get("ANTHROPIC_API_KEY")),
        yom_tov_end=YOM_TOV_END,
        yom_tov_end_display=yom_tov_end_display,
    )


@app.route("/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "feeds": {
            name: {
                "items_count": len(data["items"]),
                "last_updated": data["last_updated"].isoformat() if data["last_updated"] else None,
                "error": data["error"],
            }
            for name, data in cache.items()
        }
    }


@app.route("/refresh")
def manual_refresh():
    """Manually trigger a feed refresh."""
    update_all_feeds()
    return {"status": "refreshed", "time": datetime.now().isoformat()}


@app.route("/api/toggle-ai", methods=["POST"])
def toggle_ai():
    """Toggle AI summary on/off at runtime (no restart needed)."""
    global ai_summary_enabled, _last_dashboard_view
    ai_summary_enabled = not ai_summary_enabled
    if ai_summary_enabled:
        _last_dashboard_view = datetime.now()  # Reset inactivity timer on enable
    status = "enabled" if ai_summary_enabled else "disabled"
    logger.info(f"AI summary toggled: {status}")
    return jsonify({"ai_enabled": ai_summary_enabled, "status": status})


@app.route("/api/ai-status")
def ai_status():
    """Get current AI summary status for the dashboard toggle."""
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return jsonify({
        "ai_enabled": ai_summary_enabled,
        "has_anthropic": HAS_ANTHROPIC,
        "has_api_key": has_key,
        "last_updated": cache["ai_summary"]["last_updated"].isoformat() if cache["ai_summary"]["last_updated"] else None,
        "error": cache["ai_summary"]["error"],
        "item_count": len(cache["ai_summary"]["items"]),
    })


@app.route("/api/refresh-ai", methods=["POST"])
def refresh_ai():
    """Manually trigger an AI summary refresh (bypasses schedule)."""
    if not ai_summary_enabled:
        return jsonify({"error": "AI summary is disabled"}), 400
    fetch_ai_summary(force=True)
    return jsonify({
        "status": "refreshed",
        "item_count": len(cache["ai_summary"]["items"]),
        "error": cache["ai_summary"]["error"],
    })


# ============ MAIN ============

def _watchdog_loop():
    """Background watchdog that detects stale feeds and forces recovery.

    Runs every 2x the refresh interval. Checks EACH feed individually
    (not just the freshest one) so a single healthy feed can't mask
    dead ones. The ai_summary feed is excluded since it updates on
    a schedule, not every interval.
    """
    stale_threshold = REFRESH_INTERVAL * 3  # seconds
    WATCHDOG_EXCLUDED = {"ai_summary"}  # Schedule-based, not interval-based
    while True:
        time.sleep(REFRESH_INTERVAL * 2)
        try:
            now = datetime.now()
            stale_feeds = []
            any_updated = False

            for feed_name, data in cache.items():
                if feed_name in WATCHDOG_EXCLUDED:
                    continue
                lu = data["last_updated"]
                if lu is None:
                    stale_feeds.append(f"{feed_name}(never)")
                else:
                    age = (now - lu).total_seconds()
                    if age > stale_threshold:
                        stale_feeds.append(f"{feed_name}({age/60:.0f}m)")
                    else:
                        any_updated = True

            if stale_feeds:
                logger.error(
                    f"WATCHDOG: Stale feeds detected: {', '.join(stale_feeds)}. Forcing update."
                )
                update_all_feeds()
            elif not any_updated:
                logger.warning("WATCHDOG: No feeds have ever been updated, forcing fetch")
                update_all_feeds()
            else:
                logger.debug("WATCHDOG: All monitored feeds healthy")
        except Exception as e:
            logger.error(f"WATCHDOG: Error in watchdog loop: {e}")


if __name__ == "__main__":
    import socket
    import sys

    # Fail fast if port is already in use — prevents doomed instances from
    # wasting 30+ HTTP requests on update_all_feeds() before discovering
    # they can't bind the port (root cause of Shabbos #2 failure)
    _test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _test_sock.bind((HOST, PORT))
        _test_sock.close()
        logger.info(f"Port {PORT} is available")
    except OSError:
        logger.error(f"Port {PORT} already in use — exiting to avoid wasted API calls")
        _test_sock.close()
        sys.exit(1)

    # Load cached data from disk (instant dashboard on restart)
    if load_cache_from_disk():
        logger.info("Dashboard will show cached data while feeds refresh")

    # Setup scheduler for background updates
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        update_all_feeds,
        "interval",
        seconds=REFRESH_INTERVAL,
        id="feed_updater"
    )
    scheduler.start()

    # Start watchdog thread (detects stale feeds / dead scheduler)
    watchdog = threading.Thread(target=_watchdog_loop, daemon=True, name="watchdog")
    watchdog.start()
    logger.info("Watchdog thread started")

    # AI summary scheduler (always registered — respects runtime toggle)
    # The fetch_ai_summary() function itself checks ai_summary_enabled + API key
    if HAS_ANTHROPIC:
        scheduler.add_job(
            fetch_ai_summary,
            "cron",
            minute=5,
            id="ai_summary_updater",
            timezone="America/New_York",
        )
        logger.info("AI summary scheduler registered (hourly at :05, schedule-aware)")
        if os.environ.get("ANTHROPIC_API_KEY"):
            logger.info("AI summary ready: API key found")
        else:
            logger.info("AI summary: no API key yet (add to .env or toggle will prompt)")
    else:
        logger.info("AI summary unavailable: anthropic package not installed")

    # Initial fetch on startup
    logger.info("Performing initial feed fetch...")
    update_all_feeds()

    # AI summary starts OFF — no initial API call. User toggles on via dashboard.
    # (Previous behavior: auto-called on startup, wasting credits if nobody was watching)

    # AI status for startup message
    _ai_status = "off (toggle on dashboard)" if (HAS_ANTHROPIC and os.environ.get("ANTHROPIC_API_KEY")) else "no API key" if HAS_ANTHROPIC else "no package"

    # Print startup info
    print("\n" + "=" * 50)
    print("  SHABBOS SITUATION MONITOR")
    print("=" * 50)
    print(f"\n  Dashboard: http://localhost:{PORT}")
    print(f"  Refresh interval: {REFRESH_INTERVAL // 60} minutes")
    print(f"  AI summary: {_ai_status}")
    print(f"  Auto-restart: via start.sh")
    print(f"  Watchdog: active")
    print(f"\n  Press Ctrl+C to stop\n")
    print("=" * 50 + "\n")

    # Run Flask
    try:
        app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("\nServer stopped.")
