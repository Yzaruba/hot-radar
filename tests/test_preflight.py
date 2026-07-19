from datetime import datetime, timedelta, timezone

from scraper import preflight

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_fresh_manual_run_is_skipped():
    proceed, reason = preflight.should_run(_iso(NOW - timedelta(hours=3)), NOW, force=False)
    assert proceed is False
    assert "force is off" in reason


def test_force_manual_run_is_not_skipped():
    proceed, reason = preflight.should_run(_iso(NOW - timedelta(hours=3)), NOW, force=True)
    assert proceed is True
    assert reason == "forced"


def test_boundary_exactly_5h_runs():
    proceed, _ = preflight.should_run(_iso(NOW - timedelta(hours=5)), NOW, force=False)
    assert proceed is True


def test_stale_data_runs():
    proceed, _ = preflight.should_run(_iso(NOW - timedelta(hours=6, minutes=30)), NOW, force=False)
    assert proceed is True


def test_missing_or_garbage_timestamp_runs():
    assert preflight.should_run(None, NOW, force=False)[0] is True
    assert preflight.should_run("not-a-date", NOW, force=False)[0] is True
