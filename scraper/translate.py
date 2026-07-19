"""EN→ZH translation with repo-committed cache, plus 1688 search-URL builders."""
import time
import urllib.parse

import httpx

from . import config
from .util import log, read_json, write_json

_SEPARATORS = (",", " - ", "(", "|", "–", "【")


def to_short_title(title_en: str) -> str:
    t = title_en
    for sep in _SEPARATORS:
        idx = t.find(sep)
        if idx > 0:
            t = t[:idx]
    return " ".join(t.split()).strip()


def to_keyword_zh(title_zh: str) -> str:
    return title_zh.strip()[:30]


def url_1688(kw_zh: str):
    chars = []
    for ch in kw_zh:
        try:
            ch.encode("gbk")
            chars.append(ch)
        except UnicodeEncodeError:
            continue
    cleaned = "".join(chars).strip()
    if not cleaned:
        return None
    hexs = cleaned.encode("gbk").hex().upper()
    return f"https://m.1688.com/offer_search/-{hexs}.html"


def url_1688_fallback(kw: str) -> str:
    q = urllib.parse.quote(kw.strip())
    return f"https://s.1688.com/selloffer/offer_search.htm?keywords={q}&charset=utf8"


def _google_one(text: str) -> str:
    r = httpx.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text},
        headers={"User-Agent": config.UA},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    out = "".join(seg[0] for seg in data[0] if seg and seg[0])
    if not out:
        raise RuntimeError("empty translation")
    return out


def _mymemory_one(text: str) -> str:
    r = httpx.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text, "langpair": "en|zh-CN", "de": config.MYMEMORY_EMAIL},
        timeout=15,
    )
    r.raise_for_status()
    j = r.json()
    if j.get("responseStatus") != 200:
        raise RuntimeError(f"mymemory status {j.get('responseStatus')}")
    out = (j.get("responseData") or {}).get("translatedText", "").strip()
    if not out:
        raise RuntimeError("mymemory empty translation")
    return out


def translate_many(texts, cache_path=config.TRANS_CACHE) -> dict:
    """Translate texts EN→ZH. Cache hits skip the network entirely."""
    cache = read_json(cache_path, {}) or {}
    result, dirty = {}, False
    for t in texts:
        t = t.strip()
        if not t:
            continue
        if t in cache:
            result[t] = cache[t]
            continue
        zh = None
        for attempt in range(3):
            try:
                zh = _google_one(t)
                break
            except Exception as e:  # noqa: BLE001 - network layer, retry then fall back
                log(f"google translate failed ({e}), attempt {attempt + 1}/3")
                time.sleep(1.5 * (attempt + 1))
        if zh is None:
            try:
                zh = _mymemory_one(t)
            except Exception as e:  # noqa: BLE001
                log(f"mymemory failed ({e}); '{t}' left untranslated")
        if zh:
            cache[t] = zh
            result[t] = zh
            dirty = True
        time.sleep(0.6)
    if dirty:
        write_json(cache_path, cache)
    return result
