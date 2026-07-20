import copy
from datetime import datetime, timedelta, timezone

from scraper import enrich_reviews, reviews
from scraper import reviews_config as rcfg

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def _rv(rating, text, title=""):
    return {"rating": rating, "title": title, "text": text}


# ---- summarizer: real text only, deterministic, honest ----

def test_summarize_empty_returns_none_no_faking():
    assert reviews.summarize([]) is None
    assert reviews.summarize(None) is None


def test_summarize_buckets_by_rating_and_counts_themes():
    revs = [
        _rv(5, "Great quality, very sturdy and well made"),
        _rv(5, "quality is amazing, my kid loves it"),
        _rv(4, "good value for the price"),
        _rv(3, "it's okay I guess"),                       # neutral ignored
        _rv(1, "broke after two days, poor quality"),
        _rv(2, "flimsy and cheaply made, fell apart"),
    ]
    s = reviews.summarize(revs)
    pos = {t["zh"]: t["count"] for t in s["positive_themes"]}
    neg = {t["zh"]: t["count"] for t in s["negative_themes"]}
    assert pos["质量做工"] == 2
    assert neg["质量做工"] == 2
    assert "6条" in s["basis_zh"]


def test_summarize_deterministic():
    revs = [_rv(5, "sturdy quality"), _rv(1, "broke fast"), _rv(4, "worth the price")]
    a = reviews.summarize(copy.deepcopy(revs))
    b = reviews.summarize(list(reversed(copy.deepcopy(revs))))
    assert a == b


def test_verdict_small_sample_hedges():
    s = reviews.summarize([_rv(5, "sturdy quality"), _rv(5, "nice color")])
    assert "样本太少" in s["procurement_verdict_zh"]


def test_verdict_low_negative_share():
    revs = [_rv(5, f"good quality {i}") for i in range(9)] + [_rv(1, "broke")]
    s = reviews.summarize(revs)
    assert "差评率低" in s["procurement_verdict_zh"]


def test_verdict_mid_negative_names_top_theme():
    revs = [_rv(5, f"nice color {i}") for i in range(7)] + [
        _rv(1, "broke, poor quality"), _rv(2, "flimsy, fell apart"), _rv(1, "cracked on day one"),
    ]
    s = reviews.summarize(revs)
    assert "差评集中在" in s["procurement_verdict_zh"]
    assert "质量做工" in s["procurement_verdict_zh"]


def test_verdict_high_negative_share():
    revs = [_rv(5, "fine")] * 4 + [_rv(1, "terrible broke")] * 6
    s = reviews.summarize(revs)
    assert "不建议现在进" in s["procurement_verdict_zh"]


# ---- cache logic ----

def _pub(status="ready", expires_h=24, total=100):
    return {
        "status": status,
        "expires_at": (NOW + timedelta(hours=expires_h)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_review_count": total,
    }


def test_cache_fresh_skips_refetch():
    assert reviews.cache_is_fresh(_pub(), NOW, current_review_count=105) is True


def test_cache_expired_refetches():
    assert reviews.cache_is_fresh(_pub(expires_h=-1), NOW) is False


def test_cache_growth_over_20pct_refetches_early():
    assert reviews.cache_is_fresh(_pub(total=100), NOW, current_review_count=125) is False


def test_cache_failed_status_refetches():
    assert reviews.cache_is_fresh(_pub(status="failed"), NOW) is False
    assert reviews.cache_is_fresh(None, NOW) is False


# ---- ASIN selection ----

def test_pick_asins_top3_first_dedup_capped():
    radar = {
        "top3": {"asins": ["A1", "A2"]},
        "products": (
            [{"asin": "A1", "surge_rank": 5, "opportunity_score": 60},
             {"asin": "A2", "surge_rank": None, "opportunity_score": 64},
             {"asin": "A3", "surge_rank": 1, "opportunity_score": 50}]
            + [{"asin": f"B{i:02d}", "surge_rank": None, "opportunity_score": 40 - i}
               for i in range(30)]
        ),
    }
    out = enrich_reviews.pick_asins(radar)
    assert out[:3] == ["A1", "A2", "A3"]      # top3 first, then surge order
    assert len(out) == rcfg.MAX_ASINS_PER_RUN
    assert len(set(out)) == len(out)


# ---- dp page parsing ----

DP_HTML = """
<div id="acrPopover"><i class="a-icon-alt">4.4 out of 5 stars</i></div>
<span data-hook="total-review-count">1,234 global ratings</span>
<div data-hook="review">
  <span data-hook="review-title">5.0 out of 5 stars Amazing quality</span>
  <i data-hook="review-star-rating"><span class="a-icon-alt">5.0 out of 5 stars</span></i>
  <span data-hook="review-body">Very sturdy and well made, kids love it.</span>
</div>
<div data-hook="review">
  <i data-hook="review-star-rating"><span class="a-icon-alt">1.0 out of 5 stars</span></i>
  <span data-hook="review-body">Broke after a week. Poor quality.</span>
</div>
"""


def test_parse_dp_reviews():
    revs, total, rating = reviews.parse_dp_reviews(DP_HTML)
    assert len(revs) == 2
    assert revs[0]["rating"] == 5.0 and "sturdy" in revs[0]["text"]
    assert revs[0]["title"] == "Amazing quality"
    assert revs[1]["rating"] == 1.0
    assert total == 1234 and rating == 4.4


def test_parse_dp_empty_returns_no_reviews():
    revs, total, rating = reviews.parse_dp_reviews("<html><body>nothing</body></html>")
    assert revs == [] and total is None


# ---- providers ----

def test_none_provider_safe():
    r = reviews.NoneProvider().fetch_reviews("B000000001")
    assert r.status == "unconfigured" and r.reviews == []


def test_make_provider_defaults_safe_without_browser():
    p = reviews.make_provider(browser=None, env={})
    assert p.name == "none"  # amazon_page needs a browser; degrade safely


def test_rainforest_without_key_unconfigured():
    p = reviews.make_provider(browser=None, env={"REVIEWS_PROVIDER": "rainforest"})
    assert p.name == "rainforest"
    assert p.fetch_reviews("B000000001").status == "unconfigured"


# ---- summary doc schema ----

def test_build_summary_doc_schema_fields():
    res = reviews.ProviderResult(
        "ready",
        reviews=[_rv(5, "sturdy quality"), _rv(1, "broke"), _rv(4, "worth it"),
                 _rv(4, "cute color"), _rv(5, "kids love it")],
        total_review_count=213, rating=4.4, source_url="https://www.amazon.com/dp/X",
    )
    doc = reviews.build_summary_doc("B0XXXXXXXX", res, NOW)
    for key in ("schema_version", "asin", "source_url", "fetched_at", "expires_at",
                "status", "rating", "total_review_count", "sample_count",
                "star_distribution_sample", "summary_zh"):
        assert key in doc, key
    assert doc["schema_version"] == rcfg.SCHEMA_VERSION
    assert doc["sample_count"] == 5
    assert doc["star_distribution_sample"]["5"] == 2
    assert doc["summary_zh"]["procurement_verdict_zh"]


def test_unavailable_doc_has_no_summary():
    res = reviews.ProviderResult("unavailable", error_code="no_reviews_rendered")
    doc = reviews.build_summary_doc("B0XXXXXXXX", res, NOW)
    assert doc["status"] == "unavailable"
    assert doc["summary_zh"] is None  # nothing fake, ever


def test_preserve_keeps_real_summary_as_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(reviews, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(reviews, "PUB_DIR", tmp_path / "pub")
    good = reviews.ProviderResult(
        "ready",
        reviews=[_rv(5, "sturdy quality"), _rv(5, "kids love it"), _rv(1, "broke"),
                 _rv(4, "worth it"), _rv(4, "cute")],
        total_review_count=50, rating=4.5, source_url="u",
    )
    assert reviews.preserve_or_save("B0TESTSTALE", "amazon_page", good, NOW) == "ready"
    bad = reviews.ProviderResult("unavailable", error_code="no_reviews_rendered")
    assert reviews.preserve_or_save("B0TESTSTALE", "amazon_page", bad, NOW) == "stale_kept"
    doc = reviews.load_published("B0TESTSTALE")
    assert doc["status"] == "stale"
    assert doc["summary_zh"]["procurement_verdict_zh"]  # real data survived


def test_preserve_overwrites_when_nothing_to_keep(tmp_path, monkeypatch):
    monkeypatch.setattr(reviews, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(reviews, "PUB_DIR", tmp_path / "pub")
    bad = reviews.ProviderResult("unavailable", error_code="x")
    assert reviews.preserve_or_save("B0TESTNONE0", "amazon_page", bad, NOW) == "unavailable"
    assert reviews.load_published("B0TESTNONE0")["status"] == "unavailable"
