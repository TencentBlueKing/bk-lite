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
# Try dedicated installer credentials first
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
