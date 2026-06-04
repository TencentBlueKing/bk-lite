## Why

Playbook archive handling still has two reliability gaps: server-side upload and preview flows eagerly read whole archives into memory, and both server and executor paths lack consistent resource bounds for archive size and expansion. A single oversized or highly expanded archive can therefore pressure API workers, transfer paths, and executor nodes with normal product permissions.

## What Changes

- Add archive admission guards for Playbook upload and upgrade so oversized or over-expanded archives are rejected before parsing.
- Add bounded archive preview handling so `preview_file` refuses oversized archives before whole-package reads and only processes allowed archive members.
- Add executor-side archive resource guards so downloaded ZIP packages are validated against member-count, member-size, and total-expanded-size limits before extraction.
- Replace whole-file Playbook relay reads in the job execution transfer path with bounded streaming-compatible handling.

## Capabilities

### New Capabilities
- `playbook-archive-resource-guards`: unified resource guard rules for Playbook archive upload, transfer, preview, and executor extraction.

### Modified Capabilities
- `playbook-zip-security`: ZIP handling must enforce resource limits in addition to path and symlink safety.
- `playbook-file-preview`: archive preview must reject oversized archives before in-memory expansion and preserve preview safety under resource pressure.

## Impact

- **server/apps/job_mgmt/serializers/playbook.py**: upload, upgrade, archive parsing, and preview extraction logic
- **server/apps/job_mgmt/views/playbook.py**: preview entry-point guards
- **server/apps/job_mgmt/services/playbook_execution.py**: Playbook archive relay path from MinIO to NATS object storage
- **agents/ansible-executor/service/ansible_runner.py**: download and extraction resource limits for Playbook ZIP archives
- **server/apps/job_mgmt/tests/** and **agents/ansible-executor/tests/**: regression coverage for archive admission, preview, transfer, and extraction limits
