"""Mirror product images into site/data/img/ (same-origin → save/share works)."""
import time

import httpx

from . import config
from .util import log


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
            if not src:
                p["image"] = None
                continue
            try:
                r = client.get(src)
                r.raise_for_status()
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
