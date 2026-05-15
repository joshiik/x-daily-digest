"""X (Twitter) scraper using Playwright for JS-rendered content."""

import os
import random
import time
import json
from datetime import datetime
from urllib.parse import quote

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


class XScraper:
    """Scrapes trending topics and posts from X using a headless browser."""

    def __init__(self, auth_state_path=None):
        self.auth_state_path = auth_state_path
        self.posts = []

    def scrape(self) -> list[dict]:
        """Run the full scrape: trending topics + their top posts + For You feed."""
        proxy = os.environ.get("X_PROXY") or os.environ.get("HTTPS_PROXY") or ""

        with sync_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
            if proxy:
                launch_args.append(f"--proxy-server={proxy}")

            browser = p.chromium.launch(headless=True, args=launch_args)

            context_kwargs = {
                "viewport": {"width": 1280, "height": 800},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            }

            if self.auth_state_path and os.path.exists(self.auth_state_path):
                context = browser.new_context(
                    storage_state=self.auth_state_path, **context_kwargs
                )
                print(f"[scraper] Loaded auth state from {self.auth_state_path}")
            else:
                context = browser.new_context(**context_kwargs)
                print("[scraper] No auth state found — scraping public content only")

            page = context.new_page()

            # Block media & fonts for speed
            page.route(
                "**/*.{png,jpg,jpeg,gif,svg,mp4,webm,woff,woff2,ttf,otf,css}",
                lambda route: route.abort(),
            )

            try:
                # ── Trending topics ──
                trending_topics = self._scrape_trending(page)
                print(f"[scraper] Found {len(trending_topics)} trending topics")

                # Scrape top posts for each trending topic (limit to avoid rate-limit)
                for topic in trending_topics[:8]:
                    posts = self._scrape_topic_posts(page, topic)
                    self.posts.extend(posts)
                    delay = random.uniform(2.0, 4.0)
                    print(f"[scraper] Topic '{topic[:40]}': {len(posts)} posts, sleeping {delay:.1f}s")
                    time.sleep(delay)

                # ── For You feed ──
                fyp_posts = self._scrape_for_you(page)
                self.posts.extend(fyp_posts)
                print(f"[scraper] For You feed: {len(fyp_posts)} posts")
            finally:
                browser.close()

        return self.posts

    # ── private helpers ──

    def _scrape_trending(self, page) -> list[str]:
        """Return list of trending topic display-names."""
        page.goto("https://x.com/explore/tabs/trending", wait_until="domcontentloaded", timeout=30000)
        self._random_delay(2, 4)

        # Scroll to load more trends
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1)

        noise = {
            "·", "trending", "trending worldwide", "only on x · trending",
            "what's happening", "show more", "show less",
        }

        raw = []
        # Try [data-testid="trend"] first
        elements = page.query_selector_all('[data-testid="trend"]')
        if elements:
            for el in elements:
                text = el.inner_text().strip()
                if text:
                    raw.append(text)
        else:
            # Fallback: grab all spans with dir="ltr"
            for el in page.query_selector_all('div[dir="ltr"] span, span[dir="ltr"]'):
                text = el.inner_text().strip()
                if text and len(text) > 2:
                    raw.append(text)

        # Clean each raw trend text: extract just the topic name
        topics = []
        for text in raw:
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            # Keep lines that are NOT metadata noise
            clean = [
                l for l in lines
                if l.lower() not in noise
                and not l.isdigit()
                and not l.lower().startswith("trending")
                and l not in ("·", "•")
            ]
            if clean:
                # The topic is usually the longest remaining line
                topic = max(clean, key=len)
                topics.append(topic)

        # Deduplicate preserving order
        seen = set()
        unique = []
        for t in topics:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique.append(t)

        return unique[:10]

    def _scrape_topic_posts(self, page, topic: str) -> list[dict]:
        """Search a trending topic and scrape its top tweets."""
        search_url = f"https://x.com/search?q={quote(topic)}&src=trend_click&f=top"
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        except PlaywrightTimeout:
            print(f"[scraper] Timeout loading search for '{topic[:40]}'")
            return []
        self._random_delay(2, 3)

        # Scroll to load tweets
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 1000)")
            time.sleep(random.uniform(1, 2))

        return self._extract_tweets(page, is_trending=True)

    def _scrape_for_you(self, page) -> list[dict]:
        """Scrape the home timeline 'For You' feed."""
        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        except PlaywrightTimeout:
            print("[scraper] Timeout loading home timeline")
            return []
        self._random_delay(2, 3)

        for _ in range(4):
            page.evaluate("window.scrollBy(0, 1200)")
            time.sleep(random.uniform(1, 2))

        return self._extract_tweets(page, is_trending=False)

    def _extract_tweets(self, page, is_trending: bool = False) -> list[dict]:
        """Parse visible tweet elements on the current page."""
        tweets = []

        # Primary selector: X uses <article data-testid="tweet">
        articles = page.query_selector_all('article[data-testid="tweet"]')
        if not articles:
            # Fallback: any <article>
            articles = page.query_selector_all("article")

        for article in articles[:15]:
            try:
                data = self._parse_article(article, is_trending)
                if data and data.get("text"):
                    tweets.append(data)
            except Exception as exc:
                print(f"[scraper] Failed to parse a tweet: {exc}")
                continue

        return tweets

    def _parse_article(self, article, is_trending: bool) -> dict | None:
        """Extract fields from a single <article> element."""
        # --- text ---
        text = ""
        for sel in ['[data-testid="tweetText"]', "div[lang]"]:
            el = article.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                break

        if not text:
            return None

        # --- url & handle ---
        tweet_url = ""
        handle = ""
        for link in article.query_selector_all("a"):
            href = link.get_attribute("href") or ""
            if "/status/" in href and not tweet_url:
                tweet_url = f"https://x.com{href.split('?')[0]}"
                parts = href.strip("/").split("/")
                if parts:
                    handle = parts[0]
            if tweet_url:
                break

        # --- author display name ---
        author = ""
        name_el = article.query_selector('[data-testid="User-Name"]')
        if name_el:
            full = name_el.inner_text()
            author = full.split("@")[0].strip()

        # --- metrics ---
        likes = self._parse_metric(article, "like")
        retweets = self._parse_metric(article, "retweet")
        replies = self._parse_metric(article, "reply")

        # --- timestamp ---
        timestamp = ""
        time_el = article.query_selector("time")
        if time_el:
            timestamp = time_el.get_attribute("datetime") or ""

        return {
            "text": text,
            "author": author,
            "handle": handle.lstrip("@"),
            "url": tweet_url,
            "likes": likes,
            "retweets": retweets,
            "replies": replies,
            "timestamp": timestamp,
            "is_trending": is_trending,
        }

    def _parse_metric(self, article, name: str) -> int:
        """Parse an engagement metric (like / retweet / reply count)."""
        try:
            el = article.query_selector(f'[data-testid="{name}"]')
            if el:
                return self._parse_count(el.inner_text())
        except Exception:
            pass
        return 0

    @staticmethod
    def _parse_count(raw: str) -> int:
        """Convert '12.3K' / '1.2M' / '456' to int."""
        text = raw.strip().lower().replace(",", "")
        if not text:
            return 0
        if text.endswith("k"):
            try:
                return int(float(text[:-1]) * 1_000)
            except ValueError:
                return 0
        if text.endswith("m"):
            try:
                return int(float(text[:-1]) * 1_000_000)
            except ValueError:
                return 0
        try:
            return int(text)
        except ValueError:
            return 0

    @staticmethod
    def _random_delay(low: float, high: float):
        time.sleep(random.uniform(low, high))
