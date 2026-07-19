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
    assert meta["run_id"] == "42" and meta["deployed_commit"] == "abc123"
    assert meta["duration_seconds"] == 90.0
    assert "new-releases:kitchen" in meta["stale_pairs"]
    assert "bestsellers:kitchen" in meta["fresh_pairs"]
    assert meta["skipped_reason"] is None
