# Fix Rpc Sensitive Contract Tightening

Status: done

## Migration Context

- Legacy source: `openspec/changes/fix-rpc-sensitive-contract-tightening/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

The queue-side credential leak in `ansible-executor` has been fixed, but the upstream RPC and callback surfaces can still expose sensitive materials through error messages, callback logs, and persisted callback results. This change closes the remaining observability leak so SSH/WinRM credentials and inline inventory secrets do not reappear in server-side logs, exceptions, or callback persistence.

## What Changes

- Add a shared RPC-sensitive masking helper for structured payloads and stringified error/output content.
- Sanitize NATS/RPC error handling so raised exceptions and fallback logs never include plaintext credential fields.
- Tighten Ansible callback handling in `job_mgmt` so callback logs use summaries and persisted callback stdout/stderr/error text masks sensitive assignments.
- Reduce upstream logging detail where Playbook submission currently logs raw `extra_vars`.

## Capabilities

### New Capabilities
- `rpc-sensitive-contract-tightening`: Prevent sensitive RPC request, callback, and error content from leaking into observable server-side surfaces.

### Modified Capabilities
- `ansible-executor-payload-sanitization`: Extend the sanitization boundary to upstream RPC error/logging paths and callback persistence surfaces.

## Impact

- Affected code: `server/apps/rpc`, `server/nats_client`, `server/apps/job_mgmt`
- Affected behavior: RPC error text, callback logging, callback result persistence, Ansible submission logs
- No external API contract changes; masking applies only to observability/error surfaces

## Implementation Decisions

## Context

The existing fix set already removes plaintext credentials from executor queue and DLQ persistence, but server-side callers still process raw Ansible RPC payloads and callback results. Two leak paths remain important: `nats_client` builds exception messages and fallback logs from raw RPC error payloads, and `job_mgmt.nats_api.ansible_task_callback()` logs full callback bodies and persists callback output text as-is. These paths are cross-cutting because they sit between `apps/rpc`, `nats_client`, and `job_mgmt`, and they can reintroduce secret material even when queue storage is clean.

## Goals / Non-Goals

**Goals:**
- Provide one reusable masking helper for RPC-observable surfaces.
- Ensure NATS/RPC exception messages and fallback logs are sanitized before they are emitted.
- Ensure Ansible callback logs and stored callback output mask known credential patterns.
- Remove raw `extra_vars` logging from Playbook submission.

**Non-Goals:**
- Changing the execution contract sent to `ansible-executor`
- Encrypting RPC payloads in transit
- Removing all job stdout/stderr persistence; only known sensitive assignments are masked

## Decisions

1. **Use a shared recursive sanitizer plus string-pattern masking.**
   Structured payloads are sanitized recursively by sensitive key name, while string outputs are scrubbed with assignment-style and PEM-key regexes. This keeps caller behavior stable while covering both JSON payloads and free-form callback/error text.

2. **Sanitize at observability boundaries rather than mutating execution payloads.**
   RPC request bodies still need raw credentials to execute successfully. The fix therefore targets logs, exception text, callback summaries, and persisted callback outputs instead of changing the live request contract.

3. **Log callback summaries, not full callback bodies.**
   Callback observability keeps task/result counts and per-host status/exit code, but omits raw stdout/stderr/error bodies from logs. This preserves operational usefulness without retaining secrets.

## Risks / Trade-offs

- **[Risk]** Regex-based masking may not catch every arbitrary secret format. → **Mitigation:** cover known credential fields and PEM blocks, and keep structured-key masking as the primary path.
- **[Risk]** Masking callback stdout/stderr may hide some debugging detail. → **Mitigation:** mask only known secret assignments and preserve the rest of the text.
- **[Risk]** Shared masking logic could drift from executor-side rules. → **Mitigation:** align field names with the executor sanitization set and verify with focused regression tests.

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-03
```

## Capability Deltas

### ansible-executor-payload-sanitization

## MODIFIED Requirements

### Requirement: Sensitive-field policy must be applied consistently across queue persistence boundaries
The system SHALL use a single sensitive-field policy for queue publication, callback retry publication, DLQ summary generation, upstream RPC error handling, and server-side callback observability so the same credential classes are never persisted or logged in plaintext through one path but masked through another.

#### Scenario: Sensitive field appears in multiple queue flows
- **WHEN** the same sensitive field is present in an execution request and later in callback retry or DLQ handling
- **THEN** every queue persistence path SHALL apply the same masking or omission behavior

#### Scenario: Sensitive field reaches upstream RPC diagnostics
- **WHEN** server-side RPC error handling or callback logging observes a payload that contains sensitive credential fields
- **THEN** those diagnostics SHALL mask the sensitive values before raising, logging, or persisting the content

### rpc-sensitive-contract-tightening

## ADDED Requirements

### Requirement: RPC-observable error surfaces must exclude plaintext credential material
The system SHALL sanitize sensitive credential fields before including RPC error details in server-side exception messages or fallback error logs. Sensitive fields MUST include password, private key content, private key passphrases, inline inventory content, and equivalent host credential fields.

#### Scenario: Structured RPC error payload contains sensitive fields
- **WHEN** a NATS RPC response returns an error payload with structured sensitive fields
- **THEN** the raised server-side exception text SHALL mask those fields before returning or logging them

#### Scenario: Fallback error logging has only a raw response object
- **WHEN** RPC error handling falls back to logging the full parsed response for diagnostics
- **THEN** the logged response SHALL mask sensitive credential fields before emission

### Requirement: Ansible callback observability must use sanitized summaries
The system SHALL avoid logging raw Ansible callback payloads and MUST emit only sanitized callback summaries on the server side.

#### Scenario: Callback contains stdout, stderr, or inline inventory secrets
- **WHEN** `ansible_task_callback` receives callback data that includes host output or error text with sensitive assignments
- **THEN** the callback log entry SHALL exclude the raw bodies and SHALL not contain plaintext credential values

### Requirement: Persisted callback output must mask sensitive assignments
The system SHALL sanitize sensitive credential assignments in callback stdout, stderr, and error-message fields before persisting them to job execution records.

#### Scenario: Callback host result includes password-like output
- **WHEN** a callback host result includes password, passphrase, private key, or inventory credential text in stdout/stderr/error_message
- **THEN** the persisted execution result SHALL mask those sensitive values while preserving the surrounding output structure

## Work Checklist

## 1. Shared sanitization policy

- [x] 1.1 Add a shared RPC-sensitive masking helper for structured payloads, assignment-style strings, and PEM key blocks
- [x] 1.2 Reuse the helper from NATS/RPC error handling and job_mgmt callback processing

## 2. RPC and callback hardening

- [x] 2.1 Sanitize `nats_client` exception construction and fallback logging so plaintext credential values do not leak
- [x] 2.2 Replace raw Ansible callback logging with sanitized callback summaries
- [x] 2.3 Sanitize persisted callback stdout/stderr/error_message fields and remove raw Playbook `extra_vars` logging

## 3. Regression coverage

- [x] 3.1 Add focused server tests for RPC error masking and callback masking behavior
- [x] 3.2 Run the targeted server-side regression suite for the new masking behavior
