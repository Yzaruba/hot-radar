"""Tunable knobs for the Goodies opportunity score — no logic, only config.

Adjust weights/lists here; scoring.py stays untouched. Everything is plain data
so the algorithm remains deterministic and testable.
"""

# ---- component ceilings (must sum to 100) ----
MAX_TREND = 35
MAX_MARKET = 20
MAX_FRESH = 15
MAX_FIT = 20
MAX_MULTI = 10

# ---- Goodies fit: category affinity for a tourist gift shop (0..1) ----
CATEGORY_FIT = {
    "toys": 1.0,
    "beauty": 1.0,
    "kitchen": 0.9,
    "electronics": 0.85,
    "sports": 0.8,
    "home": 0.7,
}

# ---- Goodies fit: retail price bands (USD) for small-batch sourcing ----
# (lo, hi, factor) — first matching band wins
PRICE_BANDS = [
    (3.0, 40.0, 1.0),    # sweet spot: impulse-buy tourist pricing
    (40.0, 80.0, 0.6),
    (1.0, 3.0, 0.5),     # too cheap to matter
    (80.0, 150.0, 0.3),
    (0.0, 1.0, 0.2),
    (150.0, float("inf"), 0.1),
]

# ---- market validation ----
MIN_REVIEWS = 10          # below this the market score is capped hard…
LOW_REVIEW_CAP = 3        # …at this many points
RATING_FACTORS = [        # (min_rating, factor); first match wins; None rating → NO_RATING
    (4.5, 1.0),
    (4.0, 0.85),
    (3.5, 0.6),
    (0.0, 0.3),
]

# ---- freshness window (days since first_seen) ----
FRESH_DAYS = [(3, 8), (7, 5), (14, 3)]   # (within_days, points)
NEW_RELEASE_POINTS = 7

# ---- risk deductions (negative) ----
PENALTY_LOW_REVIEWS = -8
PENALTY_NO_PRICE = -5
PENALTY_NO_RATING = -5
PENALTY_BRAND = -10
PENALTY_BULKY = -10
HIGH_RISK_PENALTY_THRESHOLD = -10   # at/below this + low score → 高风险

# ---- recommendation thresholds ----
QUALIFY_MIN_SCORE = 55      # 推荐标准：达到才可能进 Top 3
IMMEDIATE_MIN_SCORE = 70    # 立即找货（还需 high confidence）
WATCH_MIN_SCORE = 40        # 继续观察下限

# ---- Top 3 similarity dedup ----
SIMILARITY_JACCARD = 0.5
TITLE_STOPWORDS = {
    "for", "with", "the", "and", "of", "in", "to", "a", "an", "by", "on",
    "pack", "set", "count", "pcs", "piece", "pieces", "oz", "inch", "ft",
    "new", "2025", "2026", "gift", "gifts", "women", "men", "kids", "adult",
}

# ---- brand / IP products (hard to source legitimately on 1688) ----
BRAND_KEYWORDS = [
    "apple", "iphone", "ipad", "airpods", "samsung", "anker", "soundcore",
    "jbl", "bose", "sony", "nintendo", "playstation", "xbox", "pokemon",
    "pokémon", "disney", "marvel", "star wars", "barbie", "hot wheels",
    "lego", "stanley", "yeti", "owala", "hydro flask", "crocs", "nike",
    "adidas", "wilson", "spalding", "medicube", "neutrogena", "garnier",
    "cerave", "cetaphil", "la roche-posay", "l'oreal", "loreal", "olaplex",
    "maybelline", "e.l.f", "elf cosmetics", "laneige", "cosrx", "duolingo",
    "national geographic", "harry potter", "minecraft", "roblox", "sanrio",
    "hello kitty", "squishmallows", "ninja", "keurig", "cuisinart",
    "kitchenaid", "instant pot", "dyson", "shark", "bissell", "oral-b",
    "philips", "braun", "gillette", "colgate", "crest", "listerine",
    "crayola", "olay", "band-aid", "sharpie", "elmer's", "play-doh",
]

# ---- hard exclusions: medication / prescription-adjacent (never recommend) ----
# NB: verified against real data 2026-07-20 — bare "medicine" hit a mini fridge
# ("medicine storage") and "collagen peptides" hit topical serums; keep terms
# specific to ingestible drugs so cosmetics/appliances are not swept up.
EXCLUDE_KEYWORDS = [
    "prescription", "medication", "cold medicine", "cough medicine",
    "allergy medicine", "pharmacy", "antibiotic",
    "insulin", "inhaler", "syringe", "ibuprofen", "acetaminophen", "aspirin",
    "naproxen", "nicotine", "melatonin", "laxative", "antacid", "antihistamine",
    "benadryl", "tylenol", "advil", "zyrtec", "pepto", "dramamine", "supplement",
    "vitamin d", "vitamin c gummies", "probiotics", "creatine",
]

# ---- bulky / hard-to-ship to Aruba ----
BULKY_KEYWORDS = [
    "refrigerator", "freezer", "washer", "dryer", "dishwasher", "microwave",
    "air conditioner", "treadmill", "elliptical", "exercise bike", "sofa",
    "couch", "mattress", "bed frame", "bookshelf", "dresser", "wardrobe",
    "desk ", "office chair", "gaming chair", "tv stand", "dining table",
    "patio ", "grill ", "lawn mower", "generator", "kayak", "paddle board",
    "trampoline", "basketball hoop", "55 inch", "65 inch", "75 inch",
]

# ---- reason code → Chinese phrases ----
RISK_ZH = {
    "EXCLUDED_MEDICAL": "药品/医疗类，不做",
    "BRAND_PRODUCT": "品牌/IP商品，1688拿货有仿品和侵权风险",
    "BULKY_ITEM": "体积大运输难，不适合Aruba补货",
    "LOW_REVIEWS": "评论太少，需求还没被验证",
    "NO_PRICE": "价格缺失，毛利没法预估",
    "NO_RATING": "暂无评分，质量未知",
    "DUPLICATE_KIND": "与更高分同类商品重复",
}
DEFAULT_RISK_ZH = "无明显硬伤；下单前用Google Trends验证热度持续性"
