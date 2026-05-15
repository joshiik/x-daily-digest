"""One-time helper: open a browser, log into X, and save the auth state.

Usage:
    python save_auth.py

    # With proxy (e.g. Clash):
    $env:X_PROXY="http://127.0.0.1:7890"; python save_auth.py

A browser window opens to x.com/login. Log in, then create a file called
"done.txt" in this directory (or type "done" in any way you can signal).
The script detects the file and saves the auth state.

Then base64-encode it for GitHub Secrets (PowerShell):
    [Convert]::ToBase64String([IO.File]::ReadAllBytes("auth.json")) | Set-Content auth.json.b64 -Encoding ASCII
"""

import os
import sys
import time

SIGNAL_FILE = "done.txt"


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Please install: pip install playwright && playwright install chromium")
        sys.exit(1)

    output_path = os.environ.get("AUTH_OUTPUT", "auth.json")
    proxy = os.environ.get("X_PROXY") or os.environ.get("HTTPS_PROXY") or ""

    # Clean up signal file from previous run
    if os.path.exists(SIGNAL_FILE):
        os.remove(SIGNAL_FILE)

    with sync_playwright() as p:
        launch_args = ["--disable-blink-features=AutomationControlled"]
        if proxy:
            launch_args.append(f"--proxy-server={proxy}")
            print(f"[save_auth] Using proxy: {proxy}")

        browser = p.chromium.launch(headless=False, args=launch_args)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto("https://x.com/login", wait_until="load", timeout=60000)
        # Give JavaScript time to render the login form
        time.sleep(5)
        print(f"[save_auth] Page title: '{page.title()}'")

        print()
        print("=" * 55)
        print("  Browser opened → x.com/login")
        print("  Log in manually in the browser window.")
        print()
        print(f"  When done, I will create '{SIGNAL_FILE}' for you.")
        print("  Just tell me 'done' in the chat.")
        print("=" * 55)
        print()
        print("[save_auth] Waiting for signal file...")

        # Poll for signal file (check every 2 seconds, max 5 minutes)
        for _ in range(150):
            if os.path.exists(SIGNAL_FILE):
                print("[save_auth] Signal file detected — saving auth state...")
                break
            time.sleep(2)
        else:
            print("[save_auth] Timed out waiting — saving whatever state we have...")

        context.storage_state(path=output_path)
        browser.close()

    # Clean up
    if os.path.exists(SIGNAL_FILE):
        os.remove(SIGNAL_FILE)

    file_size = os.path.getsize(output_path)
    print(f"\nAuth state saved → {output_path} ({file_size} bytes)")
    print()
    print("Next steps:")
    print("  1. Base64-encode it for GitHub Actions:")
    print("     [Convert]::ToBase64String([IO.File]::ReadAllBytes('auth.json')) | Set-Content auth.json.b64 -Encoding ASCII")
    print("  2. Add as GitHub Secret: X_AUTH_STATE_B64")
    print("  3. Also add secrets: GMAIL_USER, GMAIL_APP_PASSWORD")


if __name__ == "__main__":
    main()
