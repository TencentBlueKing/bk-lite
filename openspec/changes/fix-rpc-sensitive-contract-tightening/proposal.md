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
