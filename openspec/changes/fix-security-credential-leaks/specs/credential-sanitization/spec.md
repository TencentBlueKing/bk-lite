## ADDED Requirements

### Requirement: Sensitive credentials MUST be removed from stored task payloads

The ansible-executor SHALL sanitize task payloads before persisting to the task store. Sensitive credential fields including `password`, `private_key_content`, and `private_key_passphrase` MUST be removed from the `host_credentials` array and top-level payload before storage.

#### Scenario: Task with password credentials is stored
- **WHEN** a task is created with `host_credentials` containing `password` fields
- **THEN** the stored `payload_json` SHALL NOT contain any `password` values
- **AND** the stored `host_credentials` entries SHALL contain a `_redacted: true` marker

#### Scenario: Task with SSH key credentials is stored
- **WHEN** a task is created with `host_credentials` containing `private_key_content` or `private_key_passphrase`
- **THEN** the stored `payload_json` SHALL NOT contain any private key content
- **AND** the stored `host_credentials` entries SHALL retain non-sensitive fields (host, port, user, connection)

### Requirement: Task query responses MUST NOT expose credentials

The `task_query` API SHALL return task status and metadata without exposing sensitive credential information. The response payload MUST be derived from the sanitized stored data.

#### Scenario: Query task with redacted credentials
- **WHEN** a client calls `ansible.task.query` for a task that had credentials
- **THEN** the response `payload.host_credentials` SHALL contain only non-sensitive fields
- **AND** each credential entry SHALL have `_redacted: true` indicating sanitization occurred

#### Scenario: Query task preserves execution metadata
- **WHEN** a client calls `task_query` for any task
- **THEN** the response SHALL include `task_id`, `status`, `result`, `execution_status`, `callback_status`
- **AND** the response SHALL include non-sensitive payload fields (module, hosts, timeout, task_id)

### Requirement: Sensitive field list MUST be comprehensive

The sanitization logic SHALL remove all known sensitive credential patterns from Ansible inventory and host credentials.

#### Scenario: All sensitive patterns are sanitized
- **WHEN** a payload contains any of: `password`, `private_key_content`, `private_key_passphrase`, `ansible_password`, `ansible_ssh_passphrase`, `ansible_become_password`
- **THEN** all matching fields SHALL be removed from the stored payload
