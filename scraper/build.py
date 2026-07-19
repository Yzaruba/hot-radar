"""Pipeline orchestrator: scrape → translate → mirror → surge → contract JSON.

Exit codes: 0 = all fresh; 2 = partial (some categories/tiktok stale);
1 = total failure (nothing written, old data preserved).
"""
import re
import sys

from . import amazon, config, images, movers, tiktok, translate
from .util import iso, log, now_utc, read_json, write_json


def tiktok_match(title_en: str, hashtag_names) -> list:
    """Hashtags (len>=4) equal to a run of 1-3 consecutive title words.

    Word-run equality (not substring) so tag 'remove' does not hit 'Remover'.
    """
    words = re.findall(r"[a-z0-9]+", (title_en or "").lower())
    grams = set()
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            grams.add("".join(words[i : i + n]))
    hits = []
    for tag in hashtag_names:
        t = re.sub(r"[^a-z0-9]", "", tag.lower())
        if len(t) >= 4 and t in grams:
            hits.append(tag)
    return hits


def _prev_products(prev_radar, kind, category_id) -> list:
    if not prev_radar:
        return []
    out = []
    for p in prev_radar.get("products", []):
        if p.get("list") == kind and p.get("category") == category_id:
            q = dict(p)
            # re-derive scrape-shape fields so the pipeline can re-process them
            q["title"] = q.get("title_en")
            out.append(q)
    return out


def _scrape_amazon(prev_radar):
    from playwright.sync_api import sync_playwright

    per_key, stale_pairs = {}, set()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for cat in config.CATEGORIES:
                for kind in config.LISTS:
                    try:
                        per_key[(kind, cat["id"])] = amazon.fetch_category(
                            browser, cat["slug"], kind, category_id=cat["id"]
                        )
                        log(f"OK {kind}/{cat['id']}: {len(per_key[(kind, cat['id'])])} items")
                    except Exception as e:  # noqa: BLE001
                        log(f"FAIL {kind}/{cat['id']}: {e}")
                        stale_pairs.add((kind, cat["id"]))
                        per_key[(kind, cat["id"])] = _prev_products(prev_radar, kind, cat["id"])
            real_movers = amazon.probe_real_movers(browser)
        finally:
            browser.close()
    return per_key, stale_pairs, real_movers


def main() -> int:
    now = now_utc()
    prev_radar = read_json(config.RADAR_JSON)
    prev_trends = read_json(config.TRENDS_JSON)

    per_key, stale_pairs, real_movers = _scrape_amazon(prev_radar)
    stale_cats = {cid for (_, cid) in stale_pairs}
    if len(stale_pairs) >= len(config.CATEGORIES) * len(config.LISTS):
        log("ALL lists failed — refusing to overwrite good data")
        return 1

    tiktok_stale = False
    try:
        hashtags = tiktok.fetch_hashtags()
    except Exception as e:  # noqa: BLE001
        log(f"tiktok failed: {e}")
        tiktok_stale = True
        hashtags = [
            {"name": h["name"], "rank": h["rank"], "posts": h["posts"], "curve": h["curve"]}
            for h in (prev_trends or {}).get("hashtags", [])
        ]

    # ---- snapshot fresh observations, compute surge on card-able fresh items
    fresh_items = [
        i
        for (kind, cid), lst in per_key.items()
        for i in lst
        if (kind, cid) not in stale_pairs and i.get("rank")
    ]
    cardable = [i for i in fresh_items if i.get("title") and i.get("image_src")]
    baseline = movers.pick_baseline(now)
    surge = movers.compute_surge(cardable, baseline)
    surge_by_asin = {(s["list"], s["category"], s["asin"]): s for s in surge}

    # ---- translation (short titles + hashtag names, cached)
    all_products = []
    for (kind, cid), lst in per_key.items():
        for i in lst:
            if i.get("title") and (i.get("image_src") or i.get("image")):
                all_products.append(i)
    shorts = {translate.to_short_title(p["title"]) for p in all_products}
    tag_names = [h["name"] for h in hashtags]
    used_texts = sorted(shorts) + tag_names
    zh_map = translate.translate_many(used_texts)
    translate.prune_cache(used_texts)

    # ---- assemble contract products
    prev_first_seen = {
        p["asin"]: p.get("first_seen") for p in (prev_radar or {}).get("products", [])
    }
    today = now.strftime("%Y-%m-%d")
    products = []
    for p in all_products:
        short = translate.to_short_title(p["title"])
        title_zh = zh_map.get(short)
        keyword_zh = translate.to_keyword_zh(title_zh) if title_zh else None
        s = surge_by_asin.get((p["list"], p["category"], p["asin"]))
        matched = tiktok_match(p["title"], tag_names)
        products.append(
            {
                "asin": p["asin"],
                "title_en": p["title"],
                "title_zh": title_zh,
                "keyword_zh": keyword_zh,
                "url_1688": translate.url_1688(keyword_zh) if keyword_zh else None,
                "url_1688_fallback": translate.url_1688_fallback(short),
                "amazon_url": f"https://www.amazon.com/dp/{p['asin']}",
                "image_src": p.get("image_src"),
                "image": p.get("image"),
                "price": p.get("price"),
                "rating": p.get("rating"),
                "ratings_count": p.get("ratings_count"),
                "category": p["category"],
                "list": p["list"],
                "rank": p["rank"],
                "rank_prev": s.get("rank_prev") if s else None,
                "rank_delta": s.get("rank_delta") if s else None,
                "rank_pct": s.get("rank_pct") if s else None,
                "is_new_entry": s.get("is_new_entry", False) if s else False,
                "surge_rank": s.get("surge_rank") if s else None,
                "signals": {
                    "amazon_surge": bool(s),
                    "tiktok": matched,
                    "new_release": p["list"] == "new-releases",
                },
                "first_seen": prev_first_seen.get(p["asin"]) or today,
            }
        )

    images.mirror(products)
    products = [p for p in products if p.get("image")]
    images.prune(products)
    products.sort(key=lambda p: (p["list"], p["category"], p["rank"]))

    radar = {
        "generated_at": iso(now),
        "real_movers_available": real_movers,
        "categories": [
            {"id": c["id"], "zh": c["zh"], "stale": c["id"] in stale_cats}
            for c in config.CATEGORIES
        ],
        "products": products,
    }
    write_json(config.RADAR_JSON, radar)

    trend_rows = []
    for h in hashtags:
        zh = zh_map.get(h["name"])
        trend_rows.append(
            {
                "name": h["name"],
                "zh": zh,
                "rank": h["rank"],
                "posts": h["posts"],
                "curve": h["curve"],
                "keyword_zh": translate.to_keyword_zh(zh) if zh else None,
                "url_1688": translate.url_1688(zh) if zh else None,
            }
        )
    write_json(
        config.TRENDS_JSON,
        {"generated_at": iso(now), "stale": tiktok_stale, "hashtags": trend_rows},
    )

    if fresh_items:
        movers.save_snapshot(fresh_items, now)
    movers.prune_snapshots(now)

    log(
        f"done: {len(products)} cards, surge={len(surge)}, hashtags={len(trend_rows)}, "
        f"stale_pairs={sorted(stale_pairs)}, tiktok_stale={tiktok_stale}"
    )
    return 2 if (stale_pairs or tiktok_stale) else 0


if __name__ == "__main__":
    sys.exit(main())
