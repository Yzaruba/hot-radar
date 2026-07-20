"""Config for the review enrichment layer — no logic, only data/limits."""

# ---- run limits (per enrichment run) ----
MAX_ASINS_PER_RUN = 20
MAX_REVIEWS_PER_ASIN = 50
MAX_RETRIES_PER_ASIN = 1
CACHE_DAYS = 7
REFRESH_GROWTH_PCT = 20        # early refresh if review count grew this much
REQUEST_DELAY_RANGE = (2, 4)   # seconds between product fetches

# ---- provider selection (env-driven; never hardcode keys) ----
ENV_PROVIDER = "REVIEWS_PROVIDER"      # none | amazon_page | rainforest
ENV_API_KEY = "REVIEWS_API_KEY"
DEFAULT_PROVIDER = "amazon_page"       # our existing scraping capability

SCHEMA_VERSION = "review_summary.v1"

# ---- deterministic aspect lexicon: EN review keywords → zh theme label ----
# A review sentence hits a theme if any keyword appears (lowercase substring).
# Positive bucket = reviews rated >=4; negative bucket = rated <=2.
ASPECTS = [
    {"zh": "质量做工", "keywords": [
        "quality", "well made", "well-made", "sturdy", "solid", "cheaply made",
        "flimsy", "broke", "broken", "fell apart", "cracked", "ripped", "tear",
        "durable", "poor quality"]},
    {"zh": "尺寸大小", "keywords": [
        "size", "smaller than", "bigger than", "too small", "too big", "tiny",
        "huge", "fits", "fit perfectly", "dimensions"]},
    {"zh": "外观颜色", "keywords": [
        "color", "colours", "beautiful", "cute", "adorable", "looks great",
        "looks cheap", "faded", "design", "pretty", "aesthetic"]},
    {"zh": "好用易用", "keywords": [
        "easy to use", "easy to", "simple", "convenient", "works great",
        "works well", "doesn't work", "does not work", "stopped working",
        "hard to use", "difficult to"]},
    {"zh": "孩子喜欢", "keywords": [
        "my kid", "my son", "my daughter", "kids love", "children", "grandson",
        "granddaughter", "my child", "loves it", "loves them"]},
    {"zh": "性价比", "keywords": [
        "worth", "value", "price", "cheap", "expensive", "overpriced",
        "great deal", "money"]},
    {"zh": "电池续航", "keywords": [
        "battery", "charge", "charging", "died", "lasts", "won't charge",
        "power"]},
    {"zh": "气味", "keywords": [
        "smell", "odor", "scent", "stink", "chemical smell", "fragrance"]},
    {"zh": "粘性/贴合", "keywords": [
        "sticky", "stick", "adhesive", "won't stay", "falls off", "stays on"]},
    {"zh": "物流包装", "keywords": [
        "packaging", "arrived", "shipping", "damaged in", "box was", "missing",
        "came with"]},
    {"zh": "如图相符", "keywords": [
        "as described", "as pictured", "not as described", "misleading",
        "exactly what", "different from picture"]},
    {"zh": "耐用性", "keywords": [
        "lasted", "still going", "wore out", "stopped after", "day one",
        "week later", "month later", "returned it", "refund"]},
]

MAX_THEMES_EACH = 5
MIN_THEME_COUNT = 2   # relaxed to 1 automatically when sample is small (<8)

# ---- 采购判断 verdict thresholds (on sampled real reviews only) ----
VERDICT_MIN_SAMPLE = 5
VERDICT_NEG_LOW = 0.15
VERDICT_NEG_MID = 0.35
