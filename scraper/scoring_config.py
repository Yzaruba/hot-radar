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
# Weak prior only — the store-fit form-factor tiers below dominate.
CATEGORY_FIT = {
    "toys": 1.0,
    "beauty": 1.0,
    "kitchen": 0.9,
    "electronics": 0.85,
    "sports": 0.8,
    "home": 0.7,
}

# ---- Goodies store fit: product FORM detected from title keywords ----
# Amazon's big categories are too coarse ("home" contains both moving bags and
# cute night lights). Tier precedence when several match: low > high > mid —
# conservative, because recommending a non-fit product costs real money.
STORE_FIT_TIERS = {
    "high": [
        {"zh": "潮流玩具/捏捏乐/收藏小玩意", "keywords": [
            "squishy", "fidget", "squeeze", "stress relief", "sensory",
            "plush", "figurine", "collectible", "blind box", "mystery box",
            "slime", "pop it", "capybara", "keycap"]},
        {"zh": "手机配件/小电子", "keywords": [
            "phone case", "phone charm", "phone holder", "phone stand",
            "charger", "charging cable", "power bank", "earbuds case",
            "selfie", "phone strap", "cable protector", "airtag holder"]},
        {"zh": "美妆个护/美甲", "keywords": [
            "nail", "press on", "makeup", "lip gloss", "lip balm", "lash",
            "eyeliner", "blush", "hair clip", "claw clip", "scrunchie",
            "hair tie", "face mask sheet", "pimple patch"]},
        {"zh": "文具/DIY手工材料", "keywords": [
            "rhinestone", "diy kit", "craft kit", "sticker", "stationery",
            "gel pen", "beads", "bracelet making", "diamond painting",
            "scrapbook", "washi tape", "coloring", "origami", "clay kit"]},
        {"zh": "礼品/钥匙扣/小装饰", "keywords": [
            "keychain", "key ring", "ornament", "charm", "night light",
            "gift for", "lanyard", "magnet", "snow globe", "wind chime",
            "suncatcher", "desk toy"]},
        {"zh": "旅行/沙滩小物", "keywords": [
            "beach", "travel size", "travel bottle", "luggage tag",
            "waterproof pouch", "waterproof phone", "snorkel", "swim",
            "sunglasses", "neck fan", "portable fan", "hand fan",
            "insulated cup", "cooling towel", "sunscreen applicator"]},
        {"zh": "可定制空白品(Workshop)", "keywords": [
            "sublimation", "blank ", "custom ", "personalized", "engraving blank"]},
    ],
    "mid": [
        {"zh": "小型厨房创意用品", "keywords": [
            "kitchen gadget", "silicone mold", "ice cube tray", "bottle opener",
            "measuring spoon", "peeler", "whisk", "tongs", "straw", "tumbler",
            "mug", "egg timer", "jar opener", "chip clip"]},
        {"zh": "小型家居新奇用品", "keywords": [
            "led strip", "galaxy projector", "projector light", "mini lamp",
            "humidifier", "diffuser", "coaster", "candle", "mini fridge",
            "sunset lamp", "lava lamp", "photo clip"]},
        {"zh": "小型运动户外用品", "keywords": [
            "resistance band", "jump rope", "pickleball", "tennis ball",
            "yoga strap", "water bottle", "grip strengthener", "massage ball"]},
    ],
    "low": [
        {"zh": "搬家/普通收纳", "keywords": [
            "moving bags", "moving boxes", "storage bags", "storage bins",
            "storage containers", "vacuum storage", "closet organizer",
            "shelf liner", "underbed storage", "garment rack"]},
        {"zh": "清洁/纯家务用品", "keywords": [
            "cleaner", "detergent", "cleaning", "descaler", "stain remover",
            "drain ", "toilet ", "mop", "scrub", "disinfect", "degreaser",
            "lint roller", "trash bag", "sponge holder"]},
        {"zh": "大件家居/大家电", "keywords": [
            "furniture", "cabinet", "recliner", "sectional", "air fryer",
            "vacuum cleaner", "robot vacuum", "space heater", "dehumidifier",
            "tower fan", "box spring", "headboard", "sheet set", "comforter",
            "pillow set", "curtains"]},
        {"zh": "专业工具", "keywords": [
            "drill", "socket set", "wrench", "multimeter", "soldering",
            "chainsaw", "pressure washer", "impact driver", "tool box"]},
        {"zh": "低趣味刚需品", "keywords": [
            "paper towels", "batteries", "light bulbs", "extension cord",
            "surge protector", "toilet paper", "laundry", "insect", "pest ",
            "mouse trap", "fly trap", "roach", "dryer sheets", "air filter",
            "furnace filter", "water filter replacement"]},
    ],
}
STORE_FIT_POINTS = {"high": 10.0, "mid": 6.0, "low": 0.0}  # neutral = category prior × 4
PENALTY_LOW_STORE_FIT = -6

CATEGORY_ZH = {
    "electronics": "电子", "beauty": "美妆", "toys": "玩具",
    "kitchen": "厨房", "home": "家居", "sports": "运动",
}

STORE_FIT_REASON_ZH = {
    "high": "「{group}」是Goodies核心品类，游客顺手就买",
    "mid": "「{group}」可小量试售，非核心但有机会",
    "low": "「{group}」与Goodies游客门店不匹配",
    "neutral": "非典型Goodies品类，按{cat}大类中性判断",
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
    "BULKY_ITEM": "体积和海运成本待确认，大件不适合Aruba补货",
    "LOW_REVIEWS": "评论样本不足，需求规模未验证",
    "NO_PRICE": "价格缺失，毛利空间待采购价确认",
    "NO_RATING": "暂无评分，质量数据缺失",
    "LOW_STORE_FIT": "非Goodies门店品类，游客场景难出手",
    "DUPLICATE_KIND": "与更高分同类商品重复",
}
# When platform data shows no hard flaw, the risk line still must be SPECIFIC —
# picked deterministically by the priority chain in scoring.primary_risk_zh_for.
NO_RISK_PREFIX = "平台数据暂未发现明显风险"
SEASONAL_KEYWORDS = [
    "beach", "summer", "pool", "swim", "christmas", "halloween", "valentine",
    "easter", "back to school", "thanksgiving", "new year", "spring break",
]
RISK_SEASONAL_ZH = "季节窗口可能较短，注意物流周期"
RISK_MARGIN_ZH = "零售价偏高，毛利空间待采购价确认"
RISK_SAMPLE_ZH = "评论样本还不大，需求规模待观察"
RISK_SHIPPING_ZH = "体积和海运成本待确认"
RISK_LOCAL_ZH = "阿鲁巴本地需求未知，建议先小量试售"

# ---- procurement keyword (for 1688 sourcing) ----
# ASCII tokens are stripped from the zh keyword unless whitelisted as a spec term.
PROCUREMENT_ASCII_KEEP = {"LED", "USB", "DIY", "3D", "RGB", "PVC", "EVA", "TPU", "K9"}
# transliterated brand names that survive translation
BRAND_ZH = [
    "绘儿乐", "乐高", "迪士尼", "漫威", "宝可梦", "神奇宝贝", "任天堂",
    "三丽鸥", "凯蒂猫", "芭比", "星球大战", "哈利波特", "旁氏", "玉兰油",
    "妮维雅", "欧莱雅", "美宝莲", "高露洁", "吉列", "飞利浦",
]
# marketing / filler words with zero procurement value
PROCUREMENT_STRIP_ZH = [
    "正品", "官方", "新款", "升级版", "升级", "豪华", "高级", "热销", "爆款",
    "促销", "限量", "高品质", "优质", "最新", "全新", "适用于", "适合",
    "支持", "重型", "专业级", "礼物", "礼品装", "母亲节", "圣诞", "生日礼物",
    "2025", "2026", "年新", "男女通用", "男士女士", "成人儿童",
]
PROCUREMENT_MIN_LEN = 8
PROCUREMENT_MAX_LEN = 24
