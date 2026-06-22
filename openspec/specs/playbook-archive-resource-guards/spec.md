## Purpose

定义 Playbook 归档上传、升级与中继过程中的资源限制主规格，确保归档在准入和转发阶段都遵守体积与展开边界。

## ADDED Requirements

### Requirement: Playbook archive upload and upgrade must enforce archive resource limits
The system SHALL reject Playbook archive uploads and upgrades when archive metadata exceeds configured limits for raw archive size, member count, single-member size, or total expanded size.

#### Scenario: Oversized archive upload is rejected
- **WHEN** a user uploads a Playbook archive whose raw file size exceeds the configured archive limit
- **THEN** the server SHALL reject the request before parsing archive contents

#### Scenario: Over-expanded archive is rejected during admission
- **WHEN** a user uploads or upgrades a Playbook archive whose member metadata exceeds the configured member-count, single-member-size, or total-expanded-size limits
- **THEN** the server SHALL reject the archive before persisting it for Playbook use

### Requirement: Playbook relay must avoid whole-archive in-memory transfer
The system SHALL transfer Playbook archives from object storage to NATS object storage without fully reading the archive into memory first and SHALL fail transfer when the archive exceeds the configured size limit.

#### Scenario: Relay rejects oversized stored archive
- **WHEN** Playbook execution attempts to relay a stored archive whose object size exceeds the configured archive limit
- **THEN** the relay path SHALL fail before loading the full archive into application memory

#### Scenario: Relay streams acceptable archive
- **WHEN** Playbook execution relays an archive within the configured limit
- **THEN** the system SHALL transfer the archive without constructing an in-memory full-file copy
