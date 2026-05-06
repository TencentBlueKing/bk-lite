## ADDED Requirements

### Requirement: API secret read operations return preview-only values
The system SHALL return preview-only values for persisted API secrets in read operations. Read operations MUST NOT expose the full stored API secret after creation is complete.

#### Scenario: List API secrets
- **WHEN** a client requests the API secret list endpoint for the current user and team
- **THEN** each item includes `api_secret_preview` containing the first four characters of the stored secret
- **THEN** the response does not include the full `api_secret` value

#### Scenario: Retrieve a single API secret
- **WHEN** a client requests the API secret detail endpoint for an existing API secret
- **THEN** the response includes `api_secret_preview` containing the first four characters of the stored secret
- **THEN** the response does not include the full `api_secret` value

### Requirement: API secret creation reveals the full secret once
The system SHALL return the full generated API secret only in the successful create response so the client can present it immediately to the user.

#### Scenario: Create API secret successfully
- **WHEN** a client creates an API secret for a user and team that do not already have one
- **THEN** the response includes the full generated `api_secret`
- **THEN** the response remains associated with the created user, domain, and team

#### Scenario: Reject duplicate API secret creation
- **WHEN** a client attempts to create an API secret for a user and team that already have one
- **THEN** the system rejects the request with the existing duplicate-create behavior
- **THEN** the existing API secret remains unchanged

### Requirement: API secret management UI enforces one-time reveal behavior
The system-manager API secret page SHALL present preview-only values in the list view and SHALL present the full secret only in the immediate create-success flow.

#### Scenario: View API secret list in settings page
- **WHEN** a user opens the settings API secret page after at least one secret exists
- **THEN** the list displays `api_secret_preview` instead of the full secret
- **THEN** the list does not provide an action to copy the full secret

#### Scenario: Handle successful secret creation in settings page
- **WHEN** a user successfully creates a new API secret from the settings page
- **THEN** the page opens a success modal that displays the full secret returned by the create response
- **THEN** the modal warns that the secret cannot be viewed again after closing
- **THEN** the modal requires explicit user confirmation before it can be closed through the primary action

#### Scenario: Return to preview-only state after confirmation
- **WHEN** the user confirms they have saved the secret in the create-success modal
- **THEN** the modal closes
- **THEN** the page refreshes the API secret list
- **THEN** the refreshed page shows only `api_secret_preview`
