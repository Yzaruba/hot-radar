from pathlib import Path

import yaml

WF_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "radar.yml"
WF = yaml.safe_load(WF_PATH.read_text(encoding="utf-8"))
# YAML 1.1 parses the `on:` key as boolean True
ON = WF.get("on") or WF.get(True)


def _needs(job):
    n = job.get("needs", [])
    return [n] if isinstance(n, str) else list(n)


def test_overlapping_runs_use_one_concurrency_group():
    c = WF["concurrency"]
    assert c["group"] == "radar"
    assert c["cancel-in-progress"] is True
    # both triggers exist and there is no per-job concurrency splitting the group
    assert "schedule" in ON and "workflow_dispatch" in ON
    assert all("concurrency" not in job for job in WF["jobs"].values())


def test_force_input_is_boolean_defaulting_false():
    force = ON["workflow_dispatch"]["inputs"]["force"]
    assert force["type"] == "boolean"
    assert force["default"] is False


def test_skipped_run_does_not_scrape_commit_or_deploy():
    jobs = WF["jobs"]
    gate = "needs.preflight.outputs.proceed == 'true'"
    # commit lives inside the scrape job, so gating scrape gates the commit too
    assert gate in jobs["scrape"]["if"] and "preflight" in _needs(jobs["scrape"])
    assert gate in jobs["deploy"]["if"] and "preflight" in _needs(jobs["deploy"])
    assert gate in jobs["report"]["if"]
    step_names = " ".join(s.get("name", "") for s in jobs["scrape"]["steps"])
    assert "Commit data if changed" in step_names


def test_preflight_receives_force_input():
    steps = WF["jobs"]["preflight"]["steps"]
    gate_step = next(s for s in steps if s.get("id") == "gate")
    assert gate_step["env"]["RADAR_FORCE"] == "${{ inputs.force }}"
