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
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Optional
from html import unescape
from zoneinfo import ZoneInfo
import re

from astral import LocationInfo
from astral.sun import sun

from flask import Flask, render_template
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import feedparser
from bs4 import BeautifulSoup

from config import (
    HOST, PORT, DEBUG, REFRESH_INTERVAL,
    TWITTER_ACCOUNTS, TRUMP_TRUTH_RSS, TRUMP_TWITTER_MIRROR,
    REUTERS_MIDEAST_RSS,
    NITTER_INSTANCES, NITTER_TIMEOUT, TOI_RSS_URL, TOI_LIVEBLOG_URL,
    POLYMARKET_EVENT_SLUG, POLYMARKET_API_URL,
    MAX_ITEMS_PER_FEED, REQUEST_TIMEOUT,
    LOCATION_LAT, LOCATION_LON, LOCATION_TZ,
    CANDLE_LIGHTING_OFFSET, HAVDALAH_OFFSET, SHABBOS_SNAPSHOT_FILE,
    CACHE_FILE, CACHE_MAX_AGE,
)

# Setup logging with rotation
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_log_fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)
logger.addHandler(_console_handler)

_file_handler = RotatingFileHandler(
    'server.log', maxBytes=5 * 1024 * 1024, backupCount=3
)
_file_handler.setFormatter(_log_fmt)
logger.addHandler(_file_handler)

# Flask app
app = Flask(__name__)

# Global cache for all feeds
cache: Dict = {
    "twitter_list": {"items": [], "last_updated": None, "error": None},
    "trump": {"items": [], "last_updated": None, "error": None},
    "reuters": {"items": [], "last_updated": None, "error": None},
    "toi_liveblog": {"items": [], "last_updated": None, "error": None},
    "polymarket": {"items": [], "last_updated": None, "error": None},
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
            serializable[feed_name] = {
                "items": feed_data["items"],
                "last_updated": feed_data["last_updated"].isoformat() if feed_data["last_updated"] else None,
                "error": feed_data["error"],
            }
        # Atomic write: write to temp file in same directory, then rename
        dir_name = os.path.dirname(os.path.abspath(CACHE_FILE))
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"saved_at": datetime.now().isoformat(), "feeds": serializable}, f)
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
                loaded_count += 1
        logger.info(f"Loaded {loaded_count} feeds from disk cache ({age/60:.1f}m old)")
        return loaded_count > 0
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError) as e:
        logger.debug(f"Could not load cache from disk: {e}")
        return False


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


def save_shabbos_snapshot(probability: int, market_title: str) -> None:
    """Persist the soonest market's probability at candle lighting."""
    times = get_shabbos_times()
    snapshot = {
        "shabbos_friday": times["friday_date"].isoformat(),
        "probability": probability,
        "market_title": market_title,
        "candle_lighting": times["candle_lighting"].isoformat(),
    }
    try:
        with open(SHABBOS_SNAPSHOT_FILE, "w") as f:
            json.dump(snapshot, f)
        logger.info(f"Shabbos snapshot saved: {market_title} at {probability}%")
    except Exception as e:
        logger.warning(f"Failed to save Shabbos snapshot: {e}")


def load_shabbos_snapshot() -> Optional[Dict]:
    """Load the saved snapshot if it belongs to the current Shabbos."""
    try:
        with open(SHABBOS_SNAPSHOT_FILE) as f:
            data = json.load(f)
        times = get_shabbos_times()
        if data.get("shabbos_friday") == times["friday_date"].isoformat():
            return data
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def clear_expired_snapshot() -> None:
    """Remove the snapshot file after Shabbos ends."""
    try:
        if os.path.exists(SHABBOS_SNAPSHOT_FILE):
            os.remove(SHABBOS_SNAPSHOT_FILE)
            logger.info("Cleared expired Shabbos snapshot")
    except Exception as e:
        logger.warning(f"Failed to clear Shabbos snapshot: {e}")


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

def format_timestamp(timestamp_str: str) -> str:
    """Convert various timestamp formats to readable display."""
    if not timestamp_str:
        return ""
    try:
        # Try parsing ISO format
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%H:%M')
    except:
        try:
            # Try RSS format
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(timestamp_str)
            return dt.strftime('%H:%M')
        except:
            return timestamp_str[:16] if timestamp_str else ""


def clean_html(html_text: str) -> str:
    """Remove HTML tags and decode entities."""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return unescape(text)


def safe_request(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[requests.Response]:
    """Make a request with error handling."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        return response
    except Exception as e:
        logger.warning(f"Request failed for {url}: {e}")
        return None


# ============ TWITTER ACCOUNTS FETCHER ============

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
        for future in as_completed(futures, timeout=90):
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
        }
        logger.info(f"Got {len(all_items)} total items from Twitter accounts")
    else:
        cache["twitter_list"]["account_status"] = account_status
        if not cache["twitter_list"]["items"]:
            cache["twitter_list"]["error"] = "Could not fetch any Twitter accounts"
        logger.warning("All Twitter account fetches failed")


def fetch_single_twitter_account(username: str) -> List[Dict]:
    """Fetch tweets from a single Twitter account via multiple fallback methods."""
    logger.info(f"Fetching @{username}...")

    # Method 1: Twitter syndication API
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers)
        if response.status_code == 200:
            items = parse_twitter_syndication(response.text, username)
            if items:
                logger.info(f"Got {len(items)} tweets from @{username} via syndication")
                return items
    except Exception as e:
        logger.warning(f"Syndication fetch failed for @{username}: {e}")

    # Method 2: Nitter RSS (more reliable parsing than HTML scraping)
    items = fetch_twitter_via_nitter_rss(username)
    if items:
        logger.info(f"Got {len(items)} tweets from @{username} via Nitter RSS")
        return items

    # Method 3: Nitter HTML scraping (last resort)
    for instance in get_healthy_nitter_instances()[:4]:
        try:
            nitter_url = f"https://{instance}/{username}"
            response = safe_request(nitter_url, timeout=NITTER_TIMEOUT)
            if response:
                items = parse_nitter_profile(response.text, username)
                if items:
                    record_nitter_success(instance)
                    logger.info(f"Got {len(items)} tweets from @{username} via {instance}")
                    return items
            record_nitter_failure(instance)
        except Exception as e:
            record_nitter_failure(instance)
            logger.debug(f"Nitter {instance} failed for @{username}: {e}")
            continue

    logger.warning(f"All methods failed for @{username}")
    return []


def fetch_twitter_via_nitter_rss(username: str) -> List[Dict]:
    """Try fetching tweets via Nitter RSS feeds (more reliable than HTML scraping)."""
    for instance in get_healthy_nitter_instances()[:3]:
        try:
            rss_url = f"https://{instance}/{username}/rss"
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
                            "text": clean_html(entry.get("title", "") or entry.get("description", ""))[:300],
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
                    "text": text_elem.get_text(strip=True)[:300],
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
    logger.info("Fetching Trump Truth Social...")

    # Primary: trumpstruth.org RSS feed
    response = safe_request(TRUMP_TRUTH_RSS)
    if response:
        feed = feedparser.parse(response.content)
        if feed.entries:
            items = []
            for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
                # Get content - try multiple fields
                content = entry.get("summary", "") or entry.get("description", "") or entry.get("title", "")

                items.append({
                    "author": "realDonaldTrump",
                    "text": clean_html(content)[:400],
                    "timestamp": entry.get("published", ""),
                    "timestamp_display": format_timestamp(entry.get("published", "")),
                    "link": entry.get("link", ""),
                })

            cache["trump"] = {
                "items": items,
                "last_updated": datetime.now(),
                "error": None,
            }
            logger.info(f"Got {len(items)} Trump posts from Truth Social RSS")
            return

    # Fallback: Try Twitter mirror account via Nitter
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
                    items.append({
                        "author": "TrumpDailyPosts",
                        "text": clean_html(title)[:400],
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
    """Fetch Reuters Middle East news via RSS."""
    logger.info("Fetching Reuters Middle East...")

    response = safe_request(REUTERS_MIDEAST_RSS)
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

            cache["reuters"] = {
                "items": items,
                "last_updated": datetime.now(),
                "error": None,
            }
            logger.info(f"Got {len(items)} items from Reuters Middle East")
            return

    # Failed
    if not cache["reuters"]["items"]:
        cache["reuters"]["error"] = "Could not fetch Reuters feed"
    logger.warning("Failed to fetch Reuters Middle East")


# ============ TIMES OF ISRAEL FETCHER ============

def fetch_toi() -> None:
    """Fetch Times of Israel from RSS and liveblog."""
    logger.info("Fetching Times of Israel...")
    items = []

    # Fetch RSS feed
    response = safe_request(TOI_RSS_URL)
    if response:
        feed = feedparser.parse(response.content)

        for entry in feed.entries[:10]:
            items.append({
                "title": entry.get("title", ""),
                "summary": clean_html(entry.get("summary", ""))[:200],
                "timestamp": entry.get("published", ""),
                "timestamp_display": format_timestamp(entry.get("published", "")),
                "link": entry.get("link", ""),
                "source": "rss",
            })
        logger.info(f"Got {len(items)} items from TOI RSS")

    # Try to fetch liveblog
    response = safe_request(TOI_LIVEBLOG_URL)
    if response:
        soup = BeautifulSoup(response.content, "html.parser")
        liveblog_items = parse_toi_liveblog(soup)

        if liveblog_items:
            # Prepend liveblog items (most recent)
            items = liveblog_items + items
            logger.info(f"Got {len(liveblog_items)} liveblog items from TOI")

    # Update cache
    if items:
        cache["toi_liveblog"] = {
            "items": items[:MAX_ITEMS_PER_FEED],
            "last_updated": datetime.now(),
            "error": None,
        }
    elif not cache["toi_liveblog"]["items"]:
        cache["toi_liveblog"]["error"] = "Could not fetch TOI content"


def parse_toi_liveblog(soup) -> List[Dict]:
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
    ]

    entries = []
    for selector in selectors:
        entries = soup.select(selector)
        if entries:
            break

    for entry in entries[:10]:
        try:
            time_elem = entry.select_one("time, .timestamp, .time, .lb-time, .entry-time")
            content_elem = entry.select_one(".content, .entry-content, p, .lb-content, .entry-text")
            title_elem = entry.select_one("h2, h3, .entry-title, .headline")

            if content_elem or title_elem:
                items.append({
                    "title": title_elem.get_text(strip=True) if title_elem else "",
                    "summary": content_elem.get_text(strip=True)[:250] if content_elem else "",
                    "timestamp": time_elem.get("datetime", "") if time_elem else "",
                    "timestamp_display": time_elem.get_text(strip=True) if time_elem else "LIVE",
                    "link": TOI_LIVEBLOG_URL,
                    "source": "liveblog",
                })
        except Exception as e:
            logger.debug(f"Error parsing liveblog entry: {e}")
            continue

    return items


# ============ POLYMARKET FETCHER ============

def fetch_polymarket() -> None:
    """Fetch Polymarket odds: Iran strike event (soonest deadline) + top trending market."""
    logger.info("Fetching Polymarket odds...")

    all_items = []

    # === Primary: US/Israel strikes Iran event (auto-soonest deadline) ===
    url = f"{POLYMARKET_API_URL}?slug={POLYMARKET_EVENT_SLUG}"
    response = safe_request(url)
    if response:
        try:
            data = response.json()
            if data and len(data) > 0:
                event = data[0]
                markets = event.get("markets", [])

                dated_markets = []
                for market in markets:
                    # Skip closed/resolved markets
                    if market.get("closed"):
                        continue

                    prices_str = market.get("outcomePrices", "[]")
                    try:
                        prices = json.loads(prices_str)
                        yes_price = float(prices[0]) if prices else 0
                        probability = int(yes_price * 100)
                    except (json.JSONDecodeError, IndexError, ValueError):
                        probability = 0

                    if probability == 0 or probability == 100:
                        continue

                    title = market.get("groupItemTitle", "")
                    question = market.get("question", "")

                    # Parse date from groupItemTitle (e.g. "February 28")
                    try:
                        parsed = datetime.strptime(title, "%B %d")
                        deadline = parsed.replace(year=datetime.now().year)
                    except ValueError:
                        deadline = datetime.max  # Unknown dates sort last

                    dated_markets.append({
                        "title": title,
                        "question": question,
                        "probability": probability,
                        "volume": market.get("volumeNum", 0),
                        "link": f"https://polymarket.com/event/{POLYMARKET_EVENT_SLUG}",
                        "_deadline": deadline,
                    })

                # Sort by deadline (soonest first)
                dated_markets.sort(key=lambda x: x["_deadline"])

                for m in dated_markets:
                    del m["_deadline"]

                all_items.extend(dated_markets)
                logger.info(f"Got {len(dated_markets)} active markets from {POLYMARKET_EVENT_SLUG}")

                # --- Shabbos snapshot logic ---
                if dated_markets:
                    try:
                        soonest = dated_markets[0]
                        times = get_shabbos_times()
                        now = datetime.now(_tz)

                        if now >= times["candle_lighting"] and now <= times["havdalah"]:
                            # We're in (or past) candle lighting - save snapshot if needed
                            existing = load_shabbos_snapshot()
                            if not existing:
                                save_shabbos_snapshot(soonest["probability"], soonest["title"])
                        elif now > times["havdalah"]:
                            clear_expired_snapshot()
                    except Exception as e:
                        logger.debug(f"Shabbos snapshot check failed: {e}")

        except Exception as e:
            logger.warning(f"Error parsing Polymarket event data: {e}")

    # === Secondary: Top trending market on Polymarket (by 24h volume) ===
    trending_url = f"{POLYMARKET_API_URL}?active=true&closed=false&order=volume24hr&ascending=false&limit=10"
    response = safe_request(trending_url)
    if response:
        try:
            data = response.json()
            if data:
                for event in data:
                    slug = event.get("slug", "")
                    if "strikes-iran" in slug or slug == POLYMARKET_EVENT_SLUG:
                        continue

                    title = event.get("title", "")
                    markets = event.get("markets", [])
                    if not markets:
                        continue

                    # Find highest-volume active sub-market
                    best_market = None
                    best_vol = 0
                    for market in markets:
                        if market.get("closed"):
                            continue
                        prices_str = market.get("outcomePrices", "[]")
                        try:
                            prices = json.loads(prices_str)
                            yes_price = float(prices[0]) if prices else 0
                            prob = int(yes_price * 100)
                        except (json.JSONDecodeError, IndexError, ValueError):
                            prob = 0
                        if 0 < prob < 100:
                            vol = market.get("volumeNum", 0)
                            if vol > best_vol:
                                best_market = (market, prob)
                                best_vol = vol

                    if not best_market:
                        continue

                    market, probability = best_market
                    all_items.append({
                        "title": f"TRENDING: {title}",
                        "question": market.get("question", title),
                        "probability": probability,
                        "volume": market.get("volumeNum", 0),
                        "link": f"https://polymarket.com/event/{slug}",
                        "is_trending": True,
                    })
                    logger.info(f"Got trending market: {title}")
                    break  # Only take the #1 trending market
        except Exception as e:
            logger.warning(f"Error fetching trending Polymarket data: {e}")

    if all_items:
        cache["polymarket"] = {
            "items": all_items,
            "last_updated": datetime.now(),
            "error": None,
            "event_title": "Iran Strike Markets",
        }
        logger.info(f"Got {len(all_items)} total Polymarket markets")
    elif not cache["polymarket"]["items"]:
        cache["polymarket"]["error"] = "Could not fetch Polymarket data"
        logger.warning("Failed to fetch Polymarket")


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
        "polymarket": fetch_polymarket,
    }

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fn): name
            for name, fn in fetchers.items()
        }
        for future in as_completed(futures, timeout=120):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Fetcher {name} raised exception: {e}")

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"Feed update cycle complete in {elapsed:.1f}s")

    # Persist cache to disk after every update cycle
    save_cache_to_disk()

    logger.info("=" * 50)


# ============ FLASK ROUTES ============

@app.route("/")
def dashboard():
    """Main dashboard page."""
    # Compute Shabbos delta for soonest market
    shabbos_delta = None
    shabbos_times = None
    try:
        shabbos_times = get_shabbos_times()
        snapshot = load_shabbos_snapshot()
        if snapshot and cache["polymarket"]["items"]:
            # Find the soonest non-trending market
            for item in cache["polymarket"]["items"]:
                if not item.get("is_trending"):
                    shabbos_delta = {
                        "current": item["probability"],
                        "at_start": snapshot["probability"],
                        "delta": item["probability"] - snapshot["probability"],
                        "market_title": snapshot["market_title"],
                    }
                    break
    except Exception as e:
        logger.debug(f"Shabbos delta computation failed: {e}")

    return render_template(
        "index.html",
        cache=cache,
        generated_at=datetime.now(),
        refresh_interval=REFRESH_INTERVAL,
        shabbos_delta=shabbos_delta,
        shabbos_times=shabbos_times,
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


# ============ MAIN ============

def _watchdog_loop():
    """Background watchdog that detects stale feeds and forces recovery.

    Runs every 2x the refresh interval. If no feed has been updated in
    3x the refresh interval, it means the scheduler has silently died —
    so the watchdog forces a manual update cycle.
    """
    stale_threshold = REFRESH_INTERVAL * 3  # seconds
    while True:
        time.sleep(REFRESH_INTERVAL * 2)
        try:
            now = datetime.now()
            timestamps = [
                data["last_updated"]
                for data in cache.values()
                if data["last_updated"]
            ]
            if not timestamps:
                logger.warning("WATCHDOG: No feeds have ever been updated, forcing fetch")
                update_all_feeds()
                continue
            newest = max(timestamps)
            age = (now - newest).total_seconds()
            if age > stale_threshold:
                logger.error(
                    f"WATCHDOG: Feeds are {age/60:.0f}m stale "
                    f"(threshold: {stale_threshold/60:.0f}m). Forcing update."
                )
                update_all_feeds()
            else:
                logger.debug(f"WATCHDOG: Feeds healthy, newest is {age/60:.1f}m old")
        except Exception as e:
            logger.error(f"WATCHDOG: Error in watchdog loop: {e}")


if __name__ == "__main__":
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

    # Initial fetch on startup
    logger.info("Performing initial feed fetch...")
    update_all_feeds()

    # Print startup info
    print("\n" + "=" * 50)
    print("  SHABBOS SITUATION MONITOR")
    print("=" * 50)
    print(f"\n  Dashboard: http://localhost:{PORT}")
    print(f"  Refresh interval: {REFRESH_INTERVAL // 60} minutes")
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
