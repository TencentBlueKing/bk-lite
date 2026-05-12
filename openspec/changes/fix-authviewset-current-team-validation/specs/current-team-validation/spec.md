## ADDED Requirements

### Requirement: Validate current_team against user permissions

The system SHALL validate that the `current_team` cookie value is within the user's authorized team list (`user.group_list`) before using it for data filtering in `AuthViewSet`.

#### Scenario: User accesses data with valid current_team
- **WHEN** user has `group_list = [{"id": 1}, {"id": 2}]` and `current_team` cookie is `1`
- **THEN** system SHALL proceed with data filtering using `current_team=1`

#### Scenario: User accesses data with invalid current_team
- **WHEN** user has `group_list = [{"id": 1}]` and `current_team` cookie is `999`
- **THEN** system SHALL raise `PermissionDenied` exception and return HTTP 403

#### Scenario: User accesses data with non-numeric current_team
- **WHEN** `current_team` cookie is `"abc"` (non-numeric)
- **THEN** system SHALL use default value `0` (existing behavior from `_parse_current_team_cookie`)
- **AND** validation SHALL check if `0` is in user's `group_list`

### Requirement: Superuser bypass validation

The system SHALL allow superusers to access any team's data without validation.

#### Scenario: Superuser accesses data with any current_team
- **WHEN** user has `is_superuser=True` and `current_team` cookie is `999`
- **THEN** system SHALL proceed with data filtering using `current_team=999` without checking `group_list`

#### Scenario: Non-superuser must pass validation
- **WHEN** user has `is_superuser=False` and `current_team` cookie is not in their `group_list`
- **THEN** system SHALL raise `PermissionDenied` exception and return HTTP 403

### Requirement: Extract team IDs from group_list format

The system SHALL correctly extract team IDs from `user.group_list` which has format `[{"id": 1, "name": "...", "parent_id": 0}, ...]`.

#### Scenario: Parse group_list with multiple teams
- **WHEN** user has `group_list = [{"id": 1, "name": "A"}, {"id": 3, "name": "B"}]`
- **THEN** system SHALL recognize `1` and `3` as valid `current_team` values

#### Scenario: Handle empty group_list
- **WHEN** user has `group_list = []` and is not superuser
- **THEN** system SHALL raise `PermissionDenied` for any `current_team` value
