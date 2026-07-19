import json
from pathlib import Path

import pytest

from scraper import amazon

FIXTURE = Path(__file__).parent / "fixtures" / "amazon_zg_sample.html"


def test_parse_empty_grid_returns_empty():
    assert amazon.parse_zg_html('<div data-client-recs-list="[]"></div>') == []


def test_parse_recs_list_primary():
    recs = json.dumps([
        {"id": "B0TEST00A", "metadataMap": {"render.zg.rank": "7"}},
        {"id": "B0TEST00B", "metadataMap": {"render.zg.rank": "8"}},
    ]).replace('"', "&quot;")
    html = f'<div data-client-recs-list="{recs}"></div>'
    items = amazon.parse_zg_html(html)
    assert {(i["asin"], i["rank"]) for i in items} == {("B0TEST00A", 7), ("B0TEST00B", 8)}


@pytest.mark.skipif(not FIXTURE.exists(), reason="live fixture not captured yet")
def test_parse_zg_sample_has_ranked_items():
    items = amazon.parse_zg_html(FIXTURE.read_text(encoding="utf-8"))
    assert len(items) >= 45
    assert all(i["asin"] and i["rank"] > 0 for i in items)
    enriched = [i for i in items if i.get("title") and i.get("image_src")]
    assert len(enriched) >= 25  # ~30 server-rendered items carry title/image
    assert any(i.get("price") for i in enriched)
