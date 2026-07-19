"""Rank snapshots and self-computed Movers & Shakers (surge) list.

Amazon gutted the real M&S page for datacenter IPs (2026-05), so we snapshot
bestseller/new-release ranks each run and compute the 24h rank delta ourselves.
"""
from datetime import datetime, timedelta, timezone

from . import config
from .util import read_json, write_json

_FMT = "%Y%m%dT%H%M%SZ"


def _key(item) -> str:
    return f"{item['list']}:{item['category']}:{item['asin']}"


def save_snapshot(items, when: datetime, snap_dir=config.SNAP_DIR) -> None:
    slim = [
        {"asin": i["asin"], "list": i["list"], "category": i["category"], "rank": i["rank"]}
        for i in items
    ]
    write_json(snap_dir / f"{when.strftime(_FMT)}.json", {"when": when.strftime(_FMT), "items": slim})


def _snapshot_times(snap_dir):
    out = []
    for f in sorted(snap_dir.glob("*.json")):
        try:
            out.append((datetime.strptime(f.stem, _FMT).replace(tzinfo=timezone.utc), f))
        except ValueError:
            continue
    return out


def pick_baseline(now: datetime, snap_dir=config.SNAP_DIR):
    """Rank map from the snapshot closest to 24h old (20-28h window), else the oldest."""
    if not snap_dir.exists():
        return None
    snaps = _snapshot_times(snap_dir)
    if not snaps:
        return None
    lo, hi = config.BASELINE_WINDOW_H
    in_window = [(t, f) for t, f in snaps if lo <= (now - t).total_seconds() / 3600 <= hi]
    if in_window:
        target = now - timedelta(hours=24)
        chosen = min(in_window, key=lambda tf: abs((tf[0] - target).total_seconds()))[1]
    else:
        chosen = snaps[0][1]  # oldest
    data = read_json(chosen, {})
    return {_key(i): i["rank"] for i in data.get("items", [])}


def compute_surge(current, baseline) -> list:
    """Enrich current items with rank movement vs baseline; top SURGE_SIZE risers."""
    if baseline is None:
        return []
    virtual_prev = config.TOP_N + 1
    risers = []
    for item in current:
        prev = baseline.get(_key(item))
        cur = item["rank"]
        if prev is None:
            eff_prev, is_new = virtual_prev, True
        else:
            eff_prev, is_new = prev, False
        delta = eff_prev - cur
        if delta <= 0:
            continue
        enriched = dict(item)
        enriched.update(
            rank_prev=prev,
            rank_delta=(None if is_new else delta),
            rank_pct=round(delta / eff_prev * 100, 1),
            is_new_entry=is_new,
        )
        risers.append(enriched)
    risers.sort(key=lambda x: (-x["rank_pct"], x["rank"]))
    risers = risers[: config.SURGE_SIZE]
    for n, item in enumerate(risers, 1):
        item["surge_rank"] = n
    return risers


def prune_snapshots(now: datetime, keep_days=config.SNAPSHOT_KEEP_DAYS, snap_dir=config.SNAP_DIR) -> None:
    if not snap_dir.exists():
        return
    cutoff = now - timedelta(days=keep_days)
    for t, f in _snapshot_times(snap_dir):
        if t < cutoff:
            f.unlink()
