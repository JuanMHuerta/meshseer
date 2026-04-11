"""Headless browser screenshot validation for meshradar UI."""
from playwright.sync_api import sync_playwright
import os

BASE_URL = "http://127.0.0.1:8765"
OUT_DIR = "screenshots"
os.makedirs(OUT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()

    # ── Desktop 1440×900 ──────────────────────────────────────────────────────
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)

    # 01: initial state
    page.screenshot(path=f"{OUT_DIR}/01-desktop-initial.png")
    print("01-desktop-initial.png")

    # 02: drawer closed
    page.click("#toggle-nodes-drawer")
    page.wait_for_timeout(400)
    page.screenshot(path=f"{OUT_DIR}/02-desktop-drawer-closed.png")
    print("02-desktop-drawer-closed.png")

    # 03: drawer open + traffic open
    page.click("#toggle-nodes-drawer")
    page.wait_for_timeout(300)
    page.click("#toggle-traffic-drawer")
    page.wait_for_timeout(400)
    page.screenshot(path=f"{OUT_DIR}/03-desktop-traffic-open.png")
    print("03-desktop-traffic-open.png")

    page.close()

    # ── Mobile 390×844 ────────────────────────────────────────────────────────
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)

    # 04: mobile initial
    page.screenshot(path=f"{OUT_DIR}/04-mobile-initial.png")
    print("04-mobile-initial.png")

    # 05: mobile with drawer open
    page.click("#toggle-nodes-drawer")
    page.wait_for_timeout(400)
    page.screenshot(path=f"{OUT_DIR}/05-mobile-drawer-open.png")
    print("05-mobile-drawer-open.png")

    page.close()
    browser.close()

print(f"\nAll screenshots saved to {OUT_DIR}/")
