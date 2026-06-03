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
