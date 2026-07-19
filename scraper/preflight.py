"""Freshness gate: decide whether a run should scrape at all.

Runs in CI before anything is installed (stdlib only). Prints GitHub-output
lines `proceed=true|false` and `reason=...` for the workflow to consume.
"""
import json
import os
import sys
from datetime import datetime, timezone

from . import config

FRESH_THRESHOLD_H = 5


def should_run(generated_at_iso, now, force, threshold_h=FRESH_THRESHOLD_H):
    """Return (proceed, reason). Skip only when data is fresh AND force is off."""
    if force:
        return True, "forced"
    if not generated_at_iso:
        return True, "no existing data"
    try:
        t = datetime.strptime(generated_at_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return True, f"unparseable generated_at: {generated_at_iso!r}"
    age_h = (now - t).total_seconds() / 3600
    if age_h < threshold_h:
        return False, f"data is {age_h:.1f}h old (<{threshold_h}h) and force is off"
    return True, f"data is {age_h:.1f}h old (>={threshold_h}h)"


def main() -> int:
    force = os.environ.get("RADAR_FORCE", "").strip().lower() == "true"
    generated_at = None
    try:
        radar = json.loads(config.RADAR_JSON.read_text(encoding="utf-8"))
        generated_at = radar.get("generated_at")
    except (OSError, ValueError):
        pass
    proceed, reason = should_run(generated_at, datetime.now(timezone.utc), force)
    print(f"proceed={'true' if proceed else 'false'}")
    print(f"reason={reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
