"""X (Twitter) scraper using Playwright for JS-rendered content."""

import os
import random
import time
from urllib.parse import quote

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# AI coding / dev tools keywords to search daily
AI_KEYWORDS = [
    "AI coding assistant",
    "AI developer tools",
    "Claude Code",
    "GitHub Copilot",
    "Cursor IDE",
    "AI agent development",
    "LLM prompt engineering",
    "AI code generation",
    "Vibe coding",
    "AI programming",
]


class XScraper:
    """Scrapes X for AI coding / dev tool posts via keyword search."""

    def __init__(self, auth_state_path=None):
        self.auth_state_path = auth_state_path
        self.posts = []

    def scrape(self) -> list[dict]:
        """Search AI keywords on X, grab top + latest posts from each."""
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
                for kw in AI_KEYWORDS:
                    # Search "top" (popular posts)
                    top_posts = self._search(page, kw, sort="top")
                    self.posts.extend(top_posts)

                    # Search "latest" (fresh posts)
                    latest_posts = self._search(page, kw, sort="latest")
                    self.posts.extend(latest_posts)

                    delay = random.uniform(1.5, 3.0)
                    total = len(top_posts) + len(latest_posts)
                    print(f"[scraper] '{kw}': {total} posts, sleeping {delay:.1f}s")
                    time.sleep(delay)
            finally:
                browser.close()

        return self.posts

    # ── private helpers ──

    def _search(self, page, keyword: str, sort: str = "top") -> list[dict]:
        """Search X for a keyword, return parsed tweets."""
        f_param = "top" if sort == "top" else "live"
        search_url = f"https://x.com/search?q={quote(keyword)}&src=typed_query&f={f_param}"

        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        except PlaywrightTimeout:
            print(f"[scraper] Timeout loading search for '{keyword}'")
            return []
        self._random_delay(2, 3)

        # Scroll to load tweets
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 1000)")
            time.sleep(random.uniform(1, 2))

        return self._extract_tweets(page, keyword=keyword, sort=sort)

    def _extract_tweets(self, page, keyword: str = "", sort: str = "top") -> list[dict]:
        """Parse visible tweet elements on the current page."""
        tweets = []

        articles = page.query_selector_all('article[data-testid="tweet"]')
        if not articles:
            articles = page.query_selector_all("article")

        for article in articles[:10]:
            try:
                data = self._parse_article(article, keyword=keyword, sort=sort)
                if data and data.get("text"):
                    tweets.append(data)
            except Exception as exc:
                print(f"[scraper] Failed to parse a tweet: {exc}")
                continue

        return tweets

    def _parse_article(self, article, keyword: str = "", sort: str = "top") -> dict | None:
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
            "keyword": keyword,
            "sort": sort,
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
