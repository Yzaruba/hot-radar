from datetime import datetime, timedelta, timezone

from scraper import build


def test_tiktok_match_substring_min_length():
    tags = ["minifan", "fan", "led", "ledstriplights"]
    hits = build.tiktok_match("Mini Fan Portable LED Strip Lights", tags)
    assert "minifan" in hits           # squashed substring matches
    assert "ledstriplights" in hits
    assert "fan" not in hits and "led" not in hits  # len<4 excluded


def test_tiktok_match_no_hits():
    assert build.tiktok_match("Ceramic Mug", ["minifan"]) == []


def test_tiktok_match_rejects_partial_word():
    assert build.tiktok_match("Makeup Remover Wipes", ["remove"]) == []
    assert build.tiktok_match("Remove Stains Fast", ["remove"]) == ["remove"]


def test_prev_products_filters_and_restores_title():
    prev = {
        "products": [
            {"asin": "A", "list": "bestsellers", "category": "electronics", "title_en": "X", "rank": 1},
            {"asin": "B", "list": "new-releases", "category": "electronics", "title_en": "Y", "rank": 2},
        ]
    }
    out = build._prev_products(prev, "bestsellers", "electronics")
    assert [p["asin"] for p in out] == ["A"]
    assert out[0]["title"] == "X"


def test_prev_products_handles_missing():
    assert build._prev_products(None, "bestsellers", "electronics") == []


def test_prev_products_reads_v2_sources():
    prev = {
        "schema_version": 2,
        "products": [
            {
                "asin": "A", "title_en": "X", "image": "data/img/A.jpg", "price": "$1",
                "rating": 4.0, "ratings_count": 5,
                "sources": [{"list": "bestsellers", "category": "electronics", "rank": 4}],
            }
        ],
    }
    out = build._prev_products(prev, "bestsellers", "electronics")
    assert out[0]["title"] == "X" and out[0]["rank"] == 4
    assert out[0]["list"] == "bestsellers" and out[0]["category"] == "electronics"
    assert build._prev_products(prev, "new-releases", "electronics") == []


def _flat(asin, lst, cat, rank, **kw):
    return {"asin": asin, "list": lst, "category": cat, "rank": rank, **kw}


def test_duplicate_asins_merge_correctly():
    flat = [
        _flat("A", "bestsellers", "electronics", 3, title="X", image_src="u1", price="$1"),
        _flat("A", "new-releases", "kitchen", 7, title="X longer", image_src="u2"),
        _flat("B", "bestsellers", "electronics", 5, title="Y", image_src="u3"),
    ]
    merged = build.merge_products(flat)
    assert [m["asin"] for m in merged] == ["A", "B"]
    a = merged[0]
    assert {(s["list"], s["category"], s["rank"]) for s in a["sources"]} == {
        ("bestsellers", "electronics", 3),
        ("new-releases", "kitchen", 7),
    }
    assert a["title"] == "X" and a["image_src"] == "u1" and a["price"] == "$1"


def test_stale_pairs_do_not_overwrite_fresh_pairs():
    per_key = {
        ("bestsellers", "electronics"): [_flat("A", "bestsellers", "electronics", 1)],
        ("new-releases", "electronics"): [_flat("B", "new-releases", "electronics", 2)],
    }
    fresh = build.collect_fresh_items(per_key, {("new-releases", "electronics")})
    assert [i["asin"] for i in fresh] == ["A"]  # stale refill stays out of snapshots/surge


def test_prev_ip_products_rebuilds_scrape_shape():
    prev = {"ip_products": [
        {"asin": "A", "title_en": "Pokemon TCG Box", "image": "data/img/A.jpg",
         "price": "$39.99", "rating": 4.8, "ratings_count": 900,
         "category": "tcg", "rank": 2},
        {"asin": "B", "title_en": "Figure", "category": "anime", "rank": 5},
    ]}
    out = build._prev_ip_products(prev, "tcg")
    assert len(out) == 1
    assert out[0]["title"] == "Pokemon TCG Box" and out[0]["list"] == "bestsellers"
    assert build._prev_ip_products(None, "tcg") == []


def test_usd_only_enters_price_history():
    per_key = {("bestsellers", "electronics"): [
        {"asin": "A", "list": "bestsellers", "category": "electronics", "rank": 1, "price": "$19.99"},
        {"asin": "B", "list": "bestsellers", "category": "electronics", "rank": 2, "price": "AWG 35.90"},
    ]}
    fresh = build.collect_fresh_items(per_key, set())
    from scraper import scoring
    for i in fresh:
        raw = (i.get("price") or "").strip()
        i["price_val"] = scoring.parse_price(raw) if raw.startswith("$") else None
    vals = {i["asin"]: i["price_val"] for i in fresh}
    assert vals["A"] == 19.99
    assert vals["B"] is None  # AWG (local geo-pricing) never poisons the history


def test_run_meta_covers_ip_pairs():
    started = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    meta = build.build_run_meta(
        started, started + timedelta(seconds=10), stale_pairs=set(),
        flat_entry_count=0, merged_count=0, products=[], data_changed=False, env={},
    )
    assert "bestsellers:tcg" in meta["fresh_pairs"]
    assert "bestsellers:manga" in meta["fresh_pairs"]
    assert "bestsellers:candy" in meta["fresh_pairs"]
    assert "bestsellers:plush" in meta["fresh_pairs"] and "new-releases:plush" in meta["fresh_pairs"]


def test_candy_is_flagged_food_and_plush_is_main():
    from scraper import config as c
    assert "candy" in {x["id"] for x in c.IP_CATEGORIES}
    assert "candy" in c.FOOD_IP_IDS
    assert "plush" in {x["id"] for x in c.CATEGORIES}  # 1688-sourceable → main flow


def test_run_meta_unique_asin_count_matches_output():
    started = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    finished = started + timedelta(seconds=90)
    products = [{"asin": "A"}, {"asin": "B"}, {"asin": "C"}]
    meta = build.build_run_meta(
        started, finished,
        stale_pairs={("new-releases", "kitchen")},
        flat_entry_count=5, merged_count=3,
        products=products, data_changed=True,
        env={"GITHUB_RUN_ID": "42", "GITHUB_EVENT_NAME": "workflow_dispatch",
             "RADAR_FORCE": "true", "GITHUB_SHA": "abc123"},
    )
    assert meta["unique_asin_count"] == len(products) == meta["product_count"]
    assert meta["duplicate_count"] == 2
    assert meta["trigger"] == "manual" and meta["force"] is True
    assert meta["run_id"] == "42" and meta["source_commit"] == "abc123"
    assert "deployed_commit" not in meta  # renamed in P1A — old name overpromised
    assert meta["duration_seconds"] == 90.0
    assert "new-releases:kitchen" in meta["stale_pairs"]
    assert "bestsellers:kitchen" in meta["fresh_pairs"]
    assert meta["skipped_reason"] is None
