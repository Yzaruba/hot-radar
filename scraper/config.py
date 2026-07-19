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
TOP_N = 100
SURGE_SIZE = 30
SURGE_NEW_MAX = 10
SNAPSHOT_KEEP_DAYS = 14
MIN_BASELINE_H = 8
MAX_BASELINE_H = 48
TIKTOK_HASHTAG_LIMIT = 50
TRANS_CACHE_MAX = 4000
MYMEMORY_EMAIL = os.environ.get("MYMEMORY_EMAIL", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
