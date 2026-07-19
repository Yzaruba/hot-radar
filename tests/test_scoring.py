import copy
import random
from datetime import date

from scraper import scoring
from scraper import scoring_config as cfg

TODAY = date(2026, 7, 20)


def _p(**kw):
    base = {
        "asin": "B000000001",
        "title_en": "Mini Portable Neck Fan Rechargeable Cooling",
        "price": "$19.99",
        "rating": 4.6,
        "ratings_count": 5000,
        "sources": [{"list": "bestsellers", "category": "toys", "rank": 10}],
        "surge": None,
        "signals": {"amazon_surge": False, "tiktok": [], "new_release": False},
        "first_seen": "2026-07-01",
    }
    base.update(kw)
    return base


def _surge(rank=5, prev=50, new=False):
    if new:
        return {"list": "bestsellers", "category": "toys", "rank": rank,
                "rank_prev": None, "rank_delta": None, "rank_pct": None,
                "is_new_entry": True, "surge_rank": 1}
    delta = prev - rank
    return {"list": "bestsellers", "category": "toys", "rank": rank,
            "rank_prev": prev, "rank_delta": delta,
            "rank_pct": round(delta / prev * 100, 1), "is_new_entry": False, "surge_rank": 1}


# ---- helpers / components ----

def test_parse_price_variants():
    assert scoring.parse_price("$12.99") == 12.99
    assert scoring.parse_price("AWG 21.70") == 21.70
    assert scoring.parse_price("1,299.00") == 1299.0
    assert scoring.parse_price(None) is None
    assert scoring.parse_price("See options") is None


def test_trend_is_not_percentage_only():
    # same pct (50%), but D sits at a much better absolute rank than C
    c = _p(surge=_surge(rank=50, prev=100))
    d = _p(surge=_surge(rank=10, prev=20))
    assert scoring.trend_score(d) > scoring.trend_score(c)


def test_trend_uses_delta_too():
    small_delta = _p(surge=_surge(rank=10, prev=12))   # pct 16.7, delta 2
    big_delta = _p(surge=_surge(rank=10, prev=70))     # pct 85.7, delta 60
    assert scoring.trend_score(big_delta) > scoring.trend_score(small_delta)


def test_market_low_reviews_hard_capped():
    assert scoring.market_score(_p(ratings_count=5)) <= cfg.LOW_REVIEW_CAP
    assert scoring.market_score(_p(ratings_count=9, rating=5.0)) <= cfg.LOW_REVIEW_CAP
    assert scoring.market_score(_p(ratings_count=10000, rating=4.6)) >= 15


def test_fresh_window():
    nr = _p(sources=[{"list": "new-releases", "category": "toys", "rank": 3}],
            first_seen="2026-07-19")
    assert scoring.fresh_score(nr, TODAY) == cfg.MAX_FRESH
    old = _p(first_seen="2026-05-01")
    assert scoring.fresh_score(old, TODAY) == 0.0


def test_fit_price_band_and_category():
    assert scoring.fit_score(_p()) == 20.0  # toys + $19.99 sweet spot
    no_price = scoring.fit_score(_p(price=None))
    assert no_price == 10.0  # category only
    assert scoring.fit_score(_p(price="$500.00")) < 12


def test_multi_signal_tiktok_is_auxiliary_only():
    solo_tiktok = _p(signals={"amazon_surge": False, "tiktok": ["fan"], "new_release": False})
    assert scoring.multi_signal_score(solo_tiktok) <= 2  # can never carry a product
    multi = _p(sources=[
        {"list": "bestsellers", "category": "toys", "rank": 5},
        {"list": "bestsellers", "category": "kitchen", "rank": 9},
        {"list": "new-releases", "category": "toys", "rank": 2},
    ])
    assert scoring.multi_signal_score(multi) == 8


# ---- risks ----

def test_medical_products_are_excluded_entirely():
    p = _p(title_en="Tylenol Extra Strength Caplets 500mg")
    out = scoring.score_product(p, TODAY)
    assert out["opportunity_score"] == 0.0
    assert out["recommendation"] == "高风险"
    assert "EXCLUDED_MEDICAL" in out["reason_codes"]


def test_brand_product_penalized():
    pts, codes = scoring.risk_deductions(_p(title_en="LEGO Star Wars Building Set"))
    assert "BRAND_PRODUCT" in codes and pts <= cfg.PENALTY_BRAND


def test_bulky_item_penalized():
    pts, codes = scoring.risk_deductions(_p(title_en="TV Stand for 65 inch Television"))
    assert "BULKY_ITEM" in codes


def test_missing_price_and_rating_lower_confidence():
    out = scoring.score_product(_p(price=None, rating=None), TODAY)
    assert out["confidence"] == "low"
    assert "NO_PRICE" in out["reason_codes"] and "NO_RATING" in out["reason_codes"]
    assert "价格" in out["primary_risk_zh"] or "评分" in out["primary_risk_zh"]


def test_low_reviews_risk_and_zh_text():
    out = scoring.score_product(_p(ratings_count=4), TODAY)
    assert "LOW_REVIEWS" in out["reason_codes"]
    assert out["confidence"] == "low"
    assert "4条" in out["primary_risk_zh"]


# ---- recommendation mapping ----

def test_recommendations():
    strong = _p(surge=_surge(rank=5, prev=50), ratings_count=10000, first_seen="2026-07-18")
    out = scoring.score_product(strong, TODAY)
    assert out["opportunity_score"] >= cfg.IMMEDIATE_MIN_SCORE
    assert out["recommendation"] == "立即找货"

    weak = _p(surge=None, ratings_count=60, first_seen="2026-05-01",
              sources=[{"list": "bestsellers", "category": "home", "rank": 90}])
    out2 = scoring.score_product(weak, TODAY)
    assert out2["recommendation"] == "继续观察"

    risky = _p(title_en="LEGO Marvel Set", ratings_count=5, surge=None,
               sources=[{"list": "bestsellers", "category": "home", "rank": 95}])
    out3 = scoring.score_product(risky, TODAY)
    assert out3["recommendation"] == "高风险"


# ---- determinism + top3 ----

def _fleet():
    return [
        _p(asin="B00000000A", surge=_surge(rank=3, prev=60), ratings_count=8000,
           first_seen="2026-07-18", title_en="Rainbow Squishy Butter Toy Fidget"),
        _p(asin="B00000000B", surge=_surge(rank=8, prev=40), ratings_count=3000,
           first_seen="2026-07-17", title_en="Mini Neck Fan Portable Rechargeable"),
        _p(asin="B00000000C", surge=_surge(rank=9, prev=44), ratings_count=2500,
           first_seen="2026-07-17", title_en="Portable Neck Fan Mini Rechargeable Cooling"),
        _p(asin="B00000000D", surge=_surge(rank=12, prev=30), ratings_count=900,
           first_seen="2026-07-16", title_en="LED Photo Clip String Lights Bedroom"),
        _p(asin="B00000000E", ratings_count=3, title_en="Unknown Gadget Cube"),
    ]


def test_deterministic_same_input_same_ordering():
    a, b = copy.deepcopy(_fleet()), copy.deepcopy(_fleet())
    rng = random.Random(42)
    rng.shuffle(b)
    scoring.apply(a, TODAY)
    scoring.apply(b, TODAY)
    sa = {p["asin"]: p["opportunity_score"] for p in a}
    sb = {p["asin"]: p["opportunity_score"] for p in b}
    assert sa == sb
    assert scoring.pick_top3(a)["asins"] == scoring.pick_top3(b)["asins"]


def test_top3_dedupes_similar_products_keeping_best():
    fleet = copy.deepcopy(_fleet())
    scoring.apply(fleet, TODAY)
    top3 = scoring.pick_top3(fleet)
    # B and C are near-identical neck fans; only the higher-scoring one stays
    assert not ({"B00000000B", "B00000000C"} <= set(top3["asins"]))
    assert len(top3["asins"]) == 3


def test_top3_never_pads_with_unqualified():
    fleet = [
        copy.deepcopy(_fleet()[0]),
        _p(asin="B00000000Z", ratings_count=2, surge=None,
           sources=[{"list": "bestsellers", "category": "home", "rank": 99}]),
    ]
    scoring.apply(fleet, TODAY)
    top3 = scoring.pick_top3(fleet)
    assert top3["asins"] == ["B00000000A"]
    assert top3["qualified_count"] == 1  # honest count, no low-quality padding
