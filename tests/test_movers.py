from datetime import timedelta, timezone, datetime

from scraper import movers


def _item(asin, rank, lst="bestsellers", cat="electronics"):
    return {"asin": asin, "list": lst, "category": cat, "rank": rank}


def test_surge_risers_outrank_new_entries():
    base = {"bestsellers:electronics:A": 50, "bestsellers:electronics:B": 10}
    cur = [_item("A", 5), _item("B", 12), _item("C", 3)]
    out = movers.compute_surge(cur, base)
    a = next(x for x in out if x["asin"] == "A")
    c = next(x for x in out if x["asin"] == "C")
    assert a["rank_prev"] == 50 and a["rank_delta"] == 45 and a["is_new_entry"] is False
    assert round(a["rank_pct"], 1) == 90.0
    assert c["is_new_entry"] is True and c["rank_prev"] is None and c["rank_pct"] is None
    assert a["surge_rank"] == 1 and c["surge_rank"] == 2  # genuine riser beats NEW
    assert all(x["asin"] != "B" for x in out)  # dropped rank never surges


def test_surge_skips_unobserved_pairs():
    # category failed yesterday -> absent from baseline -> must NOT fake NEW
    base = {"bestsellers:electronics:A": 50}
    cur = [_item("X", 5, cat="kitchen")]
    assert movers.compute_surge(cur, base) == []


def test_surge_new_only_from_bestsellers():
    base = {"bestsellers:electronics:A": 50, "new-releases:electronics:B": 9}
    cur = [_item("N", 1, lst="new-releases")]
    assert movers.compute_surge(cur, base) == []  # new-releases churn is not a signal


def test_surge_new_entries_capped():
    base = {"bestsellers:electronics:Z9": 100}
    cur = [_item(f"N{i}", i + 1) for i in range(20)]
    out = movers.compute_surge(cur, base)
    assert len(out) == 10  # SURGE_NEW_MAX
    assert all(x["is_new_entry"] for x in out)


def test_surge_caps_size_with_risers():
    base = {f"bestsellers:electronics:A{i}": i + 41 for i in range(60)}
    cur = [_item(f"A{i}", i + 1) for i in range(60)]
    out = movers.compute_surge(cur, base)
    assert len(out) == 30
    assert all(not x["is_new_entry"] for x in out)


def test_surge_one_slot_per_asin():
    base = {"bestsellers:electronics:A": 50, "bestsellers:kitchen:A": 60}
    cur = [_item("A", 5), _item("A", 6, cat="kitchen")]
    out = movers.compute_surge(cur, base)
    assert len(out) == 1


def test_surge_empty_baseline_returns_empty():
    assert movers.compute_surge([_item("A", 5)], None) == []


def test_snapshot_roundtrip_and_baseline_window(tmp_path):
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_item("A", 7)], now - timedelta(hours=25), snap_dir=tmp_path)
    movers.save_snapshot([_item("A", 3)], now - timedelta(hours=2), snap_dir=tmp_path)
    movers.save_snapshot([_item("A", 9)], now - timedelta(hours=27), snap_dir=tmp_path)
    base = movers.pick_baseline(now, snap_dir=tmp_path)
    assert base == {"bestsellers:electronics:A": 7}  # 25h is closest to the 24h ideal


def test_baseline_falls_back_within_age_bounds(tmp_path):
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_item("A", 4)], now - timedelta(hours=10), snap_dir=tmp_path)
    movers.save_snapshot([_item("A", 8)], now - timedelta(hours=13), snap_dir=tmp_path)
    base = movers.pick_baseline(now, snap_dir=tmp_path)
    assert base == {"bestsellers:electronics:A": 8}  # 13h closer to 24h than 10h


def test_baseline_rejects_too_young_snapshots(tmp_path):
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_item("A", 4)], now - timedelta(minutes=25), snap_dir=tmp_path)
    assert movers.pick_baseline(now, snap_dir=tmp_path) is None


def test_baseline_rejects_too_old_snapshots(tmp_path):
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_item("A", 4)], now - timedelta(days=5), snap_dir=tmp_path)
    assert movers.pick_baseline(now, snap_dir=tmp_path) is None


def test_baseline_none_when_no_snapshots(tmp_path):
    assert movers.pick_baseline(datetime.now(timezone.utc), snap_dir=tmp_path) is None


def _pitem(asin, rank, price, lst="bestsellers", cat="tcg"):
    return {"asin": asin, "list": lst, "category": cat, "rank": rank, "price_val": price}


def test_snapshot_stores_price():
    import json
    from scraper.util import read_json
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
        movers.save_snapshot([_pitem("A", 1, 19.99)], now, snap_dir=Path(d))
        data = read_json(next(Path(d).glob("*.json")))
        assert data["items"][0]["price"] == 19.99


def test_price_report_detects_24h_drop(tmp_path):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_pitem("A", 1, 40.0)], now - timedelta(hours=24), snap_dir=tmp_path)
    out = movers.price_report([_pitem("A", 1, 29.99)], now, snap_dir=tmp_path)
    key = "bestsellers:tcg:A"
    assert out[key]["drop"]["prev_price"] == 40.0
    assert out[key]["drop"]["pct"] == 25.0


def test_price_report_small_drop_ignored(tmp_path):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_pitem("A", 1, 40.0)], now - timedelta(hours=24), snap_dir=tmp_path)
    out = movers.price_report([_pitem("A", 1, 36.0)], now, snap_dir=tmp_path)  # -10%
    assert out == {}


def test_price_report_low_needs_history_depth(tmp_path):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    # only 3 history points → no "period low" even though it's the cheapest yet
    for h in (30, 20, 10):
        movers.save_snapshot([_pitem("A", 1, 40.0)], now - timedelta(hours=h), snap_dir=tmp_path)
    out = movers.price_report([_pitem("A", 1, 39.0)], now, snap_dir=tmp_path)
    assert out == {}
    # 8+ points and strictly below all of them → low_14d
    for h in (72, 66, 60, 54, 48):
        movers.save_snapshot([_pitem("A", 1, 41.0)], now - timedelta(hours=h), snap_dir=tmp_path)
    out2 = movers.price_report([_pitem("A", 1, 39.0)], now, snap_dir=tmp_path)
    assert out2["bestsellers:tcg:A"]["low_14d"] is True


def test_price_report_missing_price_safe(tmp_path):
    now = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_pitem("A", 1, None)], now - timedelta(hours=24), snap_dir=tmp_path)
    out = movers.price_report([_pitem("A", 1, None)], now, snap_dir=tmp_path)
    assert out == {}


def test_prune_keeps_recent(tmp_path):
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_item("A", 1)], now - timedelta(days=20), snap_dir=tmp_path)
    movers.save_snapshot([_item("A", 2)], now - timedelta(days=2), snap_dir=tmp_path)
    movers.prune_snapshots(now, keep_days=14, snap_dir=tmp_path)
    assert len(list(tmp_path.glob("*.json"))) == 1
