## ADDED Requirements

### Requirement: Installer sessions MUST use dedicated download credentials

The installer session service SHALL prefer dedicated NATS download credentials (`NATS_INSTALLER_USERNAME`, `NATS_INSTALLER_PASSWORD`) over admin credentials when building session configurations.

#### Scenario: Dedicated credentials are configured
- **WHEN** `NATS_INSTALLER_USERNAME` and `NATS_INSTALLER_PASSWORD` are set in cloud region environment
- **THEN** the session config `storage.nats_username` and `storage.nats_password` SHALL use these dedicated credentials
- **AND** no warning SHALL be logged

#### Scenario: Dedicated credentials are not configured
- **WHEN** `NATS_INSTALLER_USERNAME` or `NATS_INSTALLER_PASSWORD` is missing from cloud region environment
- **THEN** the system SHALL fall back to `NATS_ADMIN_USERNAME` and `NATS_ADMIN_PASSWORD`
- **AND** a warning SHALL be logged indicating the security risk of using admin credentials

### Requirement: New credential constants MUST be defined

The node management constants SHALL define new keys for installer-specific NATS credentials to enable least-privilege access.

#### Scenario: Constants are available for configuration
- **WHEN** the node_mgmt module is loaded
- **THEN** `NodeConstants.NATS_INSTALLER_USERNAME_KEY` SHALL equal `"NATS_INSTALLER_USERNAME"`
- **AND** `NodeConstants.NATS_INSTALLER_PASSWORD_KEY` SHALL equal `"NATS_INSTALLER_PASSWORD"`

### Requirement: Backward compatibility MUST be maintained

The installer session service SHALL continue to function with existing deployments that only have admin credentials configured.

#### Scenario: Legacy deployment without dedicated credentials
- **WHEN** a cloud region has only `NATS_ADMIN_*` credentials configured
- **THEN** the installer session SHALL successfully build a valid configuration
- **AND** nodes SHALL be able to download installation packages
