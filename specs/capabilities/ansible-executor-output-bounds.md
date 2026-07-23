# ansible-executor-output-bounds Specification

## Purpose
Define bounded subprocess output handling so ansible-executor task persistence and callback flows remain stable under high-output tasks.

## Requirements
### Requirement: Executor command output must be bounded before persistence
The system SHALL enforce an explicit maximum byte limit on combined stdout/stderr collected from ansible-executor subprocesses before that output is written into task results, task state, or callback payloads.

#### Scenario: Command output remains within limit
- **WHEN** an executor subprocess finishes with combined output below the configured byte limit
- **THEN** the system SHALL persist and callback the full output without truncation

#### Scenario: Command output exceeds limit
- **WHEN** an executor subprocess emits combined output beyond the configured byte limit
- **THEN** the system SHALL truncate retained output to the configured limit before persistence and callback

### Requirement: Truncated executor output must be explicitly identifiable
The system SHALL mark bounded outputs so operators and downstream callers can distinguish complete output from truncated output.

#### Scenario: Truncated output is returned in task result
- **WHEN** an executor subprocess output is truncated due to the configured limit
- **THEN** the task result SHALL include an explicit truncation indicator and enough metadata to show that the output is partial

#### Scenario: Non-truncated output is returned in task result
- **WHEN** an executor subprocess output stays within the configured limit
- **THEN** the task result SHALL NOT falsely indicate truncation

### Requirement: Callback payloads must reuse bounded output
The system SHALL reuse the bounded task result output when assembling callback payloads and MUST NOT rebuild a larger callback payload from raw unbounded process output.

#### Scenario: Callback is sent after oversized output
- **WHEN** a task completes with subprocess output that exceeded the configured byte limit
- **THEN** the callback payload SHALL contain the same truncated output representation stored in task state
