## ADDED Requirements

### Requirement: Create memory space
The system SHALL allow users to create a memory space with name, description, scope (personal/organization), guidelines, and model configuration.

#### Scenario: Create personal memory space
- **WHEN** user submits create form with scope="personal"
- **THEN** system creates a memory space with created_by set to current user and team set to current team

#### Scenario: Create organization memory space
- **WHEN** user submits create form with scope="organization"
- **THEN** system creates a memory space accessible to all team members

### Requirement: List memory spaces
The system SHALL display all memory spaces accessible to the current user within the current team.

#### Scenario: List memory spaces for team member
- **WHEN** user views memory space list
- **THEN** system displays all memory spaces belonging to the current team

#### Scenario: Filter by scope
- **WHEN** user filters by scope="personal"
- **THEN** system displays only personal memory spaces

### Requirement: View memory space details
The system SHALL allow users to view memory space configuration and its memory entries.

#### Scenario: View configuration
- **WHEN** user opens memory space detail page
- **THEN** system displays name, description, scope, guidelines, and model configuration

#### Scenario: View memory entries for personal scope
- **WHEN** user views memory entries of a personal memory space they created
- **THEN** system displays all memory entries owned by the user

#### Scenario: View memory entries for organization scope
- **WHEN** user views memory entries of an organization memory space
- **THEN** system displays all memory entries (owner is null)

### Requirement: Update memory space
The system SHALL allow users to update memory space configuration.

#### Scenario: Update guidelines
- **WHEN** user modifies guidelines and saves
- **THEN** system updates the guidelines field

#### Scenario: Scope cannot be changed
- **WHEN** user attempts to change scope after creation
- **THEN** system rejects the change (scope is immutable)

### Requirement: Delete memory space
The system SHALL allow users to delete a memory space and all its memory entries.

#### Scenario: Delete with confirmation
- **WHEN** user confirms deletion
- **THEN** system deletes the memory space and all associated memory entries

### Requirement: Edit memory entry
The system SHALL allow users to manually edit memory entry content.

#### Scenario: Edit memory content
- **WHEN** user edits memory content in the detail view
- **THEN** system updates the memory entry content

### Requirement: Delete memory entry
The system SHALL allow users to delete individual memory entries.

#### Scenario: Delete single entry
- **WHEN** user deletes a memory entry
- **THEN** system removes the entry from the memory space
