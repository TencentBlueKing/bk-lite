## ADDED Requirements

### Requirement: collector definitions MUST support architecture-specific and generic records simultaneously

The system SHALL allow collector definitions to coexist for the same collector name and operating system across multiple CPU architectures.

#### Scenario: import generic and ARM64 collector definitions for the same collector name
- **GIVEN** a generic Linux `Telegraf` collector definition with `cpu_architecture = ""`
- **AND** an ARM64 Linux `Telegraf` collector definition with `cpu_architecture = "arm64"`
- **WHEN** the builtin collector import runs
- **THEN** both collector records MUST be stored successfully
- **AND** the two records MUST remain distinguishable by `(node_operating_system, cpu_architecture, name)`

### Requirement: runtime collector resolution MUST prefer exact architecture matches and fall back to generic definitions

The system SHALL resolve collector definitions by operating system, collector name, and normalized CPU architecture, and SHALL use generic definitions as a fallback when no architecture-specific definition exists.

#### Scenario: install or configure collector for an ARM64 node with a matching ARM64 definition
- **GIVEN** a Linux node reports `cpu_architecture = "arm64"`
- **AND** both generic and ARM64 collector definitions exist for the requested collector name
- **WHEN** the system resolves the collector during package installation or config creation
- **THEN** the ARM64 collector definition MUST be selected

#### Scenario: fall back to generic collector definition when no architecture-specific definition exists
- **GIVEN** a Linux node reports `cpu_architecture = "arm64"`
- **AND** only a generic collector definition exists for the requested collector name
- **WHEN** the system resolves the collector during package installation or config creation
- **THEN** the generic collector definition MUST be selected
- **AND** the operation MUST continue without requiring an ARM64-specific definition
