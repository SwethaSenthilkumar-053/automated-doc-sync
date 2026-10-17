# Design Review — Automated Documentation Sync

## Overall assessment

The architecture follows the main requirements: it uses a merge-triggered workflow, local generators, mapped paths, marked Markdown regions, validation, conditional commits, retries, and a manual rerun. GitHub Actions is a reasonable fit for the repository described.

The design is not implementation-ready until it closes the privileged-workflow trust boundary, defines durable handling for partial failures, and resolves checkpoint/concurrency behavior. Some choices also need to be reconciled with requirements that say to reuse existing project conventions: the architecture proposes Python, a GitHub App, PR comments, and an Actions variable despite the repository not yet establishing those mechanisms.

## Security risks

| Severity | Risk | Why it matters | Suggested mitigation |
|---|---|---|---|
| 🔴 High | Repository-controlled generator configuration and scripts run in a workflow that also has write access. | A merged change to the mapping or a generator can execute arbitrary code in the sync runner. If the write token or signing key is available to that process, a compromised or malicious change can use it to alter repository content or expose credentials. | Split generation and validation from the privileged commit step. Run generator code without write credentials; pass only validated, constrained output to a separate commit job. Give the commit job a narrowly scoped, short-lived token, and do not expose signing material to generator processes. |
| 🔴 High | Generator identifiers/arguments and repository-local scripts are not constrained precisely enough. | Mapping validation is described, but a config that selects arbitrary executables, arguments, or shell commands can become command injection or arbitrary code execution. Path traversal checks alone do not prevent this. | Use an allowlist of generator IDs mapped to fixed executable/argument templates. Invoke subprocesses with argument arrays and shell execution disabled. Validate arguments and resolve every input/output path under the checkout; reject symlink escapes. |
| 🟡 Medium | Third-party Actions and toolchain supply-chain controls are underspecified. | “Pin action versions” can still mean mutable tags; dependency installation or generator plugins can also execute untrusted code. | Pin Actions to full commit SHAs, use maintained/pinned tool versions and lockfiles where available, and grant only job-specific `permissions`. Avoid installing unpinned dependencies at runtime. |
| 🟡 Medium | Token, signing-key, and PR-comment permissions are described at a high level, not per workflow/job. | Broad workflow-level permissions or persistent credentials increase the impact of a compromised step. | Declare minimal permissions for each job, use a GitHub App installation token with short lifetime and repository scope, avoid checkout credential persistence, and keep required signing credentials isolated to the commit job. |
| 🟢 Low | Audit artifacts and comments may retain more repository metadata than necessary. | PR IDs and changed paths can expose internal project structure to artifact readers; retention is currently unspecified. | Restrict artifact access to repository collaborators, upload only required fields, and apply the repository's retention policy. Do not include source contents, secrets, or full environment dumps in logs. |

## Scalability and reliability gaps

1. **Concurrency does not guarantee a FIFO queue.** GitHub Actions concurrency allows only one running and one pending run per group; a newer pending run can replace an older pending run. The checkpoint/diff approach can cover source changes only if it remains correct across this coalescing and triggering PR metadata is separately recovered. Specify this behavior and test burst merges.
2. **The checkpoint is a single mutable Actions variable without a transactional protocol.** Define initialization, validation of SHA reachability, compare-and-set or serialized updates, and recovery when a push succeeds but the checkpoint update fails. The current ordering can cause reprocessing after a crash, and concurrent external pushes can invalidate the generated commit's base.
3. **The 15-minute target has no capacity budget.** A single serialized job runs all matching generators and all documentation tests. Establish budgets for checkout, generation, validation, retries, and push; identify which generators can safely run in parallel and what to do when the repository exceeds the budget.
4. **GitHub API discovery for coalesced PRs is not defined.** “Resolve associated merged PRs” needs a concrete source, pagination strategy, permissions, and behavior for force-pushes or unavailable metadata. Event payloads alone will not retain all replaced pending events.
5. **Audit artifact availability on failures is unclear.** Ensure the summary is emitted and uploaded even for failed or cancelled attempts, where practical, and distinguish attempt records from successful processing checkpoints.
6. **Retry classification is too broad.** Retrying validation failures or configuration errors wastes the timeout and can obscure deterministic failures. Define retryable versus terminal errors, backoff intervals, and an overall retry budget that fits the 15-minute target.

## Missing components and decisions

- **A durable unresolved-work mechanism.** Missing Markdown markers must be skipped while other targets continue, but the design does not say whether this is a successful, partial, or failed run or how the skipped target is retried after the source checkpoint advances. Track per-mapping pending failures durably, or preserve a retryable range and provide an explicit resolution/reprocessing path.
- **A complete configuration contract.** Define a schema and examples for source patterns, target paths, generator IDs, arguments, marker pairs, allowed output paths, and duplicate/overlap precedence. The standard library parses JSON but does not provide JSON Schema validation; either specify custom validation or choose a schema library.
- **A current-state conflict strategy.** The workflow checks out latest HEAD once, but another default-branch push can occur during generation. Before push, verify the expected base; on mismatch, regenerate/revalidate against the new HEAD rather than blindly retrying the same commit.
- **A non-recursive mapping policy.** Explicitly prohibit or detect mappings where generated docs are also treated as source inputs, to avoid feedback loops and repeated work.
- **A no-mapped-changes audit/checkpoint policy.** The architecture advances the checkpoint for a no-op. Define whether all changes in the SHA range have been evaluated and whether updating the checkpoint can discard unresolved prior mapping failures.
- **Manual rerun semantics.** An optional target SHA is mentioned, but the interaction with the last-success checkpoint is undefined. Specify whether manual runs mean “process checkpoint through target,” “full resync at target,” or “retry unresolved mappings,” and reject unsafe or unreachable SHAs.
- **Branch-protection feasibility.** Direct commits are required, while existing branch protection must remain authoritative. Verify that the existing automation identity is allowed to push the intended documentation changes under current rules; if not, the architecture cannot meet both constraints without an approved protection configuration change.
- **Operational alerting and ownership.** Define who owns failed runs and mapping repair, what the notification contains, and how missing markers are distinguished from exhausted retries. The repository's notification mechanism is not yet known.
- **Baseline test strategy.** Add tests for mapping validation, marker replacement/preservation, path containment, no-op commits, coalesced event ranges, checkpoint recovery, partial failures, and concurrent default-branch updates.

## Anti-patterns or questionable choices

- **Checkpoint and output commit are separate side effects.** Updating the branch and updating an Actions variable cannot be atomic. A failure between them creates replay; a premature checkpoint can lose work. Make replay idempotent, update the checkpoint only after confirmed output handling, and explicitly recover from uncertain outcomes.
- **Treating skipped-marker outcomes like ordinary success is ambiguous.** Continuing other targets is required, but a green run and advanced checkpoint could make the skipped page invisible to future automatic processing. Model partial success separately and retain unresolved work.
- **“Use existing scripts” plus an arbitrary mapping-driven command is an unsafe abstraction.** Reuse existing generators through a fixed registry of supported operations, not a generic shell runner controlled by the mapping.
- **Assuming PR comments are the project notification mechanism.** This is a proposed fallback, not an existing convention. It also requires write permission and a relevant PR for manual runs. Keep notification behind an adapter and confirm the project's approved destination.
- **Selecting a new GitHub App identity before inspecting existing automation identity may create unnecessary infrastructure.** Prefer the established identity if it satisfies least privilege, branch protection, and signing; otherwise document and approve the App setup as a deployment prerequisite.
- **Undifferentiated “three retries” is operationally misleading.** Retry only transient errors; deterministic validation, missing-generator, and marker errors need a clear result and should not burn repeated attempts.

## Recommended improvements, in priority order

1. **Establish a hard privilege boundary:** run checkout-controlled generation and documentation tests without write credentials; validate allowed outputs; commit from a separate minimal-permission job. Do not expose secrets to generators.
2. **Constrain execution:** make mappings declarative, validate a formal schema, dispatch only allowlisted generator IDs, disable shell interpolation, and enforce resolved-path containment including symlinks.
3. **Define processing state:** specify checkpoint initialization and update ordering, idempotent replay after uncertain pushes, pending/partial mapping failures, and recovery after a checkpoint becomes unreachable. Test against GitHub's pending-run replacement semantics.
4. **Make commits race-safe:** record the base SHA, verify it immediately before push, and restart generation and checks against current HEAD if the base moved. Never force-push or bypass branch protections.
5. **Make outcomes observable:** use explicit statuses such as `success`, `no-op`, `partial`, and `failed`; persist per-target results and ensure maintainers can identify and rerun unresolved targets.
6. **Bound execution:** set a retry budget within the 15-minute target, retry only classified transient failures, and measure generator/test durations. Define whether slow generators are split into independent jobs.
7. **Confirm deployment-specific integrations:** inspect the repository's actual automation identity, branch rules, test commands, notification route, and retention policy before choosing a GitHub App, PR comments, Actions variable, and artifact settings.

## Requirement coverage

| Requirement | Review |
|---|---|
| Merge to default branch, mapped changed paths, latest-state/coalesced processing | Addressed conceptually; concurrency replacement and associated-PR recovery need precise handling. |
| Existing Markdown/API generators and output locations | Reuse is stated, but a safe registry and config contract are missing. |
| Preserve hand-written content and skip missing markers while continuing | Addressed functionally; partial-failure persistence and rerun behavior are missing. |
| No mapped paths: record and skip | Addressed, but checkpoint interaction with unresolved work needs definition. |
| Direct commit, existing automation identity, branch protection/signing | Addressed as intent; identity choice is unverified and branch-rule feasibility must be confirmed. |
| Manual rerun and pre-merge mapping validation | Included; rerun target semantics and schema details need definition. |
| 15-minute target, existing timeout, three retries, tests, local-only generation | Included; retry classification, time budget, and validation command/tool details remain open. |
| Audit data and retention | Included conceptually; failure-path artifact guarantees and actual retention setting remain open. |
