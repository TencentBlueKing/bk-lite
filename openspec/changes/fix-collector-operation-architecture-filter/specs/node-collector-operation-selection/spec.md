## ADDED Requirements

### Requirement: Collector operation queries are architecture-scoped
When loading collector options for selected nodes, the system SHALL include the selected nodes' CPU architecture as the structured `cpu_architecture` query parameter.

#### Scenario: Selected ARM64 Linux node opens restart collector modal
- **WHEN** a user selects an ARM64 Linux node and opens a collector operation modal
- **THEN** the collector list request includes `node_operating_system=linux` and `cpu_architecture=arm64`

#### Scenario: Collector category is selected
- **WHEN** a collector application category is selected in the modal
- **THEN** the category MAY be sent as `tags`, but architecture correctness MUST still come from `cpu_architecture`

### Requirement: Unknown node architecture blocks collector operations
The system SHALL NOT open collector operation selection when the selected nodes have no known CPU architecture.

#### Scenario: Selected node has unknown architecture
- **WHEN** a user selects a node whose `cpu_architecture` is empty and chooses a collector operation
- **THEN** the system shows an error and does not request the collector list
