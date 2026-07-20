"""Review enrichment: pluggable providers + cache + deterministic zh summaries.

Hard rules (see spec): summaries come ONLY from real fetched review text.
No guessing from titles, no fabricated "buyers say", no captcha bypassing.
When no real data is available the output status says so and the UI shows
"评论数据暂不可用" — never plausible-looking fake reviews.
"""
import json
import os
import re
from datetime import timedelta

from bs4 import BeautifulSoup

from . import config, reviews_config as rcfg
from .util import iso, log, now_utc, read_json, write_json

RAW_DIR = config.DATA_DIR / "reviews"
PUB_DIR = config.SITE_DATA / "reviews"


# ---------- provider layer ----------

class ProviderResult:
    def __init__(self, status, reviews=None, total_review_count=None, rating=None,
                 source_url=None, error_code=None):
        self.status = status              # ready | unavailable | failed | unconfigured
        self.reviews = reviews or []      # [{rating: float, title: str, text: str}]
        self.total_review_count = total_review_count
        self.rating = rating
        self.source_url = source_url
        self.error_code = error_code


class NoneProvider:
    """Safe no-op when no review source is configured."""

    name = "none"

    def fetch_reviews(self, asin):
        return ProviderResult("unconfigured", error_code="no_provider_configured")


class AmazonPageProvider:
    """Public amazon.com/dp/{asin} page reviews.

    Live probe 2026-07-20: dp pages no longer server-render review TEXT
    anonymously (the review widget stays empty even after scroll+wait), and
    /product-reviews/ is a login wall. So today this provider honestly returns
    `unavailable` — it stays enabled as a daily canary: if Amazon re-renders
    reviews, summaries start flowing automatically. Never touches captchas or
    login walls; a blocked/empty page is reported as unavailable, full stop.
    """

    name = "amazon_page"

    def __init__(self, browser):
        self._browser = browser

    def fetch_reviews(self, asin):
        url = f"https://www.amazon.com/dp/{asin}"
        page = self._browser.new_page(
            user_agent=config.UA, locale="en-US", viewport={"width": 1280, "height": 900}
        )
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(1500)
            html = page.content()
        except Exception as e:  # noqa: BLE001
            return ProviderResult("failed", source_url=url, error_code=f"nav:{e.__class__.__name__}")
        finally:
            page.close()
        if "captcha" in html[:20000].lower():
            return ProviderResult("unavailable", source_url=url, error_code="bot_check_page")
        reviews, total, rating = parse_dp_reviews(html)
        if not reviews:
            return ProviderResult("unavailable", source_url=url, error_code="no_reviews_rendered")
        return ProviderResult(
            "ready", reviews=reviews[: rcfg.MAX_REVIEWS_PER_ASIN],
            total_review_count=total, rating=rating, source_url=url,
        )


class RainforestProvider:
    """External API adapter (untested until a key is provided; env-configured)."""

    name = "rainforest"

    def __init__(self, api_key):
        self._key = api_key

    def fetch_reviews(self, asin):
        import httpx

        if not self._key:
            return ProviderResult("unconfigured", error_code="missing_api_key")
        try:
            r = httpx.get(
                "https://api.rainforestapi.com/request",
                params={"api_key": self._key, "type": "reviews",
                        "amazon_domain": "amazon.com", "asin": asin},
                timeout=60,
            )
            r.raise_for_status()
            j = r.json()
        except Exception as e:  # noqa: BLE001
            return ProviderResult("failed", error_code=f"api:{e.__class__.__name__}")
        raw = j.get("reviews") or []
        reviews = [
            {"rating": float(x.get("rating") or 0),
             "title": (x.get("title") or "").strip(),
             "text": (x.get("body") or "").strip()}
            for x in raw if x.get("body")
        ]
        summary = j.get("summary") or {}
        if not reviews:
            return ProviderResult("unavailable", error_code="empty_api_response")
        return ProviderResult(
            "ready", reviews=reviews[: rcfg.MAX_REVIEWS_PER_ASIN],
            total_review_count=(summary.get("reviews_total")),
            rating=(summary.get("rating")),
            source_url=f"https://www.amazon.com/product-reviews/{asin}",
        )


def make_provider(browser=None, env=None):
    env = os.environ if env is None else env
    name = (env.get(rcfg.ENV_PROVIDER) or rcfg.DEFAULT_PROVIDER).strip().lower()
    if name == "amazon_page" and browser is not None:
        return AmazonPageProvider(browser)
    if name == "rainforest":
        return RainforestProvider(env.get(rcfg.ENV_API_KEY, ""))
    return NoneProvider()


# ---------- dp page parsing ----------

def _rating_from_text(text):
    m = re.search(r"([\d.]+)\s+out of 5", text or "")
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


def parse_dp_reviews(html):
    """(reviews, total_review_count, rating) from a product detail page."""
    soup = BeautifulSoup(html, "html.parser")
    reviews = []
    for block in soup.select('[data-hook="review"]'):
        star_el = block.select_one('[data-hook="review-star-rating"] .a-icon-alt') or \
            block.select_one('[data-hook="cmps-review-star-rating"] .a-icon-alt')
        body_el = block.select_one('[data-hook="review-body"]')
        title_el = block.select_one('[data-hook="review-title"]')
        rating = _rating_from_text(star_el.get_text() if star_el else "")
        text = body_el.get_text(" ", strip=True) if body_el else ""
        if rating is None or not text:
            continue
        title = title_el.get_text(" ", strip=True) if title_el else ""
        # review-title often embeds the star text; strip it
        title = re.sub(r"^[\d.]+ out of 5 stars\s*", "", title)
        reviews.append({"rating": rating, "title": title, "text": text})
    total = None
    total_el = soup.select_one('[data-hook="total-review-count"]')
    if total_el:
        m = re.search(r"[\d,]+", total_el.get_text())
        if m:
            total = int(m.group(0).replace(",", ""))
    rating_el = soup.select_one('[data-hook="rating-out-of-text"]') or \
        soup.select_one("#acrPopover .a-icon-alt")
    rating = _rating_from_text(rating_el.get_text() if rating_el else "")
    return reviews, total, rating


# ---------- deterministic zh summarization (real text only) ----------

def _themes(reviews):
    pos_counts, neg_counts = {}, {}
    for rv in reviews:
        text = f"{rv.get('title', '')} {rv.get('text', '')}".lower()
        bucket = None
        if rv["rating"] >= 4:
            bucket = pos_counts
        elif rv["rating"] <= 2:
            bucket = neg_counts
        if bucket is None:
            continue
        for aspect in rcfg.ASPECTS:
            if any(k in text for k in aspect["keywords"]):
                bucket[aspect["zh"]] = bucket.get(aspect["zh"], 0) + 1
    return pos_counts, neg_counts


def _top_themes(counts, sample_count):
    min_count = 1 if sample_count < 8 else rcfg.MIN_THEME_COUNT
    order = {a["zh"]: i for i, a in enumerate(rcfg.ASPECTS)}
    items = [(zh, c) for zh, c in counts.items() if c >= min_count]
    items.sort(key=lambda x: (-x[1], order[x[0]]))
    return [{"zh": zh, "count": c} for zh, c in items[: rcfg.MAX_THEMES_EACH]]


def _verdict_zh(reviews, neg_themes):
    n = len(reviews)
    if n < rcfg.VERDICT_MIN_SAMPLE:
        return f"样本太少（仅{n}条），判断参考性有限，先小批试"
    neg = sum(1 for r in reviews if r["rating"] <= 2)
    share = neg / n
    if share <= rcfg.VERDICT_NEG_LOW:
        return f"样本差评率低（{neg}/{n}），可小批进货验证"
    if share <= rcfg.VERDICT_NEG_MID:
        top = neg_themes[0]["zh"] if neg_themes else "个别问题"
        return f"差评集中在「{top}」（{neg}/{n}），进货前重点确认这一点"
    return f"样本差评偏多（{neg}/{n}），不建议现在进"


def summarize(reviews):
    """summary_zh from REAL review texts only. Empty input → None (no faking)."""
    if not reviews:
        return None
    pos_counts, neg_counts = _themes(reviews)
    n = len(reviews)
    neg_themes = _top_themes(neg_counts, n)
    return {
        "positive_themes": _top_themes(pos_counts, n),
        "negative_themes": neg_themes,
        "procurement_verdict_zh": _verdict_zh(reviews, neg_themes),
        "basis_zh": f"基于{n}条真实Amazon评论样本自动归纳",
    }


def star_distribution(reviews):
    dist = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
    for r in reviews:
        key = str(int(round(r["rating"])))
        if key in dist:
            dist[key] += 1
    return dist


# ---------- cache ----------

def cache_paths(asin):
    return RAW_DIR / f"{asin}.raw.json", PUB_DIR / f"{asin}.json"


def cache_is_fresh(pub, now, current_review_count=None):
    """True if the published summary is still valid (no refetch needed)."""
    if not pub or pub.get("status") != "ready":
        return False
    try:
        from datetime import datetime, timezone

        exp = datetime.strptime(pub["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError):
        return False
    if now >= exp:
        return False
    cached_total = pub.get("total_review_count")
    if current_review_count and cached_total:
        if current_review_count > cached_total * (1 + rcfg.REFRESH_GROWTH_PCT / 100):
            return False  # review volume jumped — worth an early refresh
    return True


def build_summary_doc(asin, result, now):
    doc = {
        "schema_version": rcfg.SCHEMA_VERSION,
        "asin": asin,
        "provider": getattr(result, "provider_name", None) or result.__class__.__name__,
        "source_url": result.source_url,
        "fetched_at": iso(now),
        "expires_at": iso(now + timedelta(days=rcfg.CACHE_DAYS)),
        "status": result.status,
        "rating": result.rating,
        "total_review_count": result.total_review_count,
        "sample_count": len(result.reviews),
        "star_distribution_sample": star_distribution(result.reviews) if result.reviews else None,
        "summary_zh": summarize(result.reviews),
        "error_code": result.error_code,
    }
    return doc


def save_result(asin, provider_name, result, now):
    raw_path, pub_path = cache_paths(asin)
    doc = build_summary_doc(asin, result, now)
    doc["provider"] = provider_name
    write_json(pub_path, doc)
    if result.reviews:
        # raw texts stay in the non-deployed data/ dir (not republished verbatim)
        write_json(raw_path, {
            "asin": asin, "provider": provider_name, "fetched_at": iso(now),
            "source_url": result.source_url, "reviews": result.reviews,
        })
    return doc


def load_published(asin):
    return read_json(cache_paths(asin)[1])


def preserve_or_save(asin, provider_name, result, now):
    """Persist a fetch outcome without ever destroying real data.

    Non-ready result + an existing real summary → keep it, honestly marked
    stale. Returns the recorded status string.
    """
    if result.status != "ready":
        prev = load_published(asin)
        if prev and prev.get("summary_zh"):
            prev["status"] = "stale"
            write_json(cache_paths(asin)[1], prev)
            return "stale_kept"
    save_result(asin, provider_name, result, now)
    return result.status
