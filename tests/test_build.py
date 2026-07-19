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
