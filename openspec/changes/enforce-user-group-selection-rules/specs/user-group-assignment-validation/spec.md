## ADDED Requirements

### Requirement: User create and update require at least one normal group
The system SHALL reject user create and user update requests when the submitted `group_list` is empty or when all selected groups are virtual groups. A valid selection MUST contain at least one existing group with `is_virtual=False`.

#### Scenario: Reject empty group selection on create
- **WHEN** a client submits a user create request with an empty `group_list`
- **THEN** the system returns a validation error indicating that at least one group must be selected

#### Scenario: Reject empty group selection on update
- **WHEN** a client submits a user update request with an empty `group_list`
- **THEN** the system returns a validation error indicating that at least one group must be selected

#### Scenario: Reject virtual-only group selection
- **WHEN** a client submits a user create or update request whose selected groups are all existing groups with `is_virtual=True`
- **THEN** the system returns a validation error indicating that at least one normal group is required

#### Scenario: Accept selection containing a normal group
- **WHEN** a client submits a user create or update request whose selected groups include at least one existing group with `is_virtual=False`
- **THEN** the system accepts the group selection if all other request validation passes

### Requirement: OpsPilotGuest can be selected but does not satisfy the normal-group requirement
The system SHALL allow `OpsPilotGuest` to appear in a user's selected groups, but `OpsPilotGuest` alone or together with other virtual groups MUST NOT satisfy the requirement that the user belong to at least one normal group.

#### Scenario: Reject OpsPilotGuest-only selection
- **WHEN** a client submits a user create or update request whose `group_list` contains only the `OpsPilotGuest` group
- **THEN** the system returns a validation error indicating that at least one normal group is required

#### Scenario: Accept OpsPilotGuest with a normal group
- **WHEN** a client submits a user create or update request whose `group_list` includes `OpsPilotGuest` and at least one existing group with `is_virtual=False`
- **THEN** the system accepts the group selection if all other request validation passes

### Requirement: Backend validation responses are localized
The system SHALL return localized validation messages in Chinese and English for invalid group selections in user create and user update flows.

#### Scenario: Localize empty-selection error
- **WHEN** a client submits an invalid empty `group_list` and the active language is Chinese or English
- **THEN** the system returns the corresponding localized message for the empty-selection validation error

#### Scenario: Localize virtual-only-selection error
- **WHEN** a client submits a virtual-only `group_list` and the active language is Chinese or English
- **THEN** the system returns the corresponding localized message for the normal-group-required validation error

### Requirement: Frontend blocks invalid group selections before submission
The user management frontend SHALL validate selected groups before submitting create or update requests and MUST block submission when no group is selected or when the selection lacks a normal group.

#### Scenario: Frontend blocks empty selection
- **WHEN** a user attempts to submit the create or edit form without selecting any group
- **THEN** the frontend prevents submission and displays the localized empty-selection validation message

#### Scenario: Frontend blocks virtual-only selection
- **WHEN** a user attempts to submit the create or edit form with only virtual groups selected
- **THEN** the frontend prevents submission and displays the localized normal-group-required validation message

#### Scenario: Frontend allows mixed selection with a normal group
- **WHEN** a user selects at least one normal group, with or without additional virtual groups, and submits the create or edit form
- **THEN** the frontend allows submission to proceed
