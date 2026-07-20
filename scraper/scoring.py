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


def store_fit(p):
    """(tier, group_zh) from product FORM keywords in the title.

    Precedence low > high > mid: recommending a non-fit product costs real
    money, so the conservative tier wins on conflicting matches.
    """
    title = _title_lower(p)
    for tier in ("low", "high", "mid"):
        best = None  # (position, group_zh): earliest keyword hit names the group
        for group in cfg.STORE_FIT_TIERS[tier]:
            for k in group["keywords"]:
                pos = title.find(k)
                if pos >= 0 and (best is None or pos < best[0]):
                    best = (pos, group["zh"])
        if best:
            return tier, best[1]
    return "neutral", None


def store_fit_reason_zh_for(p) -> str:
    tier, group = store_fit(p)
    if tier == "neutral":
        cats = sorted({s["category"] for s in p.get("sources", [])})
        zh = "/".join(cfg.CATEGORY_ZH.get(c, c) for c in cats)
        return cfg.STORE_FIT_REASON_ZH["neutral"].format(cat=zh or "未知")
    return cfg.STORE_FIT_REASON_ZH[tier].format(group=group)


def fit_score(p) -> float:
    """0..MAX_FIT: store-fit form tier (10) + small-batch price band (10).

    Amazon's big category is only a weak prior, used when no form matches.
    """
    tier, _ = store_fit(p)
    if tier == "neutral":
        cats = {s["category"] for s in p.get("sources", [])}
        tier_pts = max((cfg.CATEGORY_FIT.get(c, 0.5) for c in cats), default=0.5) * 4
    else:
        tier_pts = cfg.STORE_FIT_POINTS[tier]
    price = parse_price(p.get("price"))
    if price is None:
        price_factor = 0.0
    else:
        price_factor = next(
            (f for lo, hi, f in cfg.PRICE_BANDS if lo <= price < hi), 0.1
        )
    return round(tier_pts + price_factor * 10, 1)


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
    if store_fit(p)[0] == "low":
        pts += cfg.PENALTY_LOW_STORE_FIT
        codes.append("LOW_STORE_FIT")
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
            return f"评论仅{p.get('ratings_count') or 0}条，需求规模未验证"
        if code == "LOW_STORE_FIT":
            _, group = store_fit(p)
            return f"属于「{group}」，{cfg.RISK_ZH['LOW_STORE_FIT']}"
        return cfg.RISK_ZH.get(code, cfg.RISK_LOCAL_ZH)
    # no hard flaw in platform data — still name the most relevant SPECIFIC risk
    title = _title_lower(p)
    if _contains_any(title, cfg.SEASONAL_KEYWORDS):
        specific = cfg.RISK_SEASONAL_ZH
    elif (parse_price(p.get("price")) or 0) >= 25:
        specific = cfg.RISK_MARGIN_ZH
    elif (p.get("ratings_count") or 0) < 200:
        specific = cfg.RISK_SAMPLE_ZH
    elif any(s["category"] in ("home", "kitchen", "sports") for s in p.get("sources", [])):
        specific = cfg.RISK_SHIPPING_ZH
    else:
        specific = cfg.RISK_LOCAL_ZH
    return f"{cfg.NO_RISK_PREFIX}；{specific}"


_ASCII_RUN = re.compile(r"[A-Za-z][A-Za-z0-9&'’.\-]*")


def procurement_keyword(title_zh):
    """Sourcing keyword for 1688: brands/marketing gone, form+material+spec kept.

    Deterministic text surgery on the machine-translated title — no LLM.
    Returns None when nothing usable remains (caller falls back to keyword_zh).
    """
    if not title_zh:
        return None

    def _keep(m):
        tok = m.group(0)
        return tok if tok.upper() in cfg.PROCUREMENT_ASCII_KEEP else " "

    text = _ASCII_RUN.sub(_keep, title_zh)
    for b in cfg.BRAND_ZH:
        text = text.replace(b, " ")
    for w in cfg.PROCUREMENT_STRIP_ZH + cfg.PROCUREMENT_STRIP_ZH_EXTRA:
        text = text.replace(w, " ")
    text = re.sub(r"[|,，。.:：;；()（）\[\]【】/\\\-–—_+~!！?？'\"“”]+", " ", text)
    for src, dst in cfg.PROCUREMENT_REWRITE_ZH.items():  # 翻译腔 → 行业用语
        text = text.replace(src, dst)
    text = " ".join(text.split())
    # no dangling particles left by brand removal ("MGA的…" → "的…")
    text = re.sub(r"^[的与和及之\s]+|[的与和及之\s]+$", "", text)
    text = re.sub(r"的\s+", "的", text)  # "带水钻的 套件" → "带水钻的套件"
    # "2 件套" → "2件套": no space between digits and CJK
    text = re.sub(r"(?<=[0-9])\s+(?=[一-鿿])", "", text)
    text = re.sub(r"(?<=[一-鿿])\s+(?=[0-9])", "", text)
    if len(text.replace(" ", "")) > cfg.PROCUREMENT_MAX_LEN:
        out, ln = [], 0
        for part in text.split(" "):
            if ln + len(part) > cfg.PROCUREMENT_MAX_LEN:
                break
            out.append(part)
            ln += len(part)
        text = " ".join(out) if out else text.replace(" ", "")[: cfg.PROCUREMENT_MAX_LEN]
    compact_len = len(text.replace(" ", ""))
    if compact_len < 4:
        return None  # unusable残渣
    return text.strip()


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
        "store_fit_reason_zh": store_fit_reason_zh_for(p),
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

    def _key_scores(p):
        b = p["score_breakdown"]
        return (
            p["opportunity_score"],
            b.get("fit", 0),
            b.get("trend", 0),
            b.get("market", 0),
            b.get("multi_signal", 0),
        )

    # ties resolved by BUSINESS priority (fit > trend > market > multi-signal);
    # ASIN is only the final stability anchor, never a meaningful rank
    qualified.sort(key=lambda p: tuple(-v for v in _key_scores(p)) + (p["asin"],))
    picked, picked_tokens = [], []
    for p in qualified:
        toks = title_tokens(p.get("title_en"))
        if any(_jaccard(toks, t) >= cfg.SIMILARITY_JACCARD for t in picked_tokens):
            continue
        picked.append(p)
        picked_tokens.append(toks)
    top = picked[:3]
    tied = [
        i > 0 and _key_scores(top[i]) == _key_scores(top[i - 1])
        for i in range(len(top))
    ]
    return {
        "asins": [p["asin"] for p in top],
        "tied": tied,
        "qualified_count": len(picked),
    }
