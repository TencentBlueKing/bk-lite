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
