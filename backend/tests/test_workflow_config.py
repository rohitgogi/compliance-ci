"""Workflow contract tests for TODO-2 execution boundaries."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_workflow_triggers_only_on_pull_request() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "compliance-ci.yml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert set(workflow["on"].keys()) == {"pull_request"}
    assert workflow["on"]["pull_request"]["types"] == ["opened", "synchronize", "reopened"]


def test_workflow_permissions_are_least_privilege_for_ci_commenting() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "compliance-ci.yml"
    )
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    permissions = workflow["permissions"]
    assert permissions["contents"] == "read"
    assert permissions["pull-requests"] == "write"
