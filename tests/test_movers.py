from datetime import timedelta, timezone, datetime

from scraper import movers


def _item(asin, rank, lst="bestsellers", cat="electronics"):
    return {"asin": asin, "list": lst, "category": cat, "rank": rank}


def test_surge_ranks_by_pct_and_marks_new():
    base = {"bestsellers:electronics:A": 50, "bestsellers:electronics:B": 10}
    cur = [_item("A", 5), _item("B", 12), _item("C", 3)]
    out = movers.compute_surge(cur, base)
    a = next(x for x in out if x["asin"] == "A")
    c = next(x for x in out if x["asin"] == "C")
    assert a["rank_prev"] == 50 and a["rank_delta"] == 45 and a["is_new_entry"] is False
    assert round(a["rank_pct"], 1) == 90.0
    assert c["is_new_entry"] is True and c["rank_prev"] is None
    assert c["surge_rank"] == 1 and a["surge_rank"] == 2  # NEW@3 outranks 50->5
    assert all(x["asin"] != "B" for x in out)  # dropped rank never surges


def test_surge_key_separates_list_and_category():
    base = {"bestsellers:electronics:A": 50}
    cur = [_item("A", 5, cat="kitchen")]
    out = movers.compute_surge(cur, base)
    assert out[0]["is_new_entry"] is True  # different category = no baseline match


def test_surge_empty_baseline_returns_empty():
    assert movers.compute_surge([_item("A", 5)], None) == []


def test_surge_caps_size():
    base = {}
    cur = [_item(f"A{i}", i + 1) for i in range(60)]
    out = movers.compute_surge(cur, base)
    assert len(out) == 30


def test_snapshot_roundtrip_and_baseline_window(tmp_path):
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_item("A", 7)], now - timedelta(hours=25), snap_dir=tmp_path)
    movers.save_snapshot([_item("A", 3)], now - timedelta(hours=2), snap_dir=tmp_path)
    movers.save_snapshot([_item("A", 9)], now - timedelta(hours=27), snap_dir=tmp_path)
    base = movers.pick_baseline(now, snap_dir=tmp_path)
    assert base == {"bestsellers:electronics:A": 7}  # 25h is closest to the 24h ideal


def test_baseline_falls_back_to_oldest_outside_window(tmp_path):
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_item("A", 4)], now - timedelta(hours=10), snap_dir=tmp_path)
    movers.save_snapshot([_item("A", 8)], now - timedelta(hours=13), snap_dir=tmp_path)
    base = movers.pick_baseline(now, snap_dir=tmp_path)
    assert base == {"bestsellers:electronics:A": 8}


def test_baseline_rejects_too_young_snapshots(tmp_path):
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_item("A", 4)], now - timedelta(minutes=25), snap_dir=tmp_path)
    assert movers.pick_baseline(now, snap_dir=tmp_path) is None


def test_baseline_none_when_no_snapshots(tmp_path):
    assert movers.pick_baseline(datetime.now(timezone.utc), snap_dir=tmp_path) is None


def test_prune_keeps_recent(tmp_path):
    now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    movers.save_snapshot([_item("A", 1)], now - timedelta(days=20), snap_dir=tmp_path)
    movers.save_snapshot([_item("A", 2)], now - timedelta(days=2), snap_dir=tmp_path)
    movers.prune_snapshots(now, keep_days=14, snap_dir=tmp_path)
    assert len(list(tmp_path.glob("*.json"))) == 1
