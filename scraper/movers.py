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
    """Rank map from the snapshot closest to 24h old.

    Only snapshots aged MIN_BASELINE_H..MAX_BASELINE_H qualify — a minutes-old
    baseline surfaces meaningless jitter, and after a long outage a days-old
    baseline would mislabel slow drift as a 24h surge. No candidate → None.
    """
    if not snap_dir.exists():
        return None
    snaps = _snapshot_times(snap_dir)
    candidates = [
        (t, f)
        for t, f in snaps
        if config.MIN_BASELINE_H <= (now - t).total_seconds() / 3600 <= config.MAX_BASELINE_H
    ]
    if not candidates:
        return None
    target = now - timedelta(hours=24)
    chosen = min(candidates, key=lambda tf: abs((tf[0] - target).total_seconds()))[1]
    data = read_json(chosen, {})
    return {_key(i): i["rank"] for i in data.get("items", [])}


def compute_surge(current, baseline) -> list:
    """Surge board: genuine rank risers first, NEW top-100 entrants capped after.

    - Items whose (list, category) was not observed in the baseline snapshot are
      skipped entirely (a failed-category snapshot must not fake NEW entries).
    - NEW entrants only count for bestsellers (new-releases churn is trivial),
      never outrank a genuine riser, and take at most SURGE_NEW_MAX slots.
    - One board slot per ASIN.
    """
    if baseline is None:
        return []
    observed = {k.rsplit(":", 1)[0] for k in baseline}
    risers, news = [], []
    for item in current:
        if f"{item['list']}:{item['category']}" not in observed:
            continue
        prev = baseline.get(_key(item))
        cur = item["rank"]
        if prev is None:
            if item["list"] != "bestsellers":
                continue
            entrant = dict(item)
            entrant.update(rank_prev=None, rank_delta=None, rank_pct=None, is_new_entry=True)
            news.append(entrant)
            continue
        delta = prev - cur
        if delta <= 0:
            continue
        riser = dict(item)
        riser.update(
            rank_prev=prev,
            rank_delta=delta,
            rank_pct=round(delta / prev * 100, 1),
            is_new_entry=False,
        )
        risers.append(riser)
    risers.sort(key=lambda x: (-x["rank_pct"], x["rank"]))
    news.sort(key=lambda x: x["rank"])
    board, seen = [], set()
    for item in risers:
        if len(board) >= config.SURGE_SIZE:
            break
        if item["asin"] in seen:
            continue
        seen.add(item["asin"])
        board.append(item)
    news_added = 0
    for item in news:
        if len(board) >= config.SURGE_SIZE or news_added >= config.SURGE_NEW_MAX:
            break
        if item["asin"] in seen:
            continue
        seen.add(item["asin"])
        board.append(item)
        news_added += 1
    for n, item in enumerate(board, 1):
        item["surge_rank"] = n
    return board


def prune_snapshots(now: datetime, keep_days=config.SNAPSHOT_KEEP_DAYS, snap_dir=config.SNAP_DIR) -> None:
    if not snap_dir.exists():
        return
    cutoff = now - timedelta(days=keep_days)
    for t, f in _snapshot_times(snap_dir):
        if t < cutoff:
            f.unlink()
