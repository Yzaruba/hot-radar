import pytest

from scraper import tiktok


def test_validate_raises_on_bad_business_code():
    with pytest.raises(tiktok.TikTokError):
        tiktok._validate({"code": 40101, "msg": "no permission"})


def test_validate_accepts_code_zero():
    tiktok._validate({"code": 0})
    tiktok._validate({"BaseResp": {"StatusCode": 0}})


def test_extract_items_maps_fields():
    payload = {
        "code": 0,
        "data": {
            "items": [
                {
                    "hashtagName": "minifan",
                    "rankIndex": 2,
                    "publishCnt": 1234,
                    "popularityCurve": [{"value": 10}, {"value": 50}],
                }
            ]
        },
    }
    items = tiktok._extract_items(payload)
    assert items == [{"name": "minifan", "rank": 2, "posts": 1234, "curve": [10.0, 50.0]}]


def test_fetch_hashtags_raises_when_empty(monkeypatch):
    monkeypatch.setattr(tiktok, "_post", lambda client, body: {"code": 0, "data": {"items": []}})
    with pytest.raises(tiktok.TikTokError):
        tiktok.fetch_hashtags(limit=10)


def test_fetch_hashtags_paginates(monkeypatch):
    pages = {
        1: {"code": 0, "data": {"items": [{"hashtagName": f"tag{i}", "rankIndex": i, "publishCnt": 1} for i in range(1, 21)]}},
        2: {"code": 0, "data": {"items": [{"hashtagName": f"tag{i}", "rankIndex": i, "publishCnt": 1} for i in range(21, 41)]}},
    }
    monkeypatch.setattr(tiktok, "_post", lambda client, body: pages.get(body["page"], {"code": 0, "data": {"items": []}}))
    items = tiktok.fetch_hashtags(limit=30)
    assert len(items) == 30 and items[0]["name"] == "tag1"
