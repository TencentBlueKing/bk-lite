## ADDED Requirements

### Requirement: Memory read node type
The system SHALL provide a "memory_read" workflow node type that reads memory content from a configured memory space.

#### Scenario: Node available in editor
- **WHEN** user opens workflow editor
- **THEN** "读取记忆" node type is available in the node palette

### Requirement: Memory read node configuration
The system SHALL allow users to configure the memory read node with a memory space selection.

#### Scenario: Configure memory space
- **WHEN** user opens memory read node configuration panel
- **THEN** system displays a dropdown of available memory spaces with scope labels

### Requirement: Memory read node execution
The system SHALL execute memory read node by reading memory content based on scope and user permissions.

#### Scenario: Read personal memory as creator
- **WHEN** memory read node executes with personal scope memory space AND current user is the creator
- **THEN** system outputs `output` (passthrough from input) and `memory` (user's memory content)

#### Scenario: Read personal memory as non-creator
- **WHEN** memory read node executes with personal scope memory space AND current user is NOT the creator
- **THEN** system outputs `output` (passthrough from input) and `memory` (empty string)

#### Scenario: Read organization memory
- **WHEN** memory read node executes with organization scope memory space
- **THEN** system outputs `output` (passthrough from input) and `memory` (organization memory content)

#### Scenario: No memory space configured
- **WHEN** memory read node executes without memory space configured
- **THEN** system outputs `output` (passthrough from input) and `memory` (empty string)

#### Scenario: Memory not found
- **WHEN** memory read node executes AND no memory entry exists
- **THEN** system outputs `output` (passthrough from input) and `memory` (empty string)

### Requirement: Memory write node type
The system SHALL provide a "memory_write" workflow node type that writes content to a configured memory space.

#### Scenario: Node available in editor
- **WHEN** user opens workflow editor
- **THEN** "写入记忆" node type is available in the node palette

### Requirement: Memory write node configuration
The system SHALL allow users to configure the memory write node with a memory space selection.

#### Scenario: Configure memory space
- **WHEN** user opens memory write node configuration panel
- **THEN** system displays a dropdown of available memory spaces with scope labels

### Requirement: Memory write node execution
The system SHALL execute memory write node by triggering async memory write and passing through input.

#### Scenario: Write to personal memory as creator
- **WHEN** memory write node executes with personal scope memory space AND current user is the creator
- **THEN** system triggers async memory write task AND outputs `output` (passthrough from input)

#### Scenario: Write to personal memory as non-creator
- **WHEN** memory write node executes with personal scope memory space AND current user is NOT the creator
- **THEN** system skips memory write AND outputs `output` (passthrough from input)

#### Scenario: Write to organization memory
- **WHEN** memory write node executes with organization scope memory space
- **THEN** system triggers async memory write task AND outputs `output` (passthrough from input)

#### Scenario: No memory space configured
- **WHEN** memory write node executes without memory space configured
- **THEN** system outputs `output` (passthrough from input) without triggering write

#### Scenario: Empty input
- **WHEN** memory write node executes with empty input
- **THEN** system outputs `output` (empty) without triggering write

### Requirement: Memory node variable reference
The system SHALL allow downstream nodes to reference memory read node outputs using template syntax.

#### Scenario: Reference memory content
- **WHEN** downstream node uses `{{memory_read_node_id.memory}}` in configuration
- **THEN** system resolves to the memory content from the memory read node
