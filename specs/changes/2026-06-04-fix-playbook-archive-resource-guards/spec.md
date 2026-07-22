# 2026 06 04 Fix Playbook Archive Resource Guards

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-04-fix-playbook-archive-resource-guards/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

Playbook archive handling crosses four code paths today:

1. `server/apps/job_mgmt/serializers/playbook.py` parses upload and upgrade archives and still reads the whole archive into memory.
2. `server/apps/job_mgmt/views/playbook.py` preview flow calls archive extraction helpers that also read the whole archive before validating the requested member.
3. `server/apps/job_mgmt/services/playbook_execution.py` relays Playbook files from MinIO to NATS object storage by fully reading the archive into memory first.
4. `agents/ansible-executor/service/ansible_runner.py` downloads and extracts executor ZIP archives with path safety checks but without archive-size, member-count, or expanded-size bounds.

These gaps mean one oversized or highly expanded archive can stress both the API plane and the executor plane. The fix needs to be cross-cutting so the same archive policy is applied before parsing, previewing, transferring, and extracting.

## Goals / Non-Goals

**Goals:**
- Introduce explicit archive guardrails for upload, upgrade, preview, transfer, and executor extraction.
- Reject unsafe or oversized archives before eager in-memory reads or unchecked extraction.
- Keep user-facing API contracts stable aside from explicit validation failures for guarded cases.
- Reuse one archive-policy model so server and executor do not diverge on what is acceptable.

**Non-Goals:**
- Add support for new archive formats beyond the existing ZIP / tar.gz / tgz set.
- Redesign Playbook storage backends or NATS object store semantics.
- Build a general-purpose streaming archive framework for unrelated modules.
- Change frontend preview UX beyond surfacing existing validation failures.

## Decisions

### Decision 1: Introduce a shared server-side archive policy helper

**Choice:** Add a focused helper in `job_mgmt` for archive metadata inspection and policy enforcement, then call it from upload, upgrade, and preview paths.

**Rationale:** The server currently duplicates archive reads across parse and preview helpers. A shared guardrail layer keeps the limit model consistent and reduces the chance that one path gets fixed while another still reads arbitrary archive sizes.

**Alternative considered:** Inline checks separately into each serializer and preview helper. Rejected because it would duplicate logic and make future limit tuning error-prone.

### Decision 2: Guard before content extraction, not after

**Choice:** Validate archive total size and member metadata before reading file contents or extracting members wherever possible.

**Rationale:** The current problem is order-of-operations: the code loads the archive first and only later enforces per-file preview limits. Guarding earlier is the only way to prevent API memory pressure and executor expansion risk.

### Decision 3: Use bounded streaming for Playbook relay

**Choice:** Replace whole-file relay reads in `playbook_execution.py` with chunked copy semantics and enforce the same archive-size ceiling before transfer.

**Rationale:** Even with safer upload admission, existing stored archives still flow through the relay path. Bounded transfer closes that second amplification point without changing storage interfaces.

### Decision 4: Extend ZIP safety to resource limits in executor

**Choice:** Keep the existing path and symlink safety model in `_safe_extract_zip()` but add member-count, per-member-size, and total-expanded-size checks during extraction.

**Rationale:** Executor extraction is the last line of defense and must remain self-protecting even if a dangerous archive bypasses the server path or arrives from pre-existing stored data.

## Risks / Trade-offs

- **[Risk] Limits that are too small could reject legitimate Playbook bundles** → **Mitigation:** choose conservative defaults and keep server and executor thresholds aligned.
- **[Risk] Archive inspection may still require limited metadata reads for some formats** → **Mitigation:** inspect metadata without loading full member contents and only decode the requested preview member after checks pass.
- **[Risk] Transfer refactor could introduce backend compatibility issues** → **Mitigation:** preserve existing storage interfaces and only change how bytes are read and forwarded.
- **[Risk] Existing large stored archives may start failing on preview or execution** → **Mitigation:** fail fast with explicit validation errors rather than letting workers or executors degrade under load.

## Migration Plan

1. Add server-side archive guard helpers and wire them into upload, upgrade, and preview flows.
2. Refactor Playbook relay to bounded transfer with the same archive limit policy.
3. Add executor ZIP resource guards and tests.
4. Run targeted `job_mgmt` and `ansible-executor` tests covering guarded archives and normal archives.
5. Roll back by reverting the change set if needed; no schema or API version migration is required.

## Open Questions

- Whether archive policy constants should live under `job_mgmt` only or in a more reusable module shared with executor.
- Whether tarball preview should get the same member-count and expanded-size checks immediately or in a follow-up after ZIP parity.

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-02
```

## Capability Deltas

### playbook-archive-resource-guards

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

### playbook-file-preview

## ADDED Requirements

### Requirement: 预览前必须校验归档资源上限

系统 SHALL 在 Playbook 文件预览前校验归档总大小和可接受的 archive 元数据范围，避免通过预览路径触发整包高内存处理。

#### Scenario: 超大归档预览被拒绝
- **WHEN** 用户请求预览的 Playbook 归档总大小超过配置限制
- **THEN** 系统返回拒绝结果而不是先将整包读入内存

#### Scenario: 合法归档仍可预览目标文件
- **WHEN** 用户请求预览的 Playbook 归档在配置限制内且目标成员满足现有文本预览规则
- **THEN** 系统正常返回目标文件内容

### playbook-zip-security

## MODIFIED Requirements

### Requirement: Playbook ZIP 解压必须使用安全函数

Playbook ZIP 文件解压时，系统 SHALL 使用 `_safe_extract_zip()` 函数同时执行路径安全检查和资源限制检查，防止路径遍历、符号链接写入以及异常 archive expansion 导致的磁盘或内存压力。

#### Scenario: 正常 ZIP 文件解压成功
- **WHEN** 用户上传包含合法路径且 archive 元数据在限制范围内的 Playbook ZIP 文件
- **THEN** 系统成功解压文件到 workspace 目录

#### Scenario: 恶意路径遍历 ZIP 被拒绝
- **WHEN** 用户上传包含 `../` 路径遍历条目的 ZIP 文件
- **THEN** 系统拒绝解压并抛出 ValueError

#### Scenario: 符号链接 ZIP 条目被拒绝
- **WHEN** 用户上传包含符号链接条目的 ZIP 文件
- **THEN** 系统拒绝解压并抛出 ValueError

#### Scenario: 绝对路径 ZIP 条目被拒绝
- **WHEN** 用户上传包含绝对路径条目的 ZIP 文件
- **THEN** 系统拒绝解压并抛出 ValueError

#### Scenario: ZIP 成员数量超限被拒绝
- **WHEN** Playbook ZIP 成员数量超过配置上限
- **THEN** 系统拒绝解压并抛出 ValueError

#### Scenario: ZIP 解压总量超限被拒绝
- **WHEN** Playbook ZIP 的总展开字节数超过配置上限
- **THEN** 系统拒绝解压并抛出 ValueError

## Work Checklist

## 1. Server-side archive admission guards

- [x] 1.1 Add a shared Playbook archive policy helper in `server/apps/job_mgmt` for raw size, member count, single-member size, and total expanded size checks
- [x] 1.2 Apply the archive policy to `PlaybookCreateSerializer.validate_file()` and `PlaybookUpgradeSerializer.validate_file()`
- [x] 1.3 Refactor archive parsing helpers so upload and upgrade flows avoid eager whole-archive reads before guard checks
- [x] 1.4 Add preview guard checks so `preview_file` rejects oversized archives before whole-package processing

## 2. Transfer and executor protections

- [x] 2.1 Refactor `server/apps/job_mgmt/services/playbook_execution.py` to avoid whole-archive in-memory relay and fail oversized stored archives early
- [x] 2.2 Extend `agents/ansible-executor/service/ansible_runner.py::_safe_extract_zip()` with ZIP member-count, per-member-size, and total-expanded-size limits
- [x] 2.3 Ensure executor download and extraction paths use the same bounded archive policy for Playbook ZIP handling

## 3. Regression coverage and verification

- [x] 3.1 Add `job_mgmt` tests for archive upload / upgrade rejection and preview rejection under archive resource limits
- [x] 3.2 Add `ansible-executor` tests for ZIP member-count and expanded-size guard failures
- [x] 3.3 Run the targeted `job_mgmt` and `ansible-executor` test suites covering the new archive guard behavior
