# Code Review: Documentation Sync

**Scope:** All Python files under `src/`, reviewed against `requirements.md`.  
**Overall:** The code has a clear modular structure and useful unit coverage, but the current CLI does not complete the required automated sync lifecycle. In particular, it neither commits nor pushes generated output, and failed checks can leave generated files in a state that blocks future runs.

## Findings

| # | Severity | Area | Location | Finding |
|---|---|---|---|---|
| 1 | High | Correctness / Functional requirements | `src/doc_sync/cli.py:57-186`; `src/doc_sync/git.py:99-140`; `src/tests/test_cli.py:114-129` | **Generated changes are never committed or pushed by the CLI.** `commit_outputs()` exists but is not called, while `push_current_branch()` always raises. The CLI test explicitly asserts that a successful run does not commit. This leaves the required direct documentation commit unimplemented; automation identity, signing, and branch-protection behavior are also not wired. |
| 2 | High | Error handling / Retryability | `src/doc_sync/cli.py:114-154,184-194` | **A failed check or output validation can permanently block a retry.** Generation writes files before `_run_checks()` and `validate_output_paths()`. If either raises, control jumps to the outer handler before updated hashes are saved or generated files are reverted. On the next run, `ensure_clean_targets()` rejects those dirty targets because their contents do not match the last saved hashes. |
| 3 | Medium | Correctness / Performance | `src/doc_sync/cli.py:52,126-147,223-251`; `src/doc_sync/generators.py:141-181` | **There is no 15-minute end-to-end deadline.** The 900-second timeout applies independently to each check and each isolated generator, and work runs serially. Multiple targets/checks can therefore exceed the required 15 minutes. The repository also contains no workflow configuration to supply or enforce the existing workflow timeout. |
| 4 | Medium | Error handling | `src/doc_sync/retry.py:14-30`; `src/doc_sync/generators.py:83-90`; `src/doc_sync/cli.py:126-134` | **Retries cover only explicitly transient exceptions.** Generator nonzero exits and startup errors become `GeneratorError`, and failed validation commands become `SyncError`; neither is retried. This is narrower than the requirement to retry failures three times with backoff, so transient process or check failures can fail immediately. |
| 5 | Medium | Functional requirements / Notifications | `src/doc_sync/cli.py:66,178-192`; `src/doc_sync/notify.py:17-33` | **Maintainers are not actually notified.** The CLI always constructs `LoggingNotifier`, which only writes a log message. Although `CallbackNotifier` exists, there is no injection/configuration path in the CLI to connect it to the project's maintainer notification mechanism. |
| 6 | Medium | Audit / Retention | `src/doc_sync/audit.py:28-33`; `src/doc_sync/cli.py:46-48,108,184,190` | **Audit history is overwritten.** Each run writes a single JSON record to the configured audit path, whose default is fixed. A later run replaces the earlier PR references, paths, outcome, and timestamps; no append/history or retention-policy integration is present. |
| 7 | Medium | Functional requirements / Integration | Repository integration, outside `src/` | **The merge-triggered production entry point and committed mapping configuration are absent.** No `.github/workflows` directory or root `docs-sync.json` was present in the repository; the mapping JSON is only a test fixture. As a result, no implementation here invokes the CLI after a default-branch merge, validates a committed mapping before merge, or provides the required workflow/command rerun path. |

## Category assessment

- **Correctness:** Mapping selection, generated-section replacement, path checks, state checkpointing, and targeted Git helpers have sensible boundaries. The missing commit integration and dirty-output retry failure are release-blocking gaps against the stated behavior.
- **Security:** Subprocesses use argv with `shell=False`; configured paths are checked for traversal/symlinks; generator subprocesses receive a filtered environment. The isolated generator is still trusted Python code, not an OS sandbox, so it retains access to repository files and network resources. This should not be treated as isolation from malicious generators.
- **Error handling:** Expected failures are generally modeled with domain exceptions and reported in audit/log output. The dirty-output failure path above, limited retry classification, and absence of an end-to-end deadline weaken recovery.
- **Test coverage:** Tests cover core config/path/Markdown/state/retry/Git behavior and exercise successful and partial CLI runs. They do not cover commit/push integration, failed-check recovery, deadline enforcement, durable audit retention, or delivery through the real notification mechanism.
- **Code clarity:** Modules are narrowly scoped and names are generally descriptive. The CLI coordinates many lifecycle responsibilities, but the separation into mapping, generator, state, audit, and Git helpers is a good foundation.
- **DRY:** No major harmful duplication found in the reviewed files. Some subprocess and lifecycle policy is split between the CLI and Git/generator helpers, which makes integration behavior easy to omit, as seen in finding 1.
- **Dependency safety:** Runtime code uses the Python standard library. The only declared development dependency is pinned `pytest==9.1.1` in `src/requirements-dev.txt`; no third-party runtime dependency risk was identified.

## Validation

`py -3 -m pytest src/tests -q` completed with **55 passed, 2 skipped**.
