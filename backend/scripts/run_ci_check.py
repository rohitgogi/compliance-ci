"""Entry point used by GitHub Action to call Compliance CI backend."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
import sys
from pathlib import Path

from app.ci import COMMENT_MARKER, map_gate_to_check_conclusion
from app.ci_integration import build_evaluate_payload, submit_evaluation


def log_event(event: str, correlation_id: str, **fields: object) -> None:
    """Emit single-line structured JSON logs for CI diagnostics."""
    payload = {"event": event, "correlation_id": correlation_id, **fields}
    print(json.dumps(payload, sort_keys=True))


def _redact_payload_for_logs(payload: dict) -> dict:
    """Return payload shape safe for logs without leaking spec contents."""
    return {
        "payload_version": payload.get("payload_version"),
        "repo": payload.get("repo"),
        "pr_number": payload.get("pr_number"),
        "commit_sha": payload.get("commit_sha"),
        "spec_paths": [item.get("path") for item in payload.get("specs", [])],
        "spec_count": len(payload.get("specs", [])),
    }


def parse_changed_file_lines(lines: list[str]) -> list[str]:
    """
    Parse `git diff --name-status` output and return relevant non-deleted paths.

    Supported status forms:
    - A/M/T/C/U/X/B <path>
    - R<score> <old_path> <new_path>
    - D <path> (excluded)
    """
    paths: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("D"):
            continue
        if status.startswith("R"):
            if len(parts) >= 3:
                paths.append(parts[2])
            continue
        if len(parts) >= 2:
            paths.append(parts[1])
    return sorted(set(paths))


def git_changed_files(base_ref: str) -> list[str]:
    """Return changed file paths between base branch and HEAD."""
    result = subprocess.run(
        ["git", "diff", "--name-status", f"origin/{base_ref}...HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_changed_file_lines(result.stdout.splitlines())


def main() -> int:
    correlation_id = os.environ.get("COMPLIANCE_CORRELATION_ID", "").strip() or str(uuid.uuid4())
    backend_url = os.environ.get("COMPLIANCE_BACKEND_URL", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    pr_number = int(os.environ.get("PR_NUMBER", "0"))
    commit_sha = os.environ.get("GITHUB_SHA", "").strip()

    if not backend_url:
        raise RuntimeError("COMPLIANCE_BACKEND_URL is required")
    if not repo or not base_ref or pr_number <= 0 or not commit_sha:
        raise RuntimeError("GitHub context variables are missing")

    log_event("ci.start", correlation_id, repo=repo, pr_number=pr_number, base_ref=base_ref)
    changed_paths = git_changed_files(base_ref=base_ref)
    log_event("ci.changed_paths", correlation_id, changed_paths=changed_paths, changed_count=len(changed_paths))
    payload = build_evaluate_payload(
        repo=repo,
        pr_number=pr_number,
        commit_sha=commit_sha,
        base_dir=Path.cwd(),
        changed_paths=changed_paths,
    )
    log_event("ci.payload_built", correlation_id, **_redact_payload_for_logs(payload))

    # No changed spec files: soft pass for this check.
    if not payload["specs"]:
        output = {
            "final_gate": "PASS",
            "check_conclusion": "success",
            "check_summary": "No compliance specs changed.",
            "comment_markdown": f"{COMMENT_MARKER}\nNo compliance specs changed.",
        }
        log_event("ci.complete", correlation_id, final_gate="PASS", check_conclusion="success", spec_count=0)
        print(json.dumps(output))
        return 0

    response = submit_evaluation(backend_url=backend_url, payload=payload, timeout_seconds=10.0, max_retries=2)

    final_gate = response.get("final_gate")
    status = map_gate_to_check_conclusion(final_gate)
    enriched_response = {
        **response,
        "check_conclusion": status["conclusion"],
        "check_summary": status["summary"],
    }
    log_event(
        "ci.complete",
        correlation_id,
        final_gate=final_gate,
        check_conclusion=status["conclusion"],
        selected_spec_files=[item.get("path") for item in response.get("results", [])],
    )
    print(json.dumps(enriched_response))

    if status["conclusion"] == "success":
        return 0
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - CI entrypoint must return non-zero on fatal errors.
        # Keep logs actionable but never include raw payload/spec content.
        print(json.dumps({"error": str(exc), "sanitized": True}))
        raise SystemExit(1)
