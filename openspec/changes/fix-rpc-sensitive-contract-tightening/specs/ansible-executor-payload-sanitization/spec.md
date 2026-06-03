## MODIFIED Requirements

### Requirement: Sensitive-field policy must be applied consistently across queue persistence boundaries
The system SHALL use a single sensitive-field policy for queue publication, callback retry publication, DLQ summary generation, upstream RPC error handling, and server-side callback observability so the same credential classes are never persisted or logged in plaintext through one path but masked through another.

#### Scenario: Sensitive field appears in multiple queue flows
- **WHEN** the same sensitive field is present in an execution request and later in callback retry or DLQ handling
- **THEN** every queue persistence path SHALL apply the same masking or omission behavior

#### Scenario: Sensitive field reaches upstream RPC diagnostics
- **WHEN** server-side RPC error handling or callback logging observes a payload that contains sensitive credential fields
- **THEN** those diagnostics SHALL mask the sensitive values before raising, logging, or persisting the content
