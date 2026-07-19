"""TikTok Creative Center anonymous hashtag trends (US).

The old Top Products board was removed in the mid-2026 TikTok One redesign;
GetHashtagList is the surviving anonymous endpoint. HTTP 200 is NOT success —
the business code must be 0 and items non-empty, else we raise.
"""
import time

import httpx

from . import config
from .util import log

API = "https://ads.tiktok.com/CreativeOne/KnowledgeAPI/GetHashtagList"
CONFIG_API = "https://ads.tiktok.com/cc_portal_api/api/trendsTcc"

# Anonymous responses cap at ~3 hashtags per view, so we aggregate the overall
# view plus every industry view (industryID must be an int — strings are ignored).
FALLBACK_INDUSTRIES = [
    10000000000, 11000000000, 12000000000, 14000000000, 15000000000,
    17000000000, 18000000000, 19000000000, 21000000000, 22000000000,
    23000000000, 25000000000, 27000000000, 28000000000, 29000000000,
]

HEADERS = {
    "User-Agent": config.UA,
    "Content-Type": "application/json",
    "Origin": "https://ads.tiktok.com",
    "Referer": "https://ads.tiktok.com/creative/creativeCenter",
}


class TikTokError(RuntimeError):
    pass


def _validate(payload: dict) -> None:
    code = payload.get("code")
    base = (payload.get("BaseResp") or {}).get("StatusCode")
    if code == 0 or base == 0:
        return
    raise TikTokError(f"business code not ok: code={code} BaseResp.StatusCode={base}")


def _norm_curve(curve) -> list:
    out = []
    for point in curve or []:
        if isinstance(point, dict):
            v = point.get("value", point.get("Value"))
        else:
            v = point
        try:
            out.append(round(float(v), 1))
        except (TypeError, ValueError):
            continue
    return out


def _extract_items(payload: dict) -> list:
    raw = (
        payload.get("items")
        or (payload.get("data") or {}).get("items")
        or (payload.get("data") or {}).get("list")
        or []
    )
    out = []
    for it in raw:
        name = it.get("hashtagName") or it.get("hashtag_name") or ""
        if not name:
            continue
        out.append(
            {
                "name": name,
                "rank": it.get("rankIndex") or it.get("rank") or len(out) + 1,
                "posts": it.get("publishCnt") or it.get("publish_cnt") or 0,
                "curve": _norm_curve(it.get("popularityCurve") or it.get("trend")),
            }
        )
    return out


def _post(client: httpx.Client, body: dict) -> dict:
    r = client.post(API, json=body)
    r.raise_for_status()
    return r.json()


def _industries(client: httpx.Client) -> list:
    try:
        r = client.get(CONFIG_API)
        r.raise_for_status()
        j = r.json()
        if j.get("code") == 0:
            ids = (j.get("data") or {}).get("industry") or []
            if ids:
                return [int(i) for i in ids]
    except Exception as e:  # noqa: BLE001
        log(f"tiktok industry config failed ({e}), using fallback list")
    return FALLBACK_INDUSTRIES


def fetch_hashtags(limit=config.TIKTOK_HASHTAG_LIMIT) -> list:
    seen = {}
    with httpx.Client(headers=HEADERS, timeout=20) as client:
        views = [None] + _industries(client)
        for ind in views:
            body = {"timeRange": 7, "countryCode": "US", "page": 1, "limit": 20}
            if ind is not None:
                body["industryID"] = ind
            try:
                payload = _post(client, body)
                _validate(payload)
                batch = _extract_items(payload)
            except Exception as e:  # noqa: BLE001
                log(f"tiktok view {ind}: {e}")
                continue
            for it in batch:
                seen.setdefault(it["name"], it)
            time.sleep(0.3)
    if not seen:
        raise TikTokError("no hashtags returned")
    items = sorted(seen.values(), key=lambda x: -x["posts"])[:limit]
    for n, it in enumerate(items, 1):
        it["rank"] = n
    return items
