"""E2E-style tests for CI runner behavior."""

from __future__ import annotations

import json

import pytest

from scripts import run_ci_check


@pytest.fixture
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPLIANCE_BACKEND_URL", "http://backend")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/compliance-ci")
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    monkeypatch.setenv("PR_NUMBER", "123")
    monkeypatch.setenv("GITHUB_SHA", "abcdef123")
    monkeypatch.setenv("COMPLIANCE_CORRELATION_ID", "corr-1")


def test_parse_changed_file_lines_handles_rename_and_deletes() -> None:
    lines = [
        "A\tbackend/features/payments/a.yaml",
        "M\tbackend/features/payments/b.yaml",
        "R100\tbackend/features/old.yaml\tbackend/features/new.yaml",
        "D\tbackend/features/deleted.yaml",
    ]
    parsed = run_ci_check.parse_changed_file_lines(lines)
    assert parsed == [
        "backend/features/new.yaml",
        "backend/features/payments/a.yaml",
        "backend/features/payments/b.yaml",
    ]


def test_main_noop_when_no_specs_changed(required_env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(run_ci_check, "git_changed_files", lambda base_ref: ["README.md"])
    exit_code = run_ci_check.main()
    output = capsys.readouterr().out.strip().splitlines()[-1]
    body = json.loads(output)
    assert exit_code == 0
    assert body["final_gate"] == "PASS"
    assert body["check_conclusion"] == "success"


@pytest.mark.parametrize(
    ("final_gate", "expected_exit"),
    [("PASS", 0), ("REVIEW_REQUIRED", 1), ("FAIL", 1)],
)
def test_main_gate_outcomes(required_env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, final_gate: str, expected_exit: int) -> None:
    monkeypatch.setattr(
        run_ci_check,
        "git_changed_files",
        lambda base_ref: ["backend/features/payments/card_capture.yaml"],
    )
    monkeypatch.setattr(
        run_ci_check,
        "build_evaluate_payload",
        lambda **kwargs: {
            "payload_version": "v1",
            "repo": kwargs["repo"],
            "pr_number": kwargs["pr_number"],
            "commit_sha": kwargs["commit_sha"],
            "specs": [{"path": "backend/features/payments/card_capture.yaml", "spec_yaml": "feature_id: x"}],
        },
    )
    monkeypatch.setattr(
        run_ci_check,
        "submit_evaluation",
        lambda **kwargs: {
            "repo": "acme/compliance-ci",
            "pr_number": 123,
            "commit_sha": "abcdef123",
            "final_gate": final_gate,
            "comment_markdown": "comment",
            "results": [{"path": "backend/features/payments/card_capture.yaml"}],
        },
    )
    exit_code = run_ci_check.main()
    output = capsys.readouterr().out.strip().splitlines()[-1]
    body = json.loads(output)
    assert exit_code == expected_exit
    assert body["final_gate"] == final_gate
    assert body["check_conclusion"] in {"success", "failure"}


def test_main_logs_are_sanitized(required_env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(
        run_ci_check,
        "git_changed_files",
        lambda base_ref: ["backend/features/payments/card_capture.yaml"],
    )
    monkeypatch.setattr(
        run_ci_check,
        "build_evaluate_payload",
        lambda **kwargs: {
            "payload_version": "v1",
            "repo": kwargs["repo"],
            "pr_number": kwargs["pr_number"],
            "commit_sha": kwargs["commit_sha"],
            "specs": [{"path": "backend/features/payments/card_capture.yaml", "spec_yaml": "super-secret-spec-content"}],
        },
    )
    monkeypatch.setattr(
        run_ci_check,
        "submit_evaluation",
        lambda **kwargs: {
            "repo": "acme/compliance-ci",
            "pr_number": 123,
            "commit_sha": "abcdef123",
            "final_gate": "PASS",
            "comment_markdown": "comment",
            "results": [{"path": "backend/features/payments/card_capture.yaml"}],
        },
    )
    run_ci_check.main()
    all_output = capsys.readouterr().out
    assert "super-secret-spec-content" not in all_output
    assert "correlation_id" in all_output
