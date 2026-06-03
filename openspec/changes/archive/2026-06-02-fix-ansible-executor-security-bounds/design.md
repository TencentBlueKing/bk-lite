## Context

`agents/ansible-executor` currently treats queue payloads and subprocess output as ordinary task data. This creates two concrete problems on the execution plane:

1. Sensitive fields such as `host_credentials`, `private_key_content`, `private_key_passphrase`, and credential-bearing inventory content can be persisted into JetStream work queue, retry queue, and DLQ payloads even though local task-state storage already recognizes them as sensitive.
2. `run_command()` collects combined stdout/stderr with `communicate()`, so a single noisy task can expand memory usage in the executor, then propagate the same oversized output into SQLite task state and NATS callback payloads.

This change is cross-cutting inside `ansible-executor` because it touches queue publication, retry / DLQ behavior, execution result shaping, and subprocess I/O handling. The goal is to close the immediate persistence and amplification gaps without redesigning the RPC protocol or introducing a new secret transport mechanism.

## Goals / Non-Goals

**Goals:**
- Prevent plaintext sensitive task credentials from being persisted in queue, retry, and DLQ messages.
- Enforce a deterministic maximum size for executor command output before persistence and callback.
- Keep existing task execution behavior and callback schema largely compatible, with only additive truncation metadata when needed.
- Add regression coverage around sanitization and truncation so the protections cannot silently regress.

**Non-Goals:**
- Redesign how upstream services provide execution credentials.
- Introduce a new encrypted secret-envelope or external secret broker.
- Solve playbook archive resource limits or upload streaming in this change.
- Build a full external log storage system for complete command output.

## Decisions

### Decision 1: Sanitize queue-facing payloads at every persistence boundary

**Choice:** Add a dedicated queue-safe sanitization path in `nats_service.py` and reuse the same sensitive-field policy for work queue, callback retry queue, and DLQ payload generation.

**Rationale:** The current local task-state path already proves the system knows these fields are sensitive. The gap is not detection but inconsistent application. Applying the same rule set at every queue persistence boundary gives immediate risk reduction with minimal protocol churn.

**Alternative considered:** Encrypt sensitive fields in queue payloads. Rejected for this change because it would require key management, worker-side decryption flow, and likely broader contract changes across services.

### Decision 2: Replace raw task copies in DLQ with structured, sanitized summaries

**Choice:** DLQ records will carry task identifiers, delivery metadata, error summary, and a sanitized task snapshot instead of the raw serialized `msg.data`.

**Rationale:** DLQ exists for triage and replay analysis, not for long-term storage of full secrets. A structured summary preserves operability while removing the highest-risk leakage path.

**Alternative considered:** Keep raw payload only in memory logs. Rejected because failures often require post-mortem inspection after process lifetime; a sanitized summary is the safer operational compromise.

### Decision 3: Bound subprocess output before task result assembly

**Choice:** Change `run_command()` to read stdout incrementally and stop retaining bytes beyond a configured maximum. Return truncated output plus a truncation signal that downstream result assembly can preserve.

**Rationale:** The current problem starts at process I/O collection. Bounding only callback payloads would still leave the executor vulnerable to memory pressure and oversized SQLite state. The earliest reliable control point is the subprocess reader.

**Alternative considered:** Keep full output in memory and truncate only before callback. Rejected because it does not solve executor memory amplification and still bloats persisted task state.

### Decision 4: Keep result contract stable with additive truncation metadata

**Choice:** Continue returning `result`, `result_summary.stdout_combined`, and error fields in the existing shape, while adding truncation indicators only when output was clipped.

**Rationale:** Existing callers and UI flows likely depend on current result keys. Additive metadata is the lowest-risk way to expose bounded-output behavior.

## Risks / Trade-offs

- **[Risk] Sanitizing too aggressively could remove fields still required by workers** → **Mitigation:** sanitize only queue-persisted copies, not the in-memory request object already being executed by the worker path.
- **[Risk] Bounded output may hide diagnostic tail content operators expect** → **Mitigation:** include explicit truncation markers and byte-count metadata so operators know the result is partial.
- **[Risk] Inventory content may contain credentials in free-form text that are harder to scrub safely** → **Mitigation:** start with deterministic masking of known sensitive credential patterns and avoid storing raw inventory content in DLQ snapshots.
- **[Risk] Queue summary changes could affect debugging workflows** → **Mitigation:** retain task id, task type, timestamps, delivery counts, and sanitized payload structure so correlation still works.

## Migration Plan

1. Land payload sanitization and bounded output changes together so queue persistence and callback results stay coherent.
2. Run targeted ansible-executor tests covering queue publication, DLQ publication, callback retry publication, and command output truncation.
3. Deploy without protocol migration; workers and upstream services continue using the same task submission shape.
4. Roll back by reverting the executor change if any execution compatibility issue appears, since no storage schema or API version change is introduced.

## Open Questions

- Whether `inventory_content` should be fully omitted from queue snapshots or partially masked field-by-field.
- Whether the output limit should be a fixed constant first or immediately configurable through executor settings.
