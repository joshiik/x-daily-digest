"""Entry point: scrape X, format digest, and send email."""

import argparse
import os
import sys
import tempfile

from x_daily.scraper import XScraper
from x_daily.digest import build_digest
from x_daily.emailer import send_email


def main():
    parser = argparse.ArgumentParser(description="X Daily Digest")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest to stdout instead of sending email",
    )
    parser.add_argument(
        "--auth-state",
        default=os.environ.get("X_AUTH_STATE_PATH", "auth.json"),
        help="Path to Playwright auth state JSON (default: auth.json)",
    )
    parser.add_argument(
        "--to",
        default=os.environ.get("GMAIL_USER", ""),
        help="Recipient email address (default: same as GMAIL_USER)",
    )
    args = parser.parse_args()

    # ── 1. Scrape ──
    print("=" * 50)
    print("[main] Starting X scrape...")
    scraper = XScraper(auth_state_path=args.auth_state)
    posts = scraper.scrape()
    print(f"[main] Scraped {len(posts)} total posts")

    # ── 2. Build digest ──
    html = build_digest(posts, max_posts=10)

    if args.dry_run:
        print("=" * 50)
        print("[main] DRY RUN — printing digest to stdout:")
        print("=" * 50)
        # Strip HTML tags for terminal readability (rough)
        import re
        plain = re.sub(r"<[^>]+>", "", html)
        plain = re.sub(r"\n\s*\n", "\n\n", plain)
        print(plain)
        print("=" * 50)
        print(f"[main] Would have sent to: {args.to or '(set GMAIL_USER)'}")
        return

    # ── 3. Send email ──
    print("=" * 50)
    from datetime import datetime, timezone

    subject = f"X Daily Digest — {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')}"
    success = send_email(html, subject, args.to or "")
    if not success:
        print("[main] Email send FAILED — check credentials", file=sys.stderr)
        sys.exit(1)

    print("[main] Done.")


if __name__ == "__main__":
    main()
