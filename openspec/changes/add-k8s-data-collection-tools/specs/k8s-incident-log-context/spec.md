## ADDED Requirements

### Requirement: Pod incident collection includes current container logs
The system SHALL collect current Pod log context for alert-driven incident workflows when the resolved target is a Pod or when Pod context is part of the selected collection path.

#### Scenario: Collect current logs for single-container Pod
- **WHEN** the resolved target is a single-container Pod
- **THEN** the system collects current log output for that container according to the configured line limit or collection scope

#### Scenario: Record container selection for multi-container Pod
- **WHEN** the resolved target is a multi-container Pod
- **THEN** the system records which container log was collected or records that container selection is required if automatic selection cannot be completed

### Requirement: Pod restart incidents include previous container logs
The system SHALL support previous container log collection for restart-related alert scenarios so that workflows can capture evidence from the prior failed container instance.

#### Scenario: Collect previous logs for restarting Pod
- **WHEN** the target Pod has restarted and previous logs are available
- **THEN** the system collects previous container logs and includes them in the incident evidence package

#### Scenario: Record previous-log unavailability
- **WHEN** the target Pod has restarted but previous logs cannot be retrieved
- **THEN** the system records that previous logs are unavailable and preserves the reason in the collection output

### Requirement: Incident log context includes resource event timelines
The system SHALL collect resource event timeline context for the resolved target resource so that downstream analysis can correlate log evidence with Kubernetes events.

#### Scenario: Include target resource event timeline
- **WHEN** a resolved target resource supports Kubernetes events
- **THEN** the system includes the target resource event timeline for the configured time window in the collection output

### Requirement: Node-level incident context is collectable for workflow handoff
The system SHALL support node-level incident context collection for alert-driven workflows, including node diagnostic context needed to interpret Pod and Node alerts.

#### Scenario: Include node context for Pod alert
- **WHEN** the resolved target is a Pod with an assigned node
- **THEN** the system includes node diagnostic context for the node hosting that Pod in the evidence package

#### Scenario: Include node context for Node alert
- **WHEN** the resolved target is a Node
- **THEN** the system includes node diagnostic context as a first-class evidence block in the collection output

### Requirement: Incident log context preserves collection status and gaps
The system SHALL explicitly represent collection success, partial success, failure, skipped steps, and missing data for logs and node-level context.

#### Scenario: Preserve successful and failed context blocks together
- **WHEN** current logs are collected successfully but previous logs or node context collection fails
- **THEN** the evidence package includes all successful context blocks and records the failed blocks with status and error details without dropping the successful evidence

### Requirement: Incident context blocks use a uniform evidence block structure
The system SHALL wrap collected log, event, node, service, and change context into a uniform evidence block structure so workflow consumers can process collection results consistently.

#### Scenario: Evidence block includes status data and error fields
- **WHEN** a collection step returns log, event, node, service, or change context
- **THEN** the corresponding evidence block includes `status`, `data`, and `error` fields even when the collection result is partial, failed, or skipped
