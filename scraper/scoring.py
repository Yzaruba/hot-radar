"""Goodies opportunity score — deterministic, config-driven, no network, no LLM.

Same input data → same scores → same ordering. All tunables live in
scoring_config.py. Applied by build.py after products are assembled.
"""
import re
from datetime import date, datetime

from . import scoring_config as cfg


# ---------- helpers ----------

def parse_price(price_str):
    """'$12.99' / 'AWG 21.70' / '1,299.00' → float, else None."""
    if not price_str:
        return None
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", str(price_str))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _title_lower(p) -> str:
    return (p.get("title_en") or "").lower()


def _contains_any(text, keywords) -> bool:
    return any(k in text for k in keywords)


def title_tokens(title_en) -> frozenset:
    words = re.findall(r"[a-z0-9]+", (title_en or "").lower())
    return frozenset(w for w in words if len(w) >= 3 and w not in cfg.TITLE_STOPWORDS)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _best_rank(p, kind="bestsellers"):
    ranks = [s["rank"] for s in p.get("sources", []) if s["list"] == kind]
    return min(ranks) if ranks else None


# ---------- score components ----------

def trend_score(p) -> float:
    """0..MAX_TREND from surge movement AND absolute rank (never pct alone)."""
    s = p.get("surge")
    if s:
        rank = s["rank"]
        rank_part = max(0.0, (50 - rank)) / 50 * 10          # up to 10 for top ranks
        if s.get("is_new_entry"):
            return round(min(cfg.MAX_TREND, 12 + 8 + rank_part), 1)
        pct_part = min(s.get("rank_pct") or 0, 100) / 100 * 15   # up to 15
        delta_part = min(s.get("rank_delta") or 0, 60) / 60 * 10  # up to 10
        return round(min(cfg.MAX_TREND, pct_part + delta_part + rank_part), 1)
    # no movement data: a very high steady bestseller rank earns a little
    rank = _best_rank(p, "bestsellers")
    if rank is not None and rank <= 20:
        return round((20 - rank) / 20 * 8, 1)
    return 0.0


def market_score(p) -> float:
    """0..MAX_MARKET from rating × review volume; <MIN_REVIEWS is hard-capped."""
    count = p.get("ratings_count") or 0
    rating = p.get("rating")
    if count < cfg.MIN_REVIEWS:
        return float(min(cfg.LOW_REVIEW_CAP, count * 0.3))
    # log10 volume: 10→4, 100→8, 1k→12, 10k→16, 100k+→20
    import math

    volume = min(cfg.MAX_MARKET, 4 * math.log10(count))
    if rating is None:
        return round(volume * 0.4, 1)
    factor = next(f for lo, f in cfg.RATING_FACTORS if rating >= lo)
    return round(volume * factor, 1)


def fresh_score(p, today: date) -> float:
    """0..MAX_FRESH: new-releases presence + how recently first seen."""
    pts = 0.0
    if any(s["list"] == "new-releases" for s in p.get("sources", [])):
        pts += cfg.NEW_RELEASE_POINTS
    fs = p.get("first_seen")
    if fs:
        try:
            days = (today - datetime.strptime(fs, "%Y-%m-%d").date()).days
            for within, points in cfg.FRESH_DAYS:
                if days <= within:
                    pts += points
                    break
        except ValueError:
            pass
    return min(float(cfg.MAX_FRESH), pts)


def fit_score(p) -> float:
    """0..MAX_FIT: category affinity (10) + small-batch price band (10)."""
    cats = {s["category"] for s in p.get("sources", [])}
    cat_factor = max((cfg.CATEGORY_FIT.get(c, 0.5) for c in cats), default=0.5)
    price = parse_price(p.get("price"))
    if price is None:
        price_factor = 0.0
    else:
        price_factor = next(
            (f for lo, hi, f in cfg.PRICE_BANDS if lo <= price < hi), 0.1
        )
    return round(cat_factor * 10 + price_factor * 10, 1)


def multi_signal_score(p) -> float:
    """0..MAX_MULTI: distinct Amazon list placements; TikTok only assists."""
    n_sources = len(p.get("sources", []))
    pts = 0.0
    if n_sources >= 3:
        pts += 8
    elif n_sources == 2:
        pts += 5
    if (p.get("signals") or {}).get("tiktok"):
        pts += 2  # auxiliary only — can never carry a product by itself
    return min(float(cfg.MAX_MULTI), pts)


# ---------- risks ----------

def is_excluded(p) -> bool:
    return _contains_any(_title_lower(p), cfg.EXCLUDE_KEYWORDS)


def risk_deductions(p):
    """(negative_points, [codes])"""
    title = _title_lower(p)
    pts, codes = 0, []
    if (p.get("ratings_count") or 0) < cfg.MIN_REVIEWS:
        pts += cfg.PENALTY_LOW_REVIEWS
        codes.append("LOW_REVIEWS")
    if parse_price(p.get("price")) is None:
        pts += cfg.PENALTY_NO_PRICE
        codes.append("NO_PRICE")
    if p.get("rating") is None:
        pts += cfg.PENALTY_NO_RATING
        codes.append("NO_RATING")
    if _contains_any(title, cfg.BRAND_KEYWORDS):
        pts += cfg.PENALTY_BRAND
        codes.append("BRAND_PRODUCT")
    if _contains_any(title, cfg.BULKY_KEYWORDS):
        pts += cfg.PENALTY_BULKY
        codes.append("BULKY_ITEM")
    return pts, codes


def confidence_for(p, risk_codes) -> str:
    if "NO_PRICE" in risk_codes or "NO_RATING" in risk_codes or "LOW_REVIEWS" in risk_codes:
        return "low"
    if (p.get("ratings_count") or 0) >= 50:
        return "high"
    return "medium"


def recommendation_for(score, confidence, risk_pts, excluded) -> str:
    if excluded:
        return "高风险"
    if score < cfg.QUALIFY_MIN_SCORE and risk_pts <= cfg.HIGH_RISK_PENALTY_THRESHOLD:
        return "高风险"
    if score >= cfg.IMMEDIATE_MIN_SCORE and confidence == "high":
        return "立即找货"
    if score >= cfg.QUALIFY_MIN_SCORE and confidence in ("high", "medium"):
        return "小批测试"
    if score >= cfg.WATCH_MIN_SCORE:
        return "继续观察"
    return "继续观察"


# ---------- chinese one-liners (templates, no LLM) ----------

def reason_zh_for(p, breakdown) -> str:
    parts = []
    s = p.get("surge")
    if s:
        if s.get("is_new_entry"):
            parts.append("新杀入畅销榜Top100")
        else:
            parts.append(f"24小时排名{s['rank_prev']}→{s['rank']}(↑{round(s['rank_pct'] or 0)}%)")
    n_sources = len(p.get("sources", []))
    if n_sources >= 2:
        parts.append(f"同时上{n_sources}个榜")
    count = p.get("ratings_count") or 0
    if count >= 1000 and p.get("rating"):
        parts.append(f"{count:,}条评论·{p['rating']}分")
    price = parse_price(p.get("price"))
    if price is not None and 3 <= price < 40:
        parts.append(f"{p['price']}适合小批进货")
    if not parts:
        rank = _best_rank(p, "bestsellers")
        parts.append(f"畅销榜稳定第{rank}名" if rank else "榜单在售商品")
    return "，".join(parts[:2])


def primary_risk_zh_for(p, risk_codes) -> str:
    if risk_codes:
        code = risk_codes[0]
        if code == "LOW_REVIEWS":
            return f"评论仅{p.get('ratings_count') or 0}条，需求还没被验证"
        return cfg.RISK_ZH.get(code, cfg.DEFAULT_RISK_ZH)
    return cfg.DEFAULT_RISK_ZH


# ---------- main entry points ----------

def score_product(p, today: date) -> dict:
    excluded = is_excluded(p)
    breakdown = {
        "trend": trend_score(p),
        "market": market_score(p),
        "fresh": fresh_score(p, today),
        "fit": fit_score(p),
        "multi_signal": multi_signal_score(p),
    }
    risk_pts, risk_codes = risk_deductions(p)
    if excluded:
        risk_codes = ["EXCLUDED_MEDICAL"] + risk_codes
    breakdown["risk"] = float(risk_pts)
    raw = sum(v for k, v in breakdown.items() if k != "risk") + risk_pts
    score = 0.0 if excluded else round(max(0.0, min(100.0, raw)), 1)
    confidence = "low" if excluded else confidence_for(p, risk_codes)
    return {
        "opportunity_score": score,
        "confidence": confidence,
        "recommendation": recommendation_for(score, confidence, risk_pts, excluded),
        "reason_codes": risk_codes,
        "reason_zh": reason_zh_for(p, breakdown),
        "primary_risk_zh": primary_risk_zh_for(p, risk_codes),
        "score_breakdown": breakdown,
    }


def apply(products, today: date) -> None:
    """Mutate each product with its score fields. Deterministic."""
    for p in products:
        p.update(score_product(p, today))


def pick_top3(products) -> dict:
    """Qualified = score/recommendation gate; near-duplicates keep only the
    highest-scoring representative. Returns {'asins': [...], 'qualified_count': n}.
    """
    qualified = [
        p
        for p in products
        if p["opportunity_score"] >= cfg.QUALIFY_MIN_SCORE
        and p["recommendation"] in ("立即找货", "小批测试")
    ]
    qualified.sort(key=lambda p: (-p["opportunity_score"], p["asin"]))
    picked, picked_tokens = [], []
    for p in qualified:
        toks = title_tokens(p.get("title_en"))
        if any(_jaccard(toks, t) >= cfg.SIMILARITY_JACCARD for t in picked_tokens):
            continue
        picked.append(p)
        picked_tokens.append(toks)
    return {
        "asins": [p["asin"] for p in picked[:3]],
        "qualified_count": len(picked),
    }
