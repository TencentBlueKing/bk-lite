# 2026 06 02 Fix Ansible Executor Security Bounds

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-02-fix-ansible-executor-security-bounds/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

`ansible-executor` currently persists sensitive task payloads into JetStream queue and DLQ paths, and it collects subprocess output without any byte bound before persisting and callbacking results. These behaviors create a high-confidence security and stability risk in the execution plane and should be fixed before further executor expansion.

## What Changes

- Add queue-safe payload handling so `ansible-executor` queue, retry, and DLQ messages do not persist plaintext host credentials, private keys, passphrases, or equivalent sensitive materials.
- Add bounded command output collection so executor tasks truncate oversized stdout/stderr with explicit markers before writing task results or callback payloads.
- Align callback and retry payload generation with the same bounded and sanitized result model used by execution persistence.
- Add regression coverage for sensitive payload sanitization and oversized command output handling.

## Capabilities

### New Capabilities
- `ansible-executor-payload-sanitization`: Ensure executor queueing, retry, and DLQ flows never persist plaintext sensitive task credentials.
- `ansible-executor-output-bounds`: Ensure executor command execution, task result persistence, and callback payloads enforce explicit output size limits.

### Modified Capabilities
- None.

## Impact

- **agents/ansible-executor/service/nats_service.py**: queue publishing, retry publishing, DLQ publishing, and callback payload assembly
- **agents/ansible-executor/service/ansible_runner.py**: bounded subprocess output collection
- **agents/ansible-executor/service/task_store.py**: payload sanitization alignment and shared sensitive-field expectations
- **agents/ansible-executor/tests/**: regression tests for payload sanitization and output truncation
- **Security / Stability**: reduce credential exposure surface and prevent oversized task output from amplifying memory, SQLite, and NATS pressure

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-02
```

## Capability Deltas

### ansible-executor-output-bounds

## ADDED Requirements

### Requirement: Executor command output must be bounded before persistence
The system SHALL enforce an explicit maximum byte limit on combined stdout/stderr collected from ansible-executor subprocesses before that output is written into task results, task state, or callback payloads.

#### Scenario: Command output remains within limit
- **WHEN** an executor subprocess finishes with combined output below the configured byte limit
- **THEN** the system SHALL persist and callback the full output without truncation

#### Scenario: Command output exceeds limit
- **WHEN** an executor subprocess emits combined output beyond the configured byte limit
- **THEN** the system SHALL truncate retained output to the configured limit before persistence and callback

### Requirement: Truncated executor output must be explicitly identifiable
The system SHALL mark bounded outputs so operators and downstream callers can distinguish complete output from truncated output.

#### Scenario: Truncated output is returned in task result
- **WHEN** an executor subprocess output is truncated due to the configured limit
- **THEN** the task result SHALL include an explicit truncation indicator and enough metadata to show that the output is partial

#### Scenario: Non-truncated output is returned in task result
- **WHEN** an executor subprocess output stays within the configured limit
- **THEN** the task result SHALL NOT falsely indicate truncation

### Requirement: Callback payloads must reuse bounded output
The system SHALL reuse the bounded task result output when assembling callback payloads and MUST NOT rebuild a larger callback payload from raw unbounded process output.

#### Scenario: Callback is sent after oversized output
- **WHEN** a task completes with subprocess output that exceeded the configured byte limit
- **THEN** the callback payload SHALL contain the same truncated output representation stored in task state

### ansible-executor-payload-sanitization

## ADDED Requirements

### Requirement: Queue-persisted executor payloads must exclude plaintext sensitive credentials
The system SHALL prevent plaintext task credentials from being persisted into ansible-executor work queue messages, retry queue messages, and other queue-backed task snapshots. Sensitive fields MUST include structured host credentials, private key content, private key passphrases, and equivalent authentication material carried in task payloads.

#### Scenario: Work queue payload is sanitized before publish
- **WHEN** ansible-executor accepts an adhoc or playbook task containing sensitive credential fields
- **THEN** the queue-persisted payload SHALL mask or omit those sensitive fields before publishing to JetStream

#### Scenario: Local task execution still receives required credential material
- **WHEN** ansible-executor begins processing a task that originally included sensitive credential fields
- **THEN** the worker execution path SHALL still receive the credential material required to run the task successfully

### Requirement: DLQ records must not contain raw task payloads
The system SHALL store only sanitized task summaries in DLQ records and MUST NOT persist the raw serialized task message body when a task or callback message exhausts delivery attempts.

#### Scenario: Worker task reaches max delivery
- **WHEN** a queued executor task reaches the configured maximum delivery count
- **THEN** the DLQ record SHALL include task metadata and sanitized task content without the original raw message body

#### Scenario: Callback retry reaches max delivery
- **WHEN** a callback retry message reaches the configured maximum delivery count
- **THEN** the DLQ record SHALL include callback failure metadata and sanitized payload content without the original raw message body

### Requirement: Sensitive-field policy must be applied consistently across queue persistence boundaries
The system SHALL use a single sensitive-field policy for queue publication, callback retry publication, and DLQ summary generation so the same credential classes are never persisted in plaintext through one path but masked through another.

#### Scenario: Sensitive field appears in multiple queue flows
- **WHEN** the same sensitive field is present in an execution request and later in callback retry or DLQ handling
- **THEN** every queue persistence path SHALL apply the same masking or omission behavior

## Work Checklist

## 1. Queue payload sanitization

- [x] 1.1 Extract or define the ansible-executor sensitive-field policy used for queue-facing payload sanitization
- [x] 1.2 Sanitize work queue payloads in `agents/ansible-executor/service/nats_service.py` before publishing `QueuedTask`
- [x] 1.3 Replace raw task bodies in worker-task DLQ records with sanitized task summaries
- [x] 1.4 Apply the same sanitization policy to callback retry queue payloads and callback-retry DLQ records

## 2. Bounded command output

- [x] 2.1 Refactor `agents/ansible-executor/service/ansible_runner.py::run_command` to enforce a maximum retained output size during subprocess execution
- [x] 2.2 Add truncation metadata to bounded command output so downstream callers can detect partial results
- [x] 2.3 Update `agents/ansible-executor/service/nats_service.py` result assembly so persisted task results and callback payloads reuse the bounded output representation

## 3. Regression coverage

- [x] 3.1 Add ansible-executor tests proving queue, retry, and DLQ persistence paths do not retain plaintext sensitive credentials
- [x] 3.2 Add ansible-executor tests proving oversized command output is truncated and marked before persistence and callback
- [x] 3.3 Run the targeted ansible-executor test suite covering the new sanitization and bounded-output behavior
