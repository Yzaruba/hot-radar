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
    monkeypatch.setattr(tiktok, "_industries", lambda client: [111])
    monkeypatch.setattr(tiktok.time, "sleep", lambda s: None)
    with pytest.raises(tiktok.TikTokError):
        tiktok.fetch_hashtags(limit=10)


def test_fetch_hashtags_aggregates_views_dedupes_and_reranks(monkeypatch):
    def fake_post(client, body):
        ind = body.get("industryID")
        if ind is None:
            items = [{"hashtagName": "alpha", "publishCnt": 100},
                     {"hashtagName": "beta", "publishCnt": 50}]
        else:
            items = [{"hashtagName": "beta", "publishCnt": 50},
                     {"hashtagName": "gamma", "publishCnt": 900}]
        return {"code": 0, "data": {"items": items}}

    monkeypatch.setattr(tiktok, "_post", fake_post)
    monkeypatch.setattr(tiktok, "_industries", lambda client: [111])
    monkeypatch.setattr(tiktok.time, "sleep", lambda s: None)
    items = tiktok.fetch_hashtags(limit=10)
    assert [i["name"] for i in items] == ["gamma", "alpha", "beta"]  # posts desc, deduped
    assert [i["rank"] for i in items] == [1, 2, 3]


def test_fetch_hashtags_survives_partial_view_failures(monkeypatch):
    def fake_post(client, body):
        if body.get("industryID") == 111:
            raise RuntimeError("400")
        return {"code": 0, "data": {"items": [{"hashtagName": "alpha", "publishCnt": 1}]}}

    monkeypatch.setattr(tiktok, "_post", fake_post)
    monkeypatch.setattr(tiktok, "_industries", lambda client: [111, 222])
    monkeypatch.setattr(tiktok.time, "sleep", lambda s: None)
    items = tiktok.fetch_hashtags(limit=10)
    assert [i["name"] for i in items] == ["alpha"]
