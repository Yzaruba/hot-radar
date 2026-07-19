"""Mirror product images into site/data/img/ (same-origin → save/share works)."""
import time
from urllib.parse import urlparse

import httpx

from . import config
from .util import log

# Only fetch from Amazon's image CDNs — image_src comes from scraped HTML.
ALLOWED_HOST_SUFFIXES = ("media-amazon.com", "ssl-images-amazon.com")
MIN_BYTES = 1_000
MAX_BYTES = 3_000_000


def _src_ok(src: str) -> bool:
    try:
        u = urlparse(src)
    except ValueError:
        return False
    host = u.hostname or ""
    return u.scheme == "https" and host.endswith(ALLOWED_HOST_SUFFIXES)


def mirror(products) -> None:
    """Download missing images; set p['image'] to the site-relative path or None."""
    config.IMG_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": config.UA}, timeout=30, follow_redirects=True) as client:
        for p in products:
            src = p.pop("image_src", None)
            dest = config.IMG_DIR / f"{p['asin']}.jpg"
            rel = f"data/img/{p['asin']}.jpg"
            if dest.exists():
                p["image"] = rel
                continue
            if not src or not _src_ok(src):
                if src:
                    log(f"image src rejected for {p['asin']}: {src[:80]}")
                p["image"] = None
                continue
            try:
                r = client.get(src)
                r.raise_for_status()
                ctype = r.headers.get("content-type", "")
                if not ctype.startswith("image/"):
                    raise ValueError(f"not an image: {ctype}")
                if not (MIN_BYTES <= len(r.content) <= MAX_BYTES):
                    raise ValueError(f"suspicious size: {len(r.content)} bytes")
                dest.write_bytes(r.content)
                p["image"] = rel
                time.sleep(0.1)
            except Exception as e:  # noqa: BLE001
                log(f"image mirror failed for {p['asin']}: {e}")
                p["image"] = None


def prune(products) -> None:
    """Delete mirrored images no longer referenced by the current product set."""
    if not config.IMG_DIR.exists():
        return
    keep = {p["image"].rsplit("/", 1)[-1] for p in products if p.get("image")}
    for f in config.IMG_DIR.glob("*.jpg"):
        if f.name not in keep:
            f.unlink()
