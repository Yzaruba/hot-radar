import json

from scraper import translate


def test_url_1688_gbk_hex():
    assert translate.url_1688("手机") == "https://m.1688.com/offer_search/-CAD6BBFA.html"


def test_url_1688_strips_non_gbk():
    assert translate.url_1688("手机\U0001F525") == "https://m.1688.com/offer_search/-CAD6BBFA.html"


def test_url_1688_all_non_gbk_returns_none():
    assert translate.url_1688("\U0001F525") is None


def test_url_1688_fallback_utf8():
    assert translate.url_1688_fallback("手机") == (
        "https://s.1688.com/selloffer/offer_search.htm?keywords=%E6%89%8B%E6%9C%BA&charset=utf8"
    )


def test_short_title_truncates_at_separators():
    assert translate.to_short_title("Mini Fan, Portable 3-Speed (Pink)") == "Mini Fan"
    assert translate.to_short_title("LED Strip Lights - 50ft") == "LED Strip Lights"
    assert translate.to_short_title("Plain Title") == "Plain Title"


def test_keyword_zh_truncates_to_30():
    long = "很长的关键词" * 10
    assert translate.to_keyword_zh(long) == long[:30]


def test_translate_many_uses_cache(tmp_path, monkeypatch):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"Mini Fan": "迷你风扇"}, ensure_ascii=False), encoding="utf-8")
    called = []
    monkeypatch.setattr(translate, "_google_one", lambda t: called.append(t) or "X")
    out = translate.translate_many(["Mini Fan"], p)
    assert out == {"Mini Fan": "迷你风扇"}
    assert called == []


def test_translate_many_writes_cache(tmp_path, monkeypatch):
    p = tmp_path / "c.json"
    monkeypatch.setattr(translate, "_google_one", lambda t: "迷你风扇")
    monkeypatch.setattr(translate.time, "sleep", lambda s: None)
    out = translate.translate_many(["Mini Fan"], p)
    assert out["Mini Fan"] == "迷你风扇"
    assert json.loads(p.read_text(encoding="utf-8"))["Mini Fan"] == "迷你风扇"


def test_translate_many_falls_back_to_mymemory(tmp_path, monkeypatch):
    p = tmp_path / "c.json"

    def boom(t):
        raise RuntimeError("gtx down")

    monkeypatch.setattr(translate, "_google_one", boom)
    monkeypatch.setattr(translate, "_mymemory_one", lambda t: "手机套")
    monkeypatch.setattr(translate.time, "sleep", lambda s: None)
    out = translate.translate_many(["Phone Case"], p)
    assert out["Phone Case"] == "手机套"
