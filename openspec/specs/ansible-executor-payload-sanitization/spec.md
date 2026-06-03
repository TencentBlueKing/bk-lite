# ansible-executor-payload-sanitization Specification

## Purpose
Define how ansible-executor prevents plaintext credentials from being persisted through queue, retry, and DLQ storage paths.

## Requirements
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
