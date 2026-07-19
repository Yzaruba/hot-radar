"""Amazon zg list scraper (bestsellers / new-releases) via vanilla Playwright.

Parse strategy (verified live 2026-07): the data-client-recs-list JSON attribute
carries asin+rank for all 50 items per page; the ~30 server-rendered
#gridItemRoot blocks enrich title/price/rating/image. The bsms.* percentage
fields inside recs-list exist but are EMPTY — never rely on them.
An empty parse means Amazon soft-blocked us (HTTP 200 + empty grid): raise.
"""
import json
import random
import re
import time

from bs4 import BeautifulSoup

from . import config
from .util import log

BASE = "https://www.amazon.com/gp"


class CategoryEmpty(RuntimeError):
    pass


def _dynamic_image(attr_json: str):
    """Pick a mid-size (>=400px if possible) URL from data-a-dynamic-image."""
    try:
        mapping = json.loads(attr_json)
    except (TypeError, ValueError):
        return None
    if not mapping:
        return None
    by_width = sorted(mapping.items(), key=lambda kv: kv[1][0] if kv[1] else 0)
    for url, dims in by_width:
        if dims and dims[0] >= 400:
            return url
    return by_width[-1][0]


def _num(text):
    m = re.search(r"[\d,.]+", text or "")
    if not m:
        return None
    return m.group(0).replace(",", "")


def parse_zg_html(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    items = {}

    for div in soup.select("[data-client-recs-list]"):
        try:
            recs = json.loads(div["data-client-recs-list"])
        except (ValueError, KeyError):
            continue
        for rec in recs:
            asin = rec.get("id")
            meta = rec.get("metadataMap") or {}
            try:
                rank = int(meta.get("render.zg.rank"))
            except (TypeError, ValueError):
                rank = None
            if asin and rank:
                items.setdefault(asin, {"asin": asin, "rank": rank})

    for root in soup.find_all(id="gridItemRoot"):
        asin_el = root.find(attrs={"data-asin": True})
        asin = asin_el["data-asin"] if asin_el else None
        if not asin:
            continue
        entry = items.setdefault(asin, {"asin": asin, "rank": None})
        if entry["rank"] is None:
            badge = root.select_one(".zg-bdg-text")
            if badge:
                try:
                    entry["rank"] = int(_num(badge.get_text()))
                except (TypeError, ValueError):
                    pass
        title_el = root.select_one("[class*='_cDEzb_p13n-sc-css-line-clamp']")
        if title_el:
            entry["title"] = title_el.get_text(strip=True)
        price_el = root.select_one("[class*='_cDEzb_p13n-sc-price']")
        if price_el:
            entry["price"] = price_el.get_text(strip=True)
        rating_el = root.select_one(".a-icon-alt")
        if rating_el:
            try:
                entry["rating"] = float(rating_el.get_text(strip=True).split()[0])
            except (ValueError, IndexError):
                pass
            count_el = root.select_one("a[title] span.a-size-small, span.a-size-small")
            if count_el:
                try:
                    entry["ratings_count"] = int(_num(count_el.get_text()))
                except (TypeError, ValueError):
                    pass
        img = root.find("img")
        if img:
            src = _dynamic_image(img.get("data-a-dynamic-image")) or img.get("src")
            if src:
                entry["image_src"] = src

    out = [i for i in items.values() if i.get("rank")]
    out.sort(key=lambda i: i["rank"])
    return out


def _get_html(browser, url: str) -> str:
    page = browser.new_page(user_agent=config.UA, locale="en-US", viewport={"width": 1280, "height": 900})
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1500)
        return page.content()
    finally:
        page.close()


def fetch_category(browser, slug: str, kind: str, category_id: str) -> list:
    """Top100 for one category+list; raises CategoryEmpty on soft-block."""
    merged = {}
    for suffix in ("", "?pg=2"):
        url = f"{BASE}/{kind}/{slug}{suffix}"
        items = []
        for attempt in range(3):
            try:
                items = parse_zg_html(_get_html(browser, url))
                if items:
                    break
                log(f"{url}: 0 items on attempt {attempt + 1}")
            except Exception as e:  # noqa: BLE001 - retry navigation errors
                log(f"{url}: attempt {attempt + 1} error: {e}")
            time.sleep(3 * (attempt + 1))
        for i in items:
            i["list"] = kind
            i["category"] = category_id
            prev = merged.get(i["asin"])
            if prev is None or i["rank"] < prev["rank"]:
                merged[i["asin"]] = i
        time.sleep(random.uniform(2, 5))
    if not merged:
        raise CategoryEmpty(f"{kind}/{slug}: parsed 0 items (soft-block?)")
    return sorted(merged.values(), key=lambda i: i["rank"])


def probe_real_movers(browser) -> bool:
    """Canary: does the real Movers & Shakers page serve data again?"""
    try:
        items = parse_zg_html(_get_html(browser, f"{BASE}/movers-and-shakers/electronics"))
        available = len(items) > 0
        log(f"real movers-and-shakers canary: {'AVAILABLE again!' if available else 'still empty'}")
        return available
    except Exception as e:  # noqa: BLE001
        log(f"movers canary error: {e}")
        return False


if __name__ == "__main__":
    # Dev helper: capture a live fixture for tests/test_amazon_parse.py
    from pathlib import Path

    from playwright.sync_api import sync_playwright

    fixture = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "amazon_zg_sample.html"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        html = _get_html(browser, f"{BASE}/bestsellers/electronics")
        browser.close()
    fixture.write_text(html, encoding="utf-8")
    parsed = parse_zg_html(html)
    enriched = [i for i in parsed if i.get("title") and i.get("image_src")]
    print(f"fixture saved: {len(html)} bytes, parsed={len(parsed)}, enriched={len(enriched)}")
