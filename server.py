"""
Shabbos Situation Monitor - Main Server

A local server that fetches news from multiple sources and serves
an auto-refreshing dashboard for hands-free monitoring.

Run with: python server.py
Or use: ./start.sh
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from html import unescape
import re

from flask import Flask, render_template
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import feedparser
from bs4 import BeautifulSoup

from config import (
    HOST, PORT, DEBUG, REFRESH_INTERVAL,
    TWITTER_ACCOUNTS, TRUMP_TRUTH_RSS, TRUMP_TWITTER_MIRROR,
    REUTERS_MIDEAST_RSS,
    NITTER_INSTANCES, TOI_RSS_URL, TOI_LIVEBLOG_URL,
    POLYMARKET_EVENT_SLUG, POLYMARKET_API_URL,
    MAX_ITEMS_PER_FEED, REQUEST_TIMEOUT
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

    for username in TWITTER_ACCOUNTS:
        items = fetch_single_twitter_account(username)
        all_items.extend(items)

    if all_items:
        # Sort by timestamp (most recent first) and limit
        all_items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        cache["twitter_list"] = {
            "items": all_items[:MAX_ITEMS_PER_FEED],
            "last_updated": datetime.now(),
            "error": None,
        }
        logger.info(f"Got {len(all_items)} total items from Twitter accounts")
    elif not cache["twitter_list"]["items"]:
        cache["twitter_list"]["error"] = "Could not fetch any Twitter accounts"
        logger.warning("All Twitter account fetches failed")


def fetch_single_twitter_account(username: str) -> List[Dict]:
    """Fetch tweets from a single Twitter account by scraping the page."""
    logger.info(f"Fetching @{username}...")

    # Try direct Twitter page scraping
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

    # Fallback: Try Nitter instances
    for instance in NITTER_INSTANCES[:2]:  # Only try first 2 to save time
        try:
            nitter_url = f"https://{instance}/{username}"
            response = safe_request(nitter_url)
            if response:
                items = parse_nitter_profile(response.text, username)
                if items:
                    logger.info(f"Got {len(items)} tweets from @{username} via Nitter")
                    return items
        except Exception as e:
            logger.debug(f"Nitter {instance} failed for @{username}: {e}")
            continue

    logger.warning(f"All methods failed for @{username}")
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
    for instance in NITTER_INSTANCES:
        url = f"https://{instance}/{TRUMP_TWITTER_MIRROR}/rss"
        response = safe_request(url)
        if response:
            feed = feedparser.parse(response.content)
            if feed.entries:
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
    """Fetch Polymarket prediction market odds."""
    logger.info("Fetching Polymarket odds...")

    url = f"{POLYMARKET_API_URL}?slug={POLYMARKET_EVENT_SLUG}"
    response = safe_request(url)

    if response:
        try:
            data = response.json()
            if data and len(data) > 0:
                event = data[0]
                markets = event.get("markets", [])

                items = []
                for market in markets:
                    question = market.get("question", "")
                    # Extract short title from groupItemTitle or question
                    title = market.get("groupItemTitle", "")
                    if not title:
                        title = question[:50]

                    # Parse outcome prices - format is '["0.17", "0.88"]' for [Yes, No]
                    prices_str = market.get("outcomePrices", "[]")
                    try:
                        prices = eval(prices_str)  # Safe here as it's from API
                        yes_price = float(prices[0]) if prices else 0
                        probability = int(yes_price * 100)
                    except:
                        probability = 0

                    items.append({
                        "title": title,
                        "question": question,
                        "probability": probability,
                        "volume": market.get("volumeNum", 0),
                        "link": f"https://polymarket.com/event/{POLYMARKET_EVENT_SLUG}",
                    })

                cache["polymarket"] = {
                    "items": items,
                    "last_updated": datetime.now(),
                    "error": None,
                    "event_title": event.get("title", "Iran Strike Markets"),
                }
                logger.info(f"Got {len(items)} Polymarket markets")
                return
        except Exception as e:
            logger.warning(f"Error parsing Polymarket data: {e}")

    # Failed
    if not cache["polymarket"]["items"]:
        cache["polymarket"]["error"] = "Could not fetch Polymarket data"
    logger.warning("Failed to fetch Polymarket")


# ============ MAIN UPDATE FUNCTION ============

def update_all_feeds() -> None:
    """Update all feeds - called by scheduler."""
    logger.info("=" * 50)
    logger.info("Starting feed update cycle")
    logger.info("=" * 50)

    # Run fetchers (they handle their own errors)
    fetch_twitter_accounts()
    fetch_trump()
    fetch_reuters()
    fetch_toi()
    fetch_polymarket()

    logger.info("Feed update cycle complete")
    logger.info("=" * 50)


# ============ FLASK ROUTES ============

@app.route("/")
def dashboard():
    """Main dashboard page."""
    return render_template(
        "index.html",
        cache=cache,
        generated_at=datetime.now(),
        refresh_interval=REFRESH_INTERVAL,
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

if __name__ == "__main__":
    # Setup scheduler for background updates
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        update_all_feeds,
        "interval",
        seconds=REFRESH_INTERVAL,
        id="feed_updater"
    )
    scheduler.start()

    # Initial fetch on startup
    logger.info("Performing initial feed fetch...")
    update_all_feeds()

    # Print startup info
    print("\n" + "=" * 50)
    print("  SHABBOS SITUATION MONITOR")
    print("=" * 50)
    print(f"\n  Dashboard: http://localhost:{PORT}")
    print(f"  Refresh interval: {REFRESH_INTERVAL // 60} minutes")
    print(f"\n  Press Ctrl+C to stop\n")
    print("=" * 50 + "\n")

    # Run Flask
    try:
        app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("\nServer stopped.")
