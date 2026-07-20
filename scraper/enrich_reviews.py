"""Standalone review-enrichment run — fully decoupled from the 6h radar cycle.

Run manually or by .github/workflows/reviews.yml (daily). Failures here can
never block or fail the main radar publish; per-ASIN failures are isolated
and recorded in data/reviews/_status.json.
"""
import os
import random
import sys
import time

from . import config, reviews
from . import reviews_config as rcfg
from .util import iso, log, now_utc, read_json, write_json


def pick_asins(radar, limit=rcfg.MAX_ASINS_PER_RUN):
    """Deterministic priority: Top3 → surge board order → opportunity score."""
    products = radar.get("products", [])
    by_asin = {p["asin"]: p for p in products}
    ordered = [a for a in (radar.get("top3") or {}).get("asins", []) if a in by_asin]
    surge = sorted((p for p in products if p.get("surge_rank")), key=lambda p: p["surge_rank"])
    ordered += [p["asin"] for p in surge]
    scored = sorted(products, key=lambda p: (-(p.get("opportunity_score") or 0), p["asin"]))
    ordered += [p["asin"] for p in scored]
    seen, out = set(), []
    for a in ordered:
        if a in seen:
            continue
        seen.add(a)
        out.append(a)
        if len(out) >= limit:
            break
    return out


def main() -> int:
    now = now_utc()
    radar = read_json(config.RADAR_JSON)
    if not radar:
        log("no radar.json — nothing to enrich")
        return 0
    pname = (os.environ.get(rcfg.ENV_PROVIDER) or rcfg.DEFAULT_PROVIDER).strip().lower()
    asins = pick_asins(radar)
    by_asin = {p["asin"]: p for p in radar.get("products", [])}

    if pname == "none":
        write_json(reviews.RAW_DIR / "_status.json", {
            "run_at": iso(now), "provider": "none", "requested": len(asins),
            "processed": [], "skipped_fresh_cache": 0,
            "note": "no review provider configured — UI shows 待数据源接入",
        })
        log("provider=none — nothing fetched (by design)")
        return 0

    browser = pw_ctx = None
    if pname == "amazon_page":
        from playwright.sync_api import sync_playwright

        pw_ctx = sync_playwright().start()
        browser = pw_ctx.chromium.launch(headless=True)

    processed, skipped = [], 0
    try:
        provider = reviews.make_provider(browser=browser)
        for asin in asins:
            current_count = (by_asin.get(asin) or {}).get("ratings_count")
            if reviews.cache_is_fresh(reviews.load_published(asin), now, current_count):
                skipped += 1
                continue
            result = None
            for attempt in range(1 + rcfg.MAX_RETRIES_PER_ASIN):
                try:
                    result = provider.fetch_reviews(asin)
                except Exception as e:  # noqa: BLE001 — single ASIN must not kill the run
                    result = reviews.ProviderResult("failed", error_code=f"crash:{e.__class__.__name__}")
                if result.status != "failed":
                    break  # ready/unavailable/unconfigured — retrying won't change it
                time.sleep(2)
            recorded = reviews.preserve_or_save(asin, provider.name, result, now)
            processed.append({
                "asin": asin, "status": recorded,
                "error": result.error_code, "sample": len(result.reviews),
            })
            log(f"{asin}: {recorded} ({len(result.reviews)} reviews)")
            time.sleep(random.uniform(*rcfg.REQUEST_DELAY_RANGE))
    finally:
        if browser:
            browser.close()
        if pw_ctx:
            pw_ctx.stop()

    write_json(reviews.RAW_DIR / "_status.json", {
        "run_at": iso(now), "provider": pname, "requested": len(asins),
        "skipped_fresh_cache": skipped, "processed": processed,
        "limits": {
            "max_asins": rcfg.MAX_ASINS_PER_RUN,
            "max_reviews_per_asin": rcfg.MAX_REVIEWS_PER_ASIN,
            "retries_per_asin": rcfg.MAX_RETRIES_PER_ASIN,
            "cache_days": rcfg.CACHE_DAYS,
        },
    })
    ready = sum(1 for p in processed if p["status"] == "ready")
    log(f"enrich done: ready={ready} processed={len(processed)} cached={skipped}")
    if processed and all(p["status"] == "failed" for p in processed):
        return 1  # everything failed — make the (separate) workflow red for visibility
    return 0


if __name__ == "__main__":
    sys.exit(main())
