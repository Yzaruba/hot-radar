"""TikTok Creative Center anonymous hashtag trends (US).

The old Top Products board was removed in the mid-2026 TikTok One redesign;
GetHashtagList is the surviving anonymous endpoint. HTTP 200 is NOT success —
the business code must be 0 and items non-empty, else we raise.
"""
import httpx

from . import config

API = "https://ads.tiktok.com/CreativeOne/KnowledgeAPI/GetHashtagList"

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


def fetch_hashtags(limit=config.TIKTOK_HASHTAG_LIMIT) -> list:
    items, page = [], 1
    with httpx.Client(headers=HEADERS, timeout=20) as client:
        while len(items) < limit and page <= 10:
            payload = _post(client, {"timeRange": 7, "countryCode": "US", "page": page, "limit": 20})
            _validate(payload)
            batch = _extract_items(payload)
            if not batch:
                break
            items.extend(batch)
            page += 1
    if not items:
        raise TikTokError("no hashtags returned")
    return items[:limit]
