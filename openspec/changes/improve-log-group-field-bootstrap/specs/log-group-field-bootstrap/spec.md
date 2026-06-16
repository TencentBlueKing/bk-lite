## ADDED Requirements

### Requirement: Creation-time field discovery uses a wider fallback window
The system SHALL keep the shared default log query window unchanged, but the log group creation experience SHALL retry dynamic field discovery with a wider creation-only time window when the default discovery returns no fields.

#### Scenario: Default discovery returns fields
- **WHEN** a user opens the log group creation form and default field discovery returns one or more fields
- **THEN** the form SHALL display those fields without issuing a wider fallback lookup

#### Scenario: Default discovery returns no fields
- **WHEN** a user opens the log group creation form and default field discovery returns no fields
- **THEN** the form SHALL retry field discovery with an explicit wider time range for the creation form
- **AND** the shared default search window SHALL remain unchanged for normal log search and analytics queries

### Requirement: Creation-time field discovery does not require existing log group instance access
The system SHALL allow the log group creation form to request field suggestions without requiring the user to already have access to an existing log group instance, while still requiring organization-level permission to create or bind log groups.

#### Scenario: User has manageable organization but no accessible log group instance
- **WHEN** a user has organization-level permission to create or bind log groups
- **AND** the user has no existing accessible log group instances
- **THEN** creation-time field discovery SHALL NOT fail because of missing log group instance access

#### Scenario: User lacks organization-level create or bind permission
- **WHEN** a user lacks organization-level permission to create or bind log groups
- **THEN** creation-time field discovery SHALL return a permission error or no dynamic labels
- **AND** the system SHALL NOT expose dynamic log field metadata from unauthorized organizations

#### Scenario: Normal field discovery remains scoped by log group permission
- **WHEN** a user performs normal log field discovery outside the log group creation form
- **THEN** the system SHALL continue to enforce existing log group scope validation

### Requirement: Rule labels support manual field entry
The log group rule label control SHALL allow users to enter custom field names even when dynamic field discovery returns no fields.

#### Scenario: User enters custom field
- **WHEN** dynamic field suggestions are empty and the user types a field name into the rule label control
- **THEN** the form SHALL accept the custom field value as the rule field

#### Scenario: Rule validation checks required parts
- **WHEN** a user submits a log group rule
- **THEN** validation SHALL require each condition to include a non-empty field, operator, and value
- **AND** validation SHALL NOT require the field to be present in dynamic field suggestions

### Requirement: Empty label states are actionable
The log group creation form SHALL distinguish between empty dynamic field results and permission-blocked creation-time field discovery, and SHALL provide actionable guidance instead of only showing a generic no-data state.

#### Scenario: Wider discovery returns no fields
- **WHEN** both the default and wider field discovery calls return no fields
- **THEN** the label control SHALL show fallback common field suggestions
- **AND** the UI SHALL tell the user that no recommended labels were found and that manual field entry is available

#### Scenario: Creation-time field discovery is permission-blocked
- **WHEN** creation-time field discovery fails because the user lacks organization-level log group create or bind permission
- **THEN** the UI SHALL explain that dynamic labels cannot be loaded from authorized log data
- **AND** the user SHALL still be able to manually enter a rule field in the creation form

### Requirement: Common field suggestions are available as fallback
The log group creation form SHALL provide conservative common log field suggestions when dynamic discovery cannot provide labels.

#### Scenario: Fallback suggestions are displayed
- **WHEN** dynamic field discovery returns no usable labels or is unavailable
- **THEN** the label control SHALL include common field suggestions such as `_stream`, `host.name`, `service.name`, `container.name`, `kubernetes.namespace`, and `log.file.path`
