# Automated Documentation Sync — System Architecture

## Architecture overview

The system is implemented as GitHub Actions workflows backed by a small, repository-local Python sync tool. A merge event starts a serialized sync against the current default-branch state. The tool validates a committed mapping, runs the repository's local Markdown and API-doc generators, validates their output, and commits only when there are changes. A required pull-request check validates mapping changes before merge.

The repository currently contains `requirements.md` and `README.md`, but no workflow, code, mapping, generator configuration, notification integration, or retention convention. The choices below are a concrete starting architecture; where requirements say to reuse existing project conventions, adopt those conventions when they are established.

### ASCII component diagram

```text
 Developer / Maintainer
      |                         GitHub pull request
      |                                  |
      |                    +-------------v--------------+
      +------------------->| GitHub repository          |
                           | source + docs +             |
                           | docs-sync.json              |
                           +------+----------------------+
                                  |
                     PR opened/updated| PR merged to default
                                  |   |
                   +--------------v+  +v---------------------+
                   | Config-check   |  | Documentation-sync  |
                   | workflow       |  | workflow             |
                   | validate map   |  | serialize/coalesce   |
                   +-------+--------+  +----------+-----------+
                           |                      |
                  required status check           | checkout latest state
                           |                      | read last-success SHA
                           |           +----------v-----------+
                           |           | Local Python sync    |
                           |           | - diff/path matching |
                           |           | - Markdown markers  |
                           |           | - invoke generators |
                           |           | - validate outputs  |
                           |           +----+------------+----+
                           |                |            |
                           |        repository-local   GitHub API
                           |        scripts/tools      (PRs, state,
                           |                |           notification)
                           |                v            |
                           |           +----+------------+----+
                           |           | Checks, audit record, |
                           |           | conditional commit    |
                           |           +----------+------------+
                           |                      |
                           |              default branch update
                           |              (automation identity)
                           |                      |
                           +----------------------+-----> Maintainers
                                                       status/comment/
                                                       workflow logs
```

## Components and technology choices

| Component | Choice | Reason |
|---|---|---|
| Event orchestration | GitHub Actions workflow on `pull_request: closed`, guarded by `merged == true` and the default branch; also `workflow_dispatch` for reruns | Native to the repository platform, supports required PR checks and manual reruns, and avoids introducing a hosted service. |
| Sync implementation | Python 3 standard library, as a checked-in command-line tool | Provides portable path, JSON, subprocess, and file handling without sending content to an external service or requiring a new runtime service. The repository has no existing language implementation, so Python is a proposed baseline rather than an observed project convention. |
| Mapping configuration | Version-controlled `docs-sync.json` | JSON is parseable and schema-validated with the standard library; configuration changes are reviewed and versioned with code. Use explicit source globs, target paths, generator identifiers/arguments, and Markdown marker pairs. |
| Markdown updates | Existing repository scripts/templates, invoked locally by the sync tool | Preserves the requirement to reuse existing content-generation logic. If a mapping has no configured existing generator, fail that mapping and report it; do not invent or silently substitute generated content. |
| API/reference generation | Existing language-specific generators and their checked-in configuration, run locally | Reuses the repository's language/toolchain and established output locations; source and documentation content remain within the runner and repository. |
| Serialization and coalescing | GitHub Actions concurrency group scoped to repository and workflow, with cancellation disabled; sync computes changes from a durable last-success checkpoint to current default-branch HEAD | Prevents concurrent commits and lets a later run cover changes from superseded merge events. Diffing from the checkpoint avoids losing paths when events are coalesced. |
| Durable checkpoint | Repository-level Actions variable containing the last successfully processed default-branch SHA | A durable, small state value independent of runner lifetime and artifact expiration. Update only after generation, checks, and commit/no-op handling succeed. |
| Audit records | Structured JSON summary uploaded as a workflow artifact; workflow logs and run summary provide operator visibility | Records triggering PR(s), changed paths, generated paths, outcome, and timestamps. Apply the repository's configured artifact retention; no indefinite log retention is assumed. |
| Notifications | GitHub-native workflow run failure plus a comment on the relevant PR(s), or the project's established notification integration if one is added | Uses the repository platform and gives maintainers an actionable link to run logs. The repository currently has no notification convention; PR comments are the proposed default. |
| Automation identity | Dedicated GitHub App installation token for contents write and required PR/Actions access; commit signing configured if required | Avoids using a personal account and supports explicit, least-privilege repository access. Configure branch protection to permit this identity to make the required direct documentation commit; never bypass protections implicitly. |

### Mapping and update rules

`docs-sync.json` should define mappings from source path patterns to documentation targets and the local generator or update script for each target. Validate the file for valid JSON, required fields, supported generator identifiers, repository-relative paths, path traversal, duplicate/conflicting targets, and usable marker pairs. The config-check workflow runs on pull requests and is a required status check; invalid configuration blocks merge.

Markdown targets must contain exactly one configured start/end marker pair in the correct order. Replace only the content between the markers. A page with missing or malformed markers is skipped while other mappings continue; report it as a mapping-level failure and notify maintainers. A missing configured Markdown generator is an error, not a silent skip. API/reference outputs go to the existing output paths declared by their mappings and generator configuration.

## Step-by-step data flow

1. **Validate configuration before merge.** On pull-request changes, the config-check workflow runs the local validator against `docs-sync.json`. Its status is required for merging. It checks mapping structure and paths without generating or committing documentation.
2. **Accept a qualifying event.** A pull-request-closed event starts sync only when the PR was merged into the configured default branch. Maintainers can also start the same workflow manually.
3. **Serialize and coalesce work.** The workflow uses one concurrency group per repository and does not cancel a running job. The job checks out the latest default-branch HEAD, not a stale event checkout. If events overlap, the current-state diff from the last successful checkpoint ensures all intervening source changes are considered.
4. **Load checkpoint and compute scope.** Read the last-success SHA from the repository variable, then compare that commit with current default-branch HEAD. Resolve affected paths and associated merged PRs, including the event PR, for traceability. If the checkpoint is absent or no longer reachable, perform a safe full mapping scan and record that condition.
5. **Resolve mappings.** Load and validate the committed mapping again at runtime. Match changed source paths to configured mappings and deduplicate targets. If no paths match, record a successful no-op, advance the checkpoint to the processed HEAD, and do not create a commit.
6. **Generate locally.** Run only configured repository-local scripts and API/reference generators in the checked-out repository. Update marked Markdown regions without altering surrounding hand-written text. Continue independent mappings when a target is invalid, while recording each mapping result.
7. **Validate generated changes.** Run the repository's existing documentation checks and tests. Inspect the working tree and allow only documentation outputs and explicitly configured required generated metadata/configuration. A non-allowed change or failed check fails the attempt.
8. **Commit conditionally.** If there are no content changes, do not create an empty commit. Otherwise create a documentation-only commit using the automation identity, with required signing, and push directly to the default branch under its existing protection rules. A rejected push or unmet protection/signing rule is a failure; do not bypass repository rules.
9. **Record completion.** On success—including a no-op—update the last-success checkpoint to the processed HEAD. Publish a structured run record with PR identifier(s), changed paths, generated paths, per-mapping outcomes, result, and timestamps. The workflow artifact follows the configured retention policy.
10. **Retry and notify.** Retry transient generation, validation, or push failures up to three times with backoff, subject to the existing workflow timeout and the 15-minute end-to-end target. After retries are exhausted, preserve failure details, leave the checkpoint unchanged so the next run can cover the same changes, and notify maintainers through the established mechanism (GitHub PR comment/run failure by default).
11. **Manual recovery.** `workflow_dispatch` accepts an optional target SHA or defaults to current default-branch HEAD. It uses the same lock, checkpoint, validation, audit, commit, and notification path as an automatic run.

## External integrations needed

1. **GitHub Actions:** merge and manual workflow triggers, required config-validation status check, concurrency control, run logs/artifacts, workflow timeout, and workflow permissions.
2. **GitHub API / GitHub App:** least-privilege access to read PR and Actions metadata, read/write the checkpoint repository variable, post maintainer notifications, and push generated commits. Configure the App identity under branch protection. If the repository requires signed commits, provision and securely store the approved signing credential in Actions secrets.
3. **Repository-local documentation toolchains:** install or invoke the project's existing Markdown scripts, language runtimes, and API/reference generators in the runner. Pin action versions and generator/tool versions for reproducible results; do not transmit source or documentation content to external generation services.
4. **Notification destination:** use the existing project mechanism if one is established. Since none is present in the inspected repository, the proposal uses a failure workflow run and GitHub PR comments; no external chat or email service is required by this design.

## Operational constraints and open repository-specific values

- Set the concurrency key and default branch from repository context rather than hard-coding `main`.
- Configure the workflow timeout from the repository's existing policy and keep normal completion within 15 minutes.
- Use three retries with backoff for retryable failures. Invalid configuration and missing generators should be reported as actionable errors rather than hidden by retry behavior.
- Configure workflow permissions and the GitHub App narrowly; branch protection and signed-commit requirements remain authoritative.
- Set artifact retention to the repository's existing retention policy. The repository currently does not establish a value or a notification integration, so those deployment settings must be selected when its CI conventions are defined.
