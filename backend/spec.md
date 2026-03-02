# Compliance CI MVP Spec

## 1. Project Summary
Compliance CI is a backend service that automatically checks fintech feature changes for regulatory compliance during pull requests. Each feature is described in a structured YAML spec, and CI sends changed specs to the backend for evaluation. The backend returns a risk score and a decision (`PASS`, `REVIEW_REQUIRED`, or `FAIL`) that GitHub Actions uses to gate merges.

## 2. Core Features
- Parse and validate structured feature-level YAML compliance specs in PRs.
- Evaluate each changed spec against a curated regulatory corpus using RAG
- Produce a risk score and a deterministic decision (`PASS` / `REVIEW_REQUIRED` / `FAIL`).
- Return structured evidence (rules cited + reasoning summary) for auditability.
- Post a structured PR comment with decision details and blocking status.
- Persist versioned state for specs, evaluations, and corpus versions.
- Re-evaluate existing features when regulatory corpus versions change.

## 3. System Workflow (PR to Merge)
1. A PR adds or updates one or more feature YAML compliance specs.
2. GitHub Action detects changed spec files and sends them to the backend with PR metadata.
3. Backend validates schema and normalizes the feature input.
4. Backend runs RAG-based compliance evaluation against the current corpus version.
5. Backend computes risk score and decision for each changed feature.
6. Backend returns structured results to CI (decision, score, evidence, and message).
7. GitHub Action posts/updates a PR comment with per-feature outcomes.
8. Branch protection uses the CI status: allow merge for `PASS`, require manual compliance review for `REVIEW_REQUIRED`, block merge for `FAIL`.

## 4. Regulatory Corpus + RAG Design
The corpus is a curated, versioned set of regulations and internal compliance interpretations. Documents are chunked and indexed for retrieval. During evaluation, the backend retrieves relevant chunks for the feature context and uses them as grounding context for model reasoning. The decision is based on both retrieved evidence and explicit rule checks, not free-form model output alone.

## 5. Data Storage Needs
Persist the following for consistency and audit history:
- **Feature specs:** feature identifier, YAML content hash, parsed fields, repo/path metadata, and spec version.
- **Evaluations:** timestamp, corpus version, retrieved evidence references, risk score, decision, and explanation payload.
- **Decision history:** prior outcomes per feature to compare drift across PRs.
- **Corpus versions:** corpus metadata (version ID, release date, source set) to trace which rules were used.
- **Re-evaluation jobs:** status and results when corpus updates trigger backfills.

This persistence is required so compliance state survives across PRs, commits, and regulation updates.

## 6. CI Gating Logic
Use a single risk score range (`0-100`) per evaluated feature:
- `PASS`: score `0-30`; no blocking issues found; CI check passes.
- `REVIEW_REQUIRED`: score `31-69`; ambiguous or medium-risk issues; CI check is non-pass and requires manual compliance approval before merge.
- `FAIL`: score `70-100`; high-confidence non-compliance or missing critical controls; CI check fails and blocks merge.

For PRs touching multiple features, the strictest outcome determines final PR gate.

## 7. Regulation Update Trigger Behavior
When corpus version changes (for example `v1` to `v2`):
1. Create a re-evaluation job for all active features (or a scoped subset if configured).
2. Re-run compliance evaluations using the new corpus version.
3. Compare new decisions against previous stored decisions.
4. Flag features that regress (for example `PASS` to `REVIEW_REQUIRED` or `FAIL`).
5. Emit a machine-readable report so teams can open follow-up remediation PRs.

## 8. MVP Milestones (Exactly Three)
1. **Milestone 1: PR Evaluation Path**  
   Build YAML schema validation, backend evaluation endpoint, basic RAG retrieval, risk scoring, and decision response for changed specs.
2. **Milestone 2: CI Integration and Merge Gating**  
   Add GitHub Action integration, PR comment output, and branch-protection-compatible status checks for `PASS`/`REVIEW_REQUIRED`/`FAIL`.
3. **Milestone 3: Persistence and Corpus-Update Re-evaluation**  
   Add storage for spec/evaluation history and implement corpus-version-triggered re-evaluation with regression flagging.
