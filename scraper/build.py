"""Pipeline orchestrator: scrape → translate → mirror → surge → contract JSON.

Contract schema_version 2: one product per ASIN; per-list/category placements
live in the product's `sources` array, surge placement in `surge`.

Exit codes: 0 = all fresh; 2 = partial (some list/category pairs or tiktok
stale); 1 = total failure (nothing written, old data preserved).
"""
import os
import re
import sys

from . import amazon, config, images, movers, scoring, tiktok, translate
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
    """Rebuild scrape-shaped entries for one (list, category) from prior radar.json.

    Handles both schema v2 (sources array) and the original v1 flat products.
    """
    if not prev_radar:
        return []
    out = []
    for p in prev_radar.get("products", []):
        if p.get("sources"):  # schema v2
            src = next(
                (s for s in p["sources"] if s["list"] == kind and s["category"] == category_id),
                None,
            )
            if not src:
                continue
            out.append(
                {
                    "asin": p["asin"],
                    "title": p.get("title_en"),
                    "image": p.get("image"),
                    "price": p.get("price"),
                    "rating": p.get("rating"),
                    "ratings_count": p.get("ratings_count"),
                    "list": kind,
                    "category": category_id,
                    "rank": src["rank"],
                }
            )
        elif p.get("list") == kind and p.get("category") == category_id:  # schema v1
            q = dict(p)
            q["title"] = q.get("title_en")
            out.append(q)
    return out


def collect_fresh_items(per_key, stale_pairs) -> list:
    """Only actually-observed items feed snapshots and surge — never stale refills."""
    return [
        i
        for (kind, cid), lst in per_key.items()
        for i in lst
        if (kind, cid) not in stale_pairs and i.get("rank")
    ]


def merge_products(entries) -> list:
    """Merge flat (list, category) entries into one canonical product per ASIN.

    Placements are kept in `sources`; scalar enrichment (title/image/price/…)
    comes from the first source that has it, in (list, category, rank) order.
    """
    by_asin = {}
    for e in sorted(entries, key=lambda x: (x["list"], x["category"], x["rank"])):
        m = by_asin.setdefault(e["asin"], {"asin": e["asin"], "sources": []})
        m["sources"].append({"list": e["list"], "category": e["category"], "rank": e["rank"]})
        for field in ("title", "image_src", "image", "price", "rating", "ratings_count"):
            if m.get(field) is None and e.get(field) is not None:
                m[field] = e[field]
    return sorted(by_asin.values(), key=lambda m: m["asin"])


def build_run_meta(
    started,
    finished,
    stale_pairs,
    flat_entry_count,
    merged_count,
    products,
    data_changed,
    env=None,
) -> dict:
    env = os.environ if env is None else env
    trigger_map = {"schedule": "schedule", "workflow_dispatch": "manual"}
    event = env.get("GITHUB_EVENT_NAME", "")
    all_pairs = [(k, c["id"]) for c in config.CATEGORIES for k in config.LISTS]
    unique_asins = {p["asin"] for p in products}
    return {
        "run_id": env.get("GITHUB_RUN_ID", "local"),
        "trigger": trigger_map.get(event, event or "local"),
        "force": env.get("RADAR_FORCE", "").strip().lower() == "true",
        "started_at": iso(started),
        "finished_at": iso(finished),
        "duration_seconds": round((finished - started).total_seconds(), 1),
        "data_changed": data_changed,
        "skipped_reason": None,  # skipped runs never reach build.py (preflight gates them)
        "fresh_pairs": sorted(f"{k}:{c}" for (k, c) in all_pairs if (k, c) not in stale_pairs),
        "stale_pairs": sorted(f"{k}:{c}" for (k, c) in stale_pairs),
        "product_count": len(products),
        "unique_asin_count": len(unique_asins),
        "duplicate_count": flat_entry_count - merged_count,
        # renamed from deployed_commit (P1A): this is the commit the run executed
        # FROM, not the data commit it created — the old name overpromised
        "source_commit": env.get("GITHUB_SHA", "local"),
    }


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
    fresh_items = collect_fresh_items(per_key, stale_pairs)
    fresh_cardable = [i for i in fresh_items if i.get("title") and i.get("image_src")]
    baseline = movers.pick_baseline(now)
    surge = movers.compute_surge(fresh_cardable, baseline)
    surge_by_asin = {s["asin"]: s for s in surge}  # board is one-slot-per-ASIN

    # ---- merge flat entries into canonical ASIN products
    flat_cardable = [
        i
        for (kind, cid), lst in per_key.items()
        for i in lst
        if i.get("title") and (i.get("image_src") or i.get("image"))
    ]
    merged = merge_products(flat_cardable)

    # ---- translation (short titles + hashtag names, cached)
    shorts = {translate.to_short_title(m["title"]) for m in merged}
    tag_names = [h["name"] for h in hashtags]
    used_texts = sorted(shorts) + tag_names
    zh_map = translate.translate_many(used_texts)
    translate.prune_cache(used_texts)

    # ---- assemble contract products (schema v2: one per ASIN)
    prev_first_seen = {
        p["asin"]: p.get("first_seen") for p in (prev_radar or {}).get("products", [])
    }
    today = now.strftime("%Y-%m-%d")
    products = []
    for m in merged:
        short = translate.to_short_title(m["title"])
        title_zh = zh_map.get(short)
        keyword_zh = translate.to_keyword_zh(title_zh) if title_zh else None
        # sourcing keyword: brands/marketing stripped — this is what 1688 gets
        procurement = scoring.procurement_keyword(title_zh) if title_zh else None
        search_kw = procurement or keyword_zh
        s = surge_by_asin.get(m["asin"])
        products.append(
            {
                "asin": m["asin"],
                "title_en": m["title"],
                "title_zh": title_zh,
                "keyword_zh": keyword_zh,
                "procurement_keyword_zh": procurement,
                "url_1688": translate.url_1688(search_kw) if search_kw else None,
                "url_1688_fallback": translate.url_1688_fallback(short),
                "amazon_url": f"https://www.amazon.com/dp/{m['asin']}",
                "image_src": m.get("image_src"),
                "image": m.get("image"),
                "price": m.get("price"),
                "rating": m.get("rating"),
                "ratings_count": m.get("ratings_count"),
                "sources": m["sources"],
                "surge": (
                    {
                        "list": s["list"],
                        "category": s["category"],
                        "rank": s["rank"],
                        "rank_prev": s["rank_prev"],
                        "rank_delta": s["rank_delta"],
                        "rank_pct": s["rank_pct"],
                        "is_new_entry": s["is_new_entry"],
                        "surge_rank": s["surge_rank"],
                    }
                    if s
                    else None
                ),
                "surge_rank": s["surge_rank"] if s else None,
                "signals": {
                    "amazon_surge": bool(s),
                    "tiktok": tiktok_match(m["title"], tag_names),
                    "new_release": any(x["list"] == "new-releases" for x in m["sources"]),
                },
                "first_seen": prev_first_seen.get(m["asin"]) or today,
            }
        )

    images.mirror(products)
    products = [p for p in products if p.get("image")]
    images.prune(products)
    products.sort(key=lambda p: p["asin"])

    scoring.apply(products, now.date())
    top3 = scoring.pick_top3(products)

    radar = {
        "schema_version": 2,
        "top3": top3,
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

    finished = now_utc()
    data_changed = (prev_radar or {}).get("products") != products or [
        h["name"] for h in (prev_trends or {}).get("hashtags", [])
    ] != [t["name"] for t in trend_rows]
    run_meta = build_run_meta(
        now, finished, stale_pairs, len(flat_cardable), len(merged), products, data_changed
    )
    write_json(config.RUN_META, run_meta)

    log(
        f"done: {len(products)} products ({run_meta['duplicate_count']} dup placements merged), "
        f"surge={len(surge)}, hashtags={len(trend_rows)}, "
        f"stale_pairs={sorted(stale_pairs)}, tiktok_stale={tiktok_stale}, "
        f"data_changed={data_changed}"
    )
    return 2 if (stale_pairs or tiktok_stale) else 0


if __name__ == "__main__":
    sys.exit(main())
