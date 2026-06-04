## Context

Playbook archive handling crosses four code paths today:

1. `server/apps/job_mgmt/serializers/playbook.py` parses upload and upgrade archives and still reads the whole archive into memory.
2. `server/apps/job_mgmt/views/playbook.py` preview flow calls archive extraction helpers that also read the whole archive before validating the requested member.
3. `server/apps/job_mgmt/services/playbook_execution.py` relays Playbook files from MinIO to NATS object storage by fully reading the archive into memory first.
4. `agents/ansible-executor/service/ansible_runner.py` downloads and extracts executor ZIP archives with path safety checks but without archive-size, member-count, or expanded-size bounds.

These gaps mean one oversized or highly expanded archive can stress both the API plane and the executor plane. The fix needs to be cross-cutting so the same archive policy is applied before parsing, previewing, transferring, and extracting.

## Goals / Non-Goals

**Goals:**
- Introduce explicit archive guardrails for upload, upgrade, preview, transfer, and executor extraction.
- Reject unsafe or oversized archives before eager in-memory reads or unchecked extraction.
- Keep user-facing API contracts stable aside from explicit validation failures for guarded cases.
- Reuse one archive-policy model so server and executor do not diverge on what is acceptable.

**Non-Goals:**
- Add support for new archive formats beyond the existing ZIP / tar.gz / tgz set.
- Redesign Playbook storage backends or NATS object store semantics.
- Build a general-purpose streaming archive framework for unrelated modules.
- Change frontend preview UX beyond surfacing existing validation failures.

## Decisions

### Decision 1: Introduce a shared server-side archive policy helper

**Choice:** Add a focused helper in `job_mgmt` for archive metadata inspection and policy enforcement, then call it from upload, upgrade, and preview paths.

**Rationale:** The server currently duplicates archive reads across parse and preview helpers. A shared guardrail layer keeps the limit model consistent and reduces the chance that one path gets fixed while another still reads arbitrary archive sizes.

**Alternative considered:** Inline checks separately into each serializer and preview helper. Rejected because it would duplicate logic and make future limit tuning error-prone.

### Decision 2: Guard before content extraction, not after

**Choice:** Validate archive total size and member metadata before reading file contents or extracting members wherever possible.

**Rationale:** The current problem is order-of-operations: the code loads the archive first and only later enforces per-file preview limits. Guarding earlier is the only way to prevent API memory pressure and executor expansion risk.

### Decision 3: Use bounded streaming for Playbook relay

**Choice:** Replace whole-file relay reads in `playbook_execution.py` with chunked copy semantics and enforce the same archive-size ceiling before transfer.

**Rationale:** Even with safer upload admission, existing stored archives still flow through the relay path. Bounded transfer closes that second amplification point without changing storage interfaces.

### Decision 4: Extend ZIP safety to resource limits in executor

**Choice:** Keep the existing path and symlink safety model in `_safe_extract_zip()` but add member-count, per-member-size, and total-expanded-size checks during extraction.

**Rationale:** Executor extraction is the last line of defense and must remain self-protecting even if a dangerous archive bypasses the server path or arrives from pre-existing stored data.

## Risks / Trade-offs

- **[Risk] Limits that are too small could reject legitimate Playbook bundles** → **Mitigation:** choose conservative defaults and keep server and executor thresholds aligned.
- **[Risk] Archive inspection may still require limited metadata reads for some formats** → **Mitigation:** inspect metadata without loading full member contents and only decode the requested preview member after checks pass.
- **[Risk] Transfer refactor could introduce backend compatibility issues** → **Mitigation:** preserve existing storage interfaces and only change how bytes are read and forwarded.
- **[Risk] Existing large stored archives may start failing on preview or execution** → **Mitigation:** fail fast with explicit validation errors rather than letting workers or executors degrade under load.

## Migration Plan

1. Add server-side archive guard helpers and wire them into upload, upgrade, and preview flows.
2. Refactor Playbook relay to bounded transfer with the same archive limit policy.
3. Add executor ZIP resource guards and tests.
4. Run targeted `job_mgmt` and `ansible-executor` tests covering guarded archives and normal archives.
5. Roll back by reverting the change set if needed; no schema or API version migration is required.

## Open Questions

- Whether archive policy constants should live under `job_mgmt` only or in a more reusable module shared with executor.
- Whether tarball preview should get the same member-count and expanded-size checks immediately or in a follow-up after ZIP parity.
