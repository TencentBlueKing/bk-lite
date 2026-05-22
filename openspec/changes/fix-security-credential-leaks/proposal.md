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
