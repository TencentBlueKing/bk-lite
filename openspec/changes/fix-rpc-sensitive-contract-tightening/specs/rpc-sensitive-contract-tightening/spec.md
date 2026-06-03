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
