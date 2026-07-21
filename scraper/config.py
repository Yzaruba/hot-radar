import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SNAP_DIR = DATA_DIR / "snapshots"
TRANS_CACHE = DATA_DIR / "translations.json"
SITE_DIR = ROOT / "site"
SITE_DATA = SITE_DIR / "data"
IMG_DIR = SITE_DATA / "img"
RADAR_JSON = SITE_DATA / "radar.json"
TRENDS_JSON = SITE_DATA / "trends.json"
RUN_META = SITE_DATA / "run_meta.json"

# Amazon zg category slugs (verified against live pages in Task 5)
CATEGORIES = [
    {"id": "electronics", "zh": "电子", "slug": "electronics"},
    {"id": "beauty", "zh": "美妆个护", "slug": "beauty"},
    {"id": "toys", "zh": "玩具", "slug": "toys-and-games"},
    {"id": "kitchen", "zh": "厨房", "slug": "kitchen"},
    {"id": "home", "zh": "家居", "slug": "home-garden"},
    {"id": "sports", "zh": "运动户外", "slug": "sporting-goods"},
]

LISTS = ["bestsellers", "new-releases"]

# IP/collectible verticals (node IDs live-verified 2026-07-21). These feed the
# separate 潮流IP board: branded/IP goods sourced via distributors, NOT 1688 —
# so they never mix into the main Goodies-scored product flow.
IP_CATEGORIES = [
    {"id": "tcg", "zh": "集换卡牌", "slug": "toys-and-games/166242011"},
    {"id": "anime", "zh": "手办/角色", "slug": "toys-and-games/2514571011"},
    {"id": "manga", "zh": "日漫图书", "slug": "books/4367"},
]
IP_LISTS = ["bestsellers"]  # bestsellers only — half the requests, enough signal

TOP_N = 100
SURGE_SIZE = 30
SURGE_NEW_MAX = 10
SNAPSHOT_KEEP_DAYS = 14
MIN_BASELINE_H = 8
MAX_BASELINE_H = 48
PRICE_DROP_PCT = 20        # sudden-drop alert threshold vs ~24h-ago price
PRICE_LOW_MIN_POINTS = 8   # history depth (≈2 days) before a "period low" counts
TIKTOK_HASHTAG_LIMIT = 50
TRANS_CACHE_MAX = 4000
MYMEMORY_EMAIL = os.environ.get("MYMEMORY_EMAIL", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
