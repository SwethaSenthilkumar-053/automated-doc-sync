# Automated Documentation Sync — Implementation Plan

## Scope and stack

Implement the architecture using **Python 3 with pytest** and GitHub Actions. Run configured generators locally, preserve Markdown outside generated markers, validate changes before committing, and keep write credentials out of generator execution.

The repository currently has no implementation, mapping, generator definitions, CI workflows, notification route, or recorded automation identity. This plan separates work that can proceed from tasks blocked on those repository-specific facts. Do not fabricate a working `docs-sync.json` or grant write access until the blocked decisions are resolved.

### Effort guide

- **Small:** a focused configuration, module, or workflow change.
- **Medium:** several related components or a bounded integration with tests.
- **Large:** end-to-end workflow, security boundary, or operational-state design.

## Ordered tasks

Tasks are listed in dependency order. `Depends on` identifies prerequisite task IDs. Tasks marked **BLOCKED** require the stated decision or repository information before implementation can be completed.

| ID | Task | Effort | Depends on | Status |
|---|---|---:|---|---|
| T01 | Confirm repository integration contracts | Medium | — | **BLOCKED** |
| T02 | Define mapping schema and generator registry | Medium | T01 | **BLOCKED** |
| T03 | Bootstrap Python package and pytest | Small | — | Ready |
| T04 | Implement safe mapping configuration validation | Medium | T02, T03 | Blocked by T02 |
| T05 | Implement path matching and output containment | Medium | T02, T03 | Blocked by T02 |
| T06 | Implement marked Markdown section updates | Medium | T02, T03 | Blocked by T02 |
| T07 | Implement local generator execution and output validation | Large | T01, T02, T03, T05 | **BLOCKED** |
| T08 | Define and implement sync state, coalescing, and recovery | Large | T01, T03, T05 | **BLOCKED** |
| T09 | Implement retries, audit records, and notification adapter | Medium | T01, T03, T08 | **BLOCKED** |
| T10 | Implement orchestration CLI and end-to-end behavior | Large | T04–T09 | **BLOCKED** |
| T11 | Add unit and integration test coverage | Large | T04–T10 | Partially blocked |
| T12 | Add pull-request configuration validation workflow | Small | T04, T10 | Blocked by T10 |
| T13 | Add secure merge-sync and manual-rerun workflows | Large | T01, T07–T10, T12 | **BLOCKED** |
| T14 | Configure repository rules, identity, and operational settings | Medium | T01, T13 | **BLOCKED** |
| T15 | Run acceptance checks and production readiness review | Medium | T11–T14 | Blocked by T14 |

### Task details and exact file paths

#### T01 — Confirm repository integration contracts

**Effort:** Medium · **Status:** BLOCKED

Before workflow or integration implementation, inspect and record:

- Existing automation identity, write permissions, branch protection, and commit-signing policy.
- Existing Markdown scripts/templates, API/reference generators, supported runtimes, and output directories.
- Existing documentation checks and tests, runner timeout, notification mechanism, and artifact/log retention.
- How missing-marker mappings are represented as partial work and retried after other targets complete.
- Manual rerun semantics and the durable source of truth for processed and unresolved work.
- How concurrent merges are coalesced without losing work or PR audit references, including GitHub Actions pending-run replacement behavior.

**Exact files to create:** none. Record confirmed settings in the repository's existing operational configuration; do not add guessed values to source.

#### T02 — Define mapping schema and generator registry

**Effort:** Medium · **Status:** BLOCKED by T01

Define the versioned mapping contract before writing a configuration file. It must describe repository-relative source patterns, target paths, fixed generator IDs, constrained arguments/options, Markdown marker pairs, and allowed output paths. Define duplicate/overlap precedence and reject recursive mappings where generated documentation is also a source input. Select a schema-validation method and maintain an allowlist that maps generator IDs to fixed local commands; do not support arbitrary shell commands from configuration.

**Exact file paths to create:**

- `docs-sync.schema.json` — formal mapping configuration schema.
- `docs-sync.json` — actual mappings, only after existing scripts, generators, and output locations are confirmed.

#### T03 — Bootstrap Python package and pytest

**Effort:** Small · **Status:** Ready

Create the Python package layout and test configuration. Pin supported Python versions and development/test dependencies. Keep runtime dependencies minimal; add a schema or GitHub API library only if the decisions in T01/T02 require one.

**Exact file paths to create:**

- `pyproject.toml` — package metadata, supported Python version, pytest configuration, and lint/type-check configuration if adopted.
- `requirements-dev.txt` — pinned pytest and selected development tooling.
- `src/doc_sync/__init__.py`
- `tests/conftest.py`

#### T04 — Implement safe mapping configuration validation

**Effort:** Medium · **Depends on:** T02, T03

Parse and validate configuration with actionable errors. Validate required keys and types, supported generator IDs, normalized repository-relative paths, duplicate targets, source/output recursion, and marker definitions. Resolve targets beneath the checkout and reject traversal and symlink escapes. Configuration errors are terminal, not retried.

**Exact file paths to create:**

- `src/doc_sync/config.py`
- `src/doc_sync/errors.py`
- `tests/test_config.py`

#### T05 — Implement path matching and output containment

**Effort:** Medium · **Depends on:** T02, T03

Match changed paths to configured mappings deterministically, deduplicate targets, and classify no-match as a recorded no-op. Ensure generator inputs and outputs stay within the repository and permitted output roots. Cover deleted/renamed paths and platform-independent path normalization.

**Exact file paths to create:**

- `src/doc_sync/paths.py`
- `src/doc_sync/mapping.py`
- `tests/test_paths.py`
- `tests/test_mapping.py`

#### T06 — Implement marked Markdown section updates

**Effort:** Medium · **Depends on:** T02, T03

Replace only the content between exactly one valid start/end marker pair, preserving all text outside the markers. Missing, duplicated, reversed, or malformed markers produce a per-target skipped result so independent targets can proceed. Define the persisted partial outcome and rerun behavior with T01 before checkpoint advancement.

**Exact file paths to create:**

- `src/doc_sync/markdown.py`
- `tests/test_markdown.py`

#### T07 — Implement local generator execution and output validation

**Effort:** Large · **Status:** BLOCKED by T01/T02

Implement only after the existing generators and their expected outputs are known. Invoke allowlisted commands using argument arrays with shell execution disabled. Apply bounded runtime, capture useful non-sensitive output, classify retryable versus terminal errors, and verify the produced working-tree paths against the configured allowlist. Generator execution must not receive repository write credentials or signing secrets.

**Exact file paths to create:**

- `src/doc_sync/generators.py`
- `src/doc_sync/outputs.py`
- `tests/test_generators.py`
- `tests/test_outputs.py`

#### T08 — Define and implement sync state, coalescing, and recovery

**Effort:** Large · **Status:** BLOCKED by T01

Specify initialization and validation of the last-success checkpoint, processing range, source SHA capture, partial/unresolved mapping persistence, and recovery if a docs push succeeds but state update fails. Handle Actions pending-run replacement without losing changed paths or PR audit references. Before committing, verify the base SHA is still current; if not, re-checkout and regenerate/revalidate rather than pushing stale output. Make replay idempotent. Do not advance state past unresolved work unless the agreed durable recovery mechanism guarantees rerun.

**Exact file paths to create:**

- `src/doc_sync/state.py`
- `src/doc_sync/git.py`
- `tests/test_state.py`
- `tests/test_git.py`

The durable state backend and any associated repository configuration are **BLOCKED** until T01 chooses the mechanism. The architecture's Actions variable proposal must not be implemented as transactional storage without a recovery design.

#### T09 — Implement retries, audit records, and notification adapter

**Effort:** Medium · **Status:** BLOCKED by T01/T08

Represent outcomes explicitly (`success`, `no-op`, `partial`, `failed`). Retry only classified transient errors, with a total backoff budget that fits the 15-minute completion target and the existing workflow timeout. Record the triggering PR(s), changed paths, generated paths, per-target results, attempt/result, and timestamps. Ensure failure summaries are preserved where possible. Route notifications through the confirmed project mechanism; retain a testable adapter boundary.

**Exact file paths to create:**

- `src/doc_sync/retry.py`
- `src/doc_sync/audit.py`
- `src/doc_sync/notify.py`
- `tests/test_retry.py`
- `tests/test_audit.py`
- `tests/test_notify.py`

#### T10 — Implement orchestration CLI and end-to-end behavior

**Effort:** Large · **Depends on:** T04–T09

Create one CLI used by automated and manual runs. It should load the committed config, compute affected paths from durable state to current HEAD, process eligible mappings, continue independent mappings after target-level failures, validate generated changes, and return meaningful exit codes. Define and validate manual inputs; reject unreachable or unsafe SHAs. Preserve no-op and partial outcomes in the audit record.

**Exact file paths to create:**

- `src/doc_sync/cli.py`
- `src/doc_sync/__main__.py`
- `tests/test_cli.py`

#### T11 — Add unit and integration test coverage

**Effort:** Large · **Depends on:** T04–T10; unit tests can proceed alongside implementation

Use pytest with temporary repositories and mocked external boundaries. Cover configuration/path traversal and symlink rejection; marker preservation and malformed markers; generator allowlisting and command invocation; no-op/duplicate commit avoidance; state initialization, replay, unresolved targets, and commit/state crash windows; event coalescing; default-branch races; retry classification; audit output on failures; and manual reruns. Add a fixture repository with representative Markdown markers and a harmless local generator, without copying production source or credentials.

**Exact file paths to create:**

- `tests/test_sync_integration.py`
- `tests/fixtures/docs-sync.json`
- `tests/fixtures/sample.md`
- `tests/fixtures/sample_generator.py`

#### T12 — Add pull-request configuration validation workflow

**Effort:** Small · **Depends on:** T04, T10

Run Python setup, pytest, and mapping validation on pull-request changes. Configure the resulting status check as required in repository settings. Grant read-only permissions. Pin every third-party Action to a full commit SHA and pin the Python/tool versions.

**Exact file path to create:**

- `.github/workflows/docs-sync-config.yml`

#### T13 — Add secure merge-sync and manual-rerun workflows

**Effort:** Large · **Status:** BLOCKED by T01 and T07–T10

Trigger only after merged pull requests to the configured default branch and support `workflow_dispatch`. Serialize safely and coalesce via the agreed state protocol. Separate untrusted checkout/generation/tests from privileged commit and notification actions: the generator job receives no write token or signing credential; a separate minimal-permission job consumes only validated, allowlisted outputs and commits without executing generated files. Verify the base SHA before push. Retain the existing branch protections and signing policy; never force-push or bypass protections. Apply the configured workflow timeout and artifact retention.

**Exact file paths to create:**

- `.github/workflows/docs-sync.yml`
- `.github/workflows/docs-sync-tests.yml` (only if the repository has no suitable existing test workflow)

#### T14 — Configure repository rules, identity, and operational settings

**Effort:** Medium · **Status:** BLOCKED by T01/T13

Configure the existing automation identity or an approved least-privilege GitHub App, with short-lived credentials and minimal job permissions. Confirm that direct documentation commits are accepted by branch protection and satisfy signing requirements. Configure required status checks, repository variables/state if selected, notification destination, and retention. Do not create credentials in source or grant a broad bypass.

**Exact files to create:** none by default. Secret and branch-protection setup belongs in GitHub repository/organization settings. If a non-secret operational configuration file is required by the confirmed project convention, add it only after T01.

#### T15 — Run acceptance checks and production readiness review

**Effort:** Medium · **Depends on:** T11–T14

Run pytest and all existing documentation checks. Validate workflow syntax and permissions, then exercise a test repository or safe dry run for merged-PR trigger filtering, no mapped changes, changed mapped paths, partial marker failure, retry exhaustion, manual rerun, concurrent merges, stale-base recovery, and successful/no-op commits. Verify audit retention, notification delivery, the 15-minute target, and branch-protection/signing behavior before enabling production write access.

**Exact files to create:** none. Fix any implementation/test files identified by acceptance results.

## Proposed new-file inventory

Create these files as their tasks become unblocked:

```text
pyproject.toml
requirements-dev.txt
docs-sync.schema.json
docs-sync.json
src/doc_sync/__init__.py
src/doc_sync/__main__.py
src/doc_sync/audit.py
src/doc_sync/cli.py
src/doc_sync/config.py
src/doc_sync/errors.py
src/doc_sync/generators.py
src/doc_sync/git.py
src/doc_sync/mapping.py
src/doc_sync/markdown.py
src/doc_sync/notify.py
src/doc_sync/outputs.py
src/doc_sync/paths.py
src/doc_sync/retry.py
src/doc_sync/state.py
tests/conftest.py
tests/test_audit.py
tests/test_cli.py
tests/test_config.py
tests/test_generators.py
tests/test_git.py
tests/test_mapping.py
tests/test_markdown.py
tests/test_notify.py
tests/test_outputs.py
tests/test_paths.py
tests/test_retry.py
tests/test_state.py
tests/test_sync_integration.py
tests/fixtures/docs-sync.json
tests/fixtures/sample.md
tests/fixtures/sample_generator.py
.github/workflows/docs-sync-config.yml
.github/workflows/docs-sync.yml
```

`.github/workflows/docs-sync-tests.yml` is conditional: create it only if no existing workflow can run the Python test suite. `docs-sync.json` must contain confirmed repository mappings and must not be populated with placeholder production commands.

## Definition of done

- Mapping validation runs as a required pre-merge check and rejects unsafe or invalid mappings.
- Only configured, repository-local generators run; subprocesses cannot execute arbitrary config-supplied shell commands.
- Generator jobs have no write credentials; the isolated commit step enforces the output allowlist and current-base check.
- Markdown updates preserve all content outside valid generated markers; missing-marker targets are visible and recoverable without losing other work.
- Merges are processed against current default-branch state without losing changes under coalescing, retries, or state-update failures.
- No-op runs create no commit and still produce the required audit record.
- Existing documentation checks pass before commit; transient failures retry within the time budget and terminal failures notify maintainers.
- Manual reruns share the same safety and audit path.
- `pytest` passes, integration/acceptance cases pass, and production identity, branch protection, signing, notification, timeout, and retention settings are confirmed.
