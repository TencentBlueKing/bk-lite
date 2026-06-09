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
