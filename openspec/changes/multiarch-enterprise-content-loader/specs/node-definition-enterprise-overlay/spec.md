## ADDED Requirements

### Requirement: node_mgmt builtin definitions MUST support community and optional enterprise overlays

The system SHALL load builtin controller and collector definitions from community content first and SHALL then apply enterprise content when an enterprise definition directory exists.

#### Scenario: enterprise overlay overrides a community definition
- **GIVEN** a community definition file contains a builtin definition with ID `controller_linux`
- **AND** the enterprise definition directory exists and contains a definition with the same ID
- **WHEN** node_mgmt builtin definitions are loaded
- **THEN** the enterprise definition MUST override the community definition for that ID

#### Scenario: enterprise overlay adds new architecture-specific content
- **GIVEN** the community definitions contain only Windows x86_64 and Linux x86_64 controller definitions
- **AND** the enterprise definition directory contains a Linux ARM64 controller definition with a new ID
- **WHEN** node_mgmt builtin definitions are loaded
- **THEN** the Linux ARM64 definition MUST be included in the merged result
- **AND** the community definitions MUST remain available

### Requirement: controller builtin initialization MUST use JSON definitions without reusing definition IDs as model primary keys

The system SHALL initialize builtin `Controller` rows from JSON definitions while keeping Django model primary keys managed by the database.

#### Scenario: initialize controller from JSON definition with string ID
- **GIVEN** a controller JSON definition contains `id: "controller_linux"`
- **WHEN** the builtin controller initialization runs
- **THEN** the system MUST create or update the `Controller` row using `(os, cpu_architecture, name)` matching
- **AND** the JSON definition ID MUST NOT be written to the integer `Controller.id` database primary key
