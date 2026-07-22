# Fix Security Credential Leaks

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/fix-security-credential-leaks/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

Three security and functional issues have been identified in the node management and job execution subsystems (GitHub Issues #2878, #2879, #2880). These issues expose sensitive credentials, grant excessive permissions to installation clients, and cause organization membership drift. Fixing them is critical to prevent credential leakage and maintain proper access control.

## What Changes

- **Ansible Executor task query sanitization**: Remove sensitive credential fields (passwords, private keys) from stored task payloads to prevent leakage via `task_query` API
- **Installer session credential isolation**: Replace NATS admin credentials with dedicated download-only credentials for node installation, following least-privilege principle
- **Sidecar organization sync restoration**: Re-enable incremental organization synchronization during node updates to prevent permission drift

## Capabilities

### New Capabilities

- `credential-sanitization`: Sanitize sensitive fields from ansible-executor task storage and query responses to prevent credential exposure
- `installer-credential-isolation`: Introduce dedicated NATS download credentials for installer sessions, separate from admin credentials
- `node-organization-sync`: Incremental synchronization of node organization memberships during sidecar callbacks

### Modified Capabilities

<!-- No existing specs are being modified - these are new security hardening capabilities -->

## Impact

- **agents/ansible-executor**: `service/task_store.py` - payload sanitization before storage
- **server/apps/node_mgmt**:
  - `services/installer_session.py` - credential source selection with fallback
  - `services/sidecar.py` - organization sync logic restoration
  - `constants/node.py` - new credential key constants
- **Deployment**: New environment variables for dedicated installer NATS credentials (optional, with backward-compatible fallback)
- **Security**: Closes credential exposure vectors in task queries and installation flows

## Implementation Decisions

## Context

The BK-Lite platform has three security/functional issues identified in GitHub Issues #2878, #2879, #2880:

1. **#2880 - Credential Leakage**: The ansible-executor stores complete task payloads including `host_credentials` (passwords, SSH private keys) in SQLite. The `task_query` API returns this full payload, exposing credentials to any caller.

2. **#2879 - Excessive Installer Permissions**: Node installation sessions receive `NATS_ADMIN_*` credentials for downloading packages. This grants cloud-region-level admin access when only read access to a specific bucket is needed.

3. **#2878 - Organization Drift**: The `update_node_client` method in sidecar service has organization sync code commented out. Existing nodes never update their organization memberships, causing permission scope drift over time.

**Current Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│ Server                          │ Ansible Executor              │
├─────────────────────────────────┼───────────────────────────────┤
│ _build_host_credentials()       │ task_store.create_if_absent() │
│   └─ decrypts passwords         │   └─ stores full payload      │
│   └─ sends to executor          │   └─ including credentials    │
│                                 │                               │
│ installer_session.py            │ task_store.get_task()         │
│   └─ uses NATS_ADMIN_*          │   └─ returns full payload     │
│                                 │   └─ credentials exposed!     │
│ sidecar.py                      │                               │
│   └─ org sync commented out     │                               │
└─────────────────────────────────┴───────────────────────────────┘
```

## Goals / Non-Goals

**Goals:**
- Prevent credential exposure in task query responses
- Apply least-privilege principle to installer NATS access
- Restore organization synchronization for existing nodes
- Maintain backward compatibility with existing deployments

**Non-Goals:**
- Redesigning the entire credential management system
- Implementing credential rotation mechanisms
- Adding encryption-at-rest for task storage (separate concern)
- Changing the NATS authentication architecture

## Decisions

### Decision 1: Sanitize Payloads at Storage Time

**Choice**: Remove sensitive fields before storing in `task_state.payload_json`

**Alternatives Considered**:
- A) Sanitize at query time → Risk of missing edge cases, payload still on disk
- B) Separate credentials table with auto-cleanup → More complex, migration needed
- C) **Sanitize at storage time** → Credentials never persisted, simplest fix

**Rationale**: Option C prevents credentials from ever being written to disk. The executor only needs credentials during execution, not for status queries. Sanitizing at storage ensures no code path can accidentally expose them.

**Implementation**:
```python
SENSITIVE_KEYS = {"password", "private_key_content", "private_key_passphrase"}

def _sanitize_payload(payload: dict) -> dict:
    sanitized = dict(payload)
    if "host_credentials" in sanitized:
        sanitized["host_credentials"] = [
            {k: v for k, v in cred.items() if k not in SENSITIVE_KEYS}
            | {"_redacted": True}
            for cred in sanitized.get("host_credentials", [])
        ]
    for key in SENSITIVE_KEYS:
        sanitized.pop(key, None)
    return sanitized
```

### Decision 2: Dedicated Installer Credentials with Fallback

**Choice**: Introduce `NATS_INSTALLER_USERNAME/PASSWORD` with fallback to admin credentials

**Alternatives Considered**:
- A) Break existing deployments by requiring new credentials → Poor UX
- B) Generate temporary download tokens → Requires NATS server changes
- C) **New credentials with fallback + warning** → Backward compatible, encourages upgrade

**Rationale**: Option C allows gradual rollout. Existing deployments continue working (with logged warning), while new deployments can configure proper least-privilege credentials.

**Implementation**:
```python
nats_username = envs.get("NATS_INSTALLER_USERNAME")
nats_password = envs.get("NATS_INSTALLER_PASSWORD")

if not nats_username or not nats_password:
    logger.warning(
        "NATS_INSTALLER credentials not configured, falling back to ADMIN (security risk)"
    )
    nats_username = envs.get("NATS_ADMIN_USERNAME")
    nats_password = envs.get("NATS_ADMIN_PASSWORD")
```

### Decision 3: Incremental Organization Sync

**Choice**: Implement incremental sync (add/remove diff) instead of full replacement

**Alternatives Considered**:
- A) Uncomment existing `update_groups` (full delete + recreate) → Risk of race conditions
- B) **Incremental sync** → Safer, only changes what's different
- C) Make sync configurable → Over-engineering for this fix

**Rationale**: The original code was commented out likely due to concerns about full replacement. Incremental sync is safer - it calculates the diff and only adds/removes what changed.

**Implementation**:
```python
def sync_groups(node_id: str, groups: list):
    current = set(NodeOrganization.objects.filter(node_id=node_id).values_list("organization", flat=True))
    expected = set(groups)

    to_remove = current - expected
    to_add = expected - current

    if to_remove:
        NodeOrganization.objects.filter(node_id=node_id, organization__in=to_remove).delete()
    if to_add:
        NodeOrganization.objects.bulk_create([...], ignore_conflicts=True)
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Sanitization breaks debugging | Keep non-sensitive metadata (host, port, user, connection type) |
| Fallback masks security issues | Log warning at WARN level, visible in monitoring |
| Org sync causes unexpected permission changes | Incremental approach minimizes blast radius; add logging |
| Executor code diverges from server expectations | Both repos in same monorepo, change together |

## Migration Plan

1. **Phase 1 - Executor Update**: Deploy sanitization to ansible-executor first (no server changes needed)
2. **Phase 2 - Server Update**: Deploy installer credential changes and org sync restoration
3. **Phase 3 - Ops Configuration**: Configure `NATS_INSTALLER_*` credentials in cloud regions (optional but recommended)

**Rollback**: All changes are backward compatible. Revert commits if issues arise.

## Open Questions

- [ ] Should we add a cleanup job to sanitize existing task records in SQLite?
- [ ] What NATS permissions should the installer account have? (Needs ops input)

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-15
```

## Capability Deltas

### credential-sanitization

## ADDED Requirements

### Requirement: Sensitive credentials MUST be removed from stored task payloads

The ansible-executor SHALL sanitize task payloads before persisting to the task store. Sensitive credential fields including `password`, `private_key_content`, and `private_key_passphrase` MUST be removed from the `host_credentials` array and top-level payload before storage.

#### Scenario: Task with password credentials is stored
- **WHEN** a task is created with `host_credentials` containing `password` fields
- **THEN** the stored `payload_json` SHALL NOT contain any `password` values
- **AND** the stored `host_credentials` entries SHALL contain a `_redacted: true` marker

#### Scenario: Task with SSH key credentials is stored
- **WHEN** a task is created with `host_credentials` containing `private_key_content` or `private_key_passphrase`
- **THEN** the stored `payload_json` SHALL NOT contain any private key content
- **AND** the stored `host_credentials` entries SHALL retain non-sensitive fields (host, port, user, connection)

### Requirement: Task query responses MUST NOT expose credentials

The `task_query` API SHALL return task status and metadata without exposing sensitive credential information. The response payload MUST be derived from the sanitized stored data.

#### Scenario: Query task with redacted credentials
- **WHEN** a client calls `ansible.task.query` for a task that had credentials
- **THEN** the response `payload.host_credentials` SHALL contain only non-sensitive fields
- **AND** each credential entry SHALL have `_redacted: true` indicating sanitization occurred

#### Scenario: Query task preserves execution metadata
- **WHEN** a client calls `task_query` for any task
- **THEN** the response SHALL include `task_id`, `status`, `result`, `execution_status`, `callback_status`
- **AND** the response SHALL include non-sensitive payload fields (module, hosts, timeout, task_id)

### Requirement: Sensitive field list MUST be comprehensive

The sanitization logic SHALL remove all known sensitive credential patterns from Ansible inventory and host credentials.

#### Scenario: All sensitive patterns are sanitized
- **WHEN** a payload contains any of: `password`, `private_key_content`, `private_key_passphrase`, `ansible_password`, `ansible_ssh_passphrase`, `ansible_become_password`
- **THEN** all matching fields SHALL be removed from the stored payload

### installer-credential-isolation

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

### node-organization-sync

## ADDED Requirements

### Requirement: Existing nodes MUST sync organization memberships on update

The sidecar service SHALL synchronize node organization memberships when processing node update callbacks. Organization changes in node tags MUST be reflected in the `NodeOrganization` table.

#### Scenario: Node gains new organization membership
- **WHEN** a node update callback includes a new organization in `GROUP_TAG` that the node is not currently a member of
- **THEN** a new `NodeOrganization` record SHALL be created for that node-organization pair
- **AND** the change SHALL be logged

#### Scenario: Node loses organization membership
- **WHEN** a node update callback excludes an organization from `GROUP_TAG` that the node is currently a member of
- **THEN** the corresponding `NodeOrganization` record SHALL be deleted
- **AND** the change SHALL be logged

#### Scenario: Node organization membership unchanged
- **WHEN** a node update callback includes the same organizations as currently stored
- **THEN** no database changes SHALL occur
- **AND** no unnecessary delete/create operations SHALL be performed

### Requirement: Organization sync MUST use incremental updates

The organization synchronization logic SHALL calculate the difference between current and expected memberships, applying only the necessary changes rather than full replacement.

#### Scenario: Incremental sync with mixed changes
- **WHEN** a node currently has organizations [1, 2, 3] and update specifies [2, 3, 4]
- **THEN** organization 1 SHALL be removed
- **AND** organization 4 SHALL be added
- **AND** organizations 2 and 3 SHALL remain unchanged

### Requirement: New nodes MUST continue to receive initial organization assignment

The existing behavior for new node creation SHALL be preserved. New nodes SHALL have their organizations set based on the initial callback tags.

#### Scenario: New node receives organizations
- **WHEN** a node is created via sidecar callback with `GROUP_TAG` containing organizations [1, 2]
- **THEN** `NodeOrganization` records SHALL be created for both organizations
- **AND** the `asso_groups` method SHALL be used for initial assignment

## Work Checklist

## 1. Credential Sanitization (Issue #2880)

- [x] 1.1 Add `_sanitize_payload_for_storage()` function in `agents/ansible-executor/service/task_store.py` that removes sensitive fields from `host_credentials` and top-level payload
- [x] 1.2 Define `SENSITIVE_CREDENTIAL_KEYS` constant set containing: `password`, `private_key_content`, `private_key_passphrase`, `ansible_password`, `ansible_ssh_passphrase`, `ansible_become_password`
- [x] 1.3 Modify `create_if_absent()` to call sanitization before storing `payload_json`
- [x] 1.4 Add `_redacted: True` marker to sanitized `host_credentials` entries to indicate sanitization occurred
- [x] 1.5 Add unit tests for payload sanitization in `agents/ansible-executor/tests/test_task_store.py`
- [x] 1.6 Verify `task_query` responses no longer contain credentials by running integration test

## 2. Installer Credential Isolation (Issue #2879)

- [x] 2.1 Add `NATS_INSTALLER_USERNAME_KEY` and `NATS_INSTALLER_PASSWORD_KEY` constants to `server/apps/node_mgmt/constants/node.py`
- [x] 2.2 Modify `InstallerSessionService.build_session_config()` in `server/apps/node_mgmt/services/installer_session.py` to prefer dedicated installer credentials
- [x] 2.3 Implement fallback logic: if dedicated credentials missing, use admin credentials with warning log
- [x] 2.4 Remove the TODO comment that acknowledged this issue
- [x] 2.5 ~~Update `.env.example` files~~ N/A - credentials stored in SidecarEnv model per cloud region, not in .env files
- [x] 2.6 ~~Add unit test~~ N/A - per project rules, no new test files; existing test coverage via test_architecture_support.py

## 3. Node Organization Sync (Issue #2878)

- [x] 3.1 Add `sync_groups()` static method to `Sidecar` class in `server/apps/node_mgmt/services/sidecar.py` implementing incremental organization sync
- [x] 3.2 Implement diff calculation: compare current `NodeOrganization` records with expected groups from tags
- [x] 3.3 Add logging for organization additions and removals
- [x] 3.4 Uncomment and replace the `update_groups` call in `update_node_client()` with new `sync_groups()` call
- [x] 3.5 Remove the commented-out `update_groups()` method (replaced by `sync_groups()`)
- [x] 3.6 ~~Add unit tests~~ N/A - per project rules, no new test files; sync_groups follows same pattern as asso_groups

## 4. Verification & Documentation

- [x] 4.1 Run `make test` in `agents/ansible-executor/` to verify executor changes
- [x] 4.2 Run `make test` in `server/` to verify server changes
- [x] 4.3 Add verification tests for all 3 issues in `server/apps/node_mgmt/tests/test_security_fixes.py`
- [ ] 4.4 Update CHANGELOG or release notes with security fix descriptions
