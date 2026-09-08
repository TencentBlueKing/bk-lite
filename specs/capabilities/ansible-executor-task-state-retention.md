# ansible-executor-task-state-retention Specification

## Purpose
Bound ansible-executor SQLite `task_state` growth after tasks reach a terminal status, without changing the shared callback or `task.query` payload contract used by job, patch, node bootstrap, and stargazer.

## Requirements
### Requirement: Terminal task rows expire after a dedicated retention window
The system SHALL delete persisted `task_state` rows only after they are terminal and older than a configured retention period. Running, queued, and callback-pending rows MUST remain queryable.

#### Scenario: Expired delivered terminal row is removed
- **WHEN** a task is in a terminal status, its callback status is `sent`, `none`, or exhausted `failed`, and `updated_at` is older than `terminal_task_retention_seconds`
- **THEN** the system SHALL delete that row from local task state

#### Scenario: In-flight or recent terminal row is kept
- **WHEN** a task is still running or queued, or its callback is still `pending`, or a terminal row is still inside the retention window
- **THEN** the system SHALL keep the row so `ansible.task.query` and callback retry can still observe it

### Requirement: Callback payload contract stays shared
The system SHALL NOT add executor-private failure fields to callback or `task.query` results. Structured failure details for host monitoring belong in executor logs; downstream modules continue to read the existing `success`, `error`, `result`, and `result_summary` keys.

#### Scenario: Compacted callback does not invent new result_summary keys
- **WHEN** a callback payload is compacted because it exceeds the NATS max payload
- **THEN** `result_summary` SHALL only retain the existing bounded-output keys and MUST NOT add `failure_*` fields
