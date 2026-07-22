# 2026 06 05 Add Distribution File Team Validation

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-add-distribution-file-team-validation/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

`DELETE /api/v1/job_mgmt/api/open/delete_file` 接口当前没有做组校验，任何持有有效 API Secret 的用户都可以删除任意文件（只要知道 file_id 和 file_key）。这是一个安全漏洞，需要确保只有同组用户才能删除文件。

## What Changes

- `DistributionFile` 模型添加 `team` 字段，记录文件归属的团队
- `OpenFileUploadView` 上传时保存当前用户的 team（取 `user.group_list[0]`）
- `OpenFileDeleteView` 删除时校验文件的 team 与当前用户的 team 一致
- 历史数据（`team=None`）不做迁移，新数据必须有 team

## Capabilities

### New Capabilities

- `distribution-file-team-ownership`: 文件分发记录的团队归属与权限校验

### Modified Capabilities

<!-- 无需修改现有 spec -->

## Impact

- **模型**: `server/apps/job_mgmt/models/distribution_file.py` - 添加 team 字段
- **视图**: `server/apps/job_mgmt/views/open_api.py` - 上传/删除接口添加 team 逻辑
- **数据库**: 需要 migration 添加 team 字段（nullable，允许历史数据为空）
- **API 行为变更**: 删除接口会拒绝跨组删除（返回 404 或 403）

## Implementation Decisions

## Context

当前 `DistributionFile` 模型没有 `team` 字段，导致文件上传后无法追踪归属团队。删除接口只校验 `file_id + file_key`，任何持有有效 API Secret 的用户都可以删除任意文件。

现有代码库中，其他模型（如 `Script`、`Playbook`、`ScheduledTask`）都有 `team` 字段，并在操作时进行组校验。

## Goals / Non-Goals

**Goals:**
- 为 `DistributionFile` 添加 `team` 字段，记录文件归属
- 上传时自动记录当前用户的 team（取 `user.group_list[0]`）
- 删除时校验文件的 team 与当前用户的 team 一致

**Non-Goals:**
- 不迁移历史数据（`team=None` 的记录保持原样）
- 不支持文件跨组共享
- 不修改内部 `DistributionFileViewSet`（仅修改 open API）

## Decisions

### 1. team 字段类型：IntegerField (nullable)

**选择**: `team = models.IntegerField(null=True, blank=True)`

**理由**:
- 与 `UserAPISecret.team` 类型一致（IntegerField）
- 允许 null 以兼容历史数据
- 简单直接，不需要 JSONField（文件只属于一个 team）

**备选方案**:
- JSONField（支持多 team）- 过度设计，当前需求不需要

### 2. team 来源：user.group_list[0]

**选择**: 从 `request.user.group_list[0]` 获取

**理由**:
- `APISecretAuthBackend` 已将 `UserAPISecret.team` 设置到 `user.group_list`
- 与其他接口保持一致的取值方式

### 3. 删除校验失败的响应：404

**选择**: 文件不存在或 team 不匹配时返回 404

**理由**:
- 不泄露文件是否存在的信息（安全考虑）
- 与当前行为一致（文件不存在时 continue，最终返回 deleted=0）

### 4. 历史数据处理：不迁移

**选择**: `team=None` 的历史记录保持原样，新记录必须有 team

**理由**:
- 用户明确要求不处理旧数据
- 历史文件可能已被使用或清理，迁移意义不大

**影响**: 历史文件（`team=None`）无法被任何人通过 open API 删除（因为 team 校验会失败）

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 历史文件无法通过 open API 删除 | 可通过内部 admin 或定时清理任务处理 |
| `user.group_list` 为空时上传失败 | 在上传接口添加校验，返回明确错误 |

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-27
```

## Capability Deltas

### distribution-file-team-ownership

## ADDED Requirements

### Requirement: 文件上传时记录团队归属

系统 SHALL 在文件上传时记录当前用户的团队 ID（取 `user.group_list[0]`）。

#### Scenario: 正常上传记录 team
- **WHEN** 用户通过 `POST /api/v1/job_mgmt/api/open/upload_file` 上传文件
- **THEN** 系统创建 `DistributionFile` 记录，`team` 字段为当前用户的 `group_list[0]`

#### Scenario: 用户无 team 时上传失败
- **WHEN** 用户的 `group_list` 为空
- **THEN** 系统返回 400 错误，提示 "用户未关联团队"

### Requirement: 文件删除时校验团队归属

系统 SHALL 在删除文件时校验文件的 `team` 与当前用户的 `team` 一致。

#### Scenario: 同组用户删除成功
- **WHEN** 用户请求删除文件，且文件的 `team` 与用户的 `group_list[0]` 一致
- **THEN** 系统删除文件并返回成功

#### Scenario: 跨组删除被拒绝
- **WHEN** 用户请求删除文件，但文件的 `team` 与用户的 `group_list[0]` 不一致
- **THEN** 系统不删除文件（视为文件不存在），返回 `deleted: 0`

#### Scenario: 历史文件（无 team）无法删除
- **WHEN** 用户请求删除 `team=None` 的历史文件
- **THEN** 系统不删除文件（team 校验失败），返回 `deleted: 0`

## Work Checklist

## 1. 模型层修改

- [x] 1.1 在 `DistributionFile` 模型添加 `team` 字段（`IntegerField(null=True, blank=True)`）
- [x] 1.2 生成并执行数据库迁移（`python manage.py makemigrations job_mgmt && python manage.py migrate`）

## 2. 上传接口修改

- [x] 2.1 在 `OpenFileUploadView.post()` 中获取 `user.group_list[0]` 作为 team
- [x] 2.2 添加校验：如果 `user.group_list` 为空，返回 400 错误
- [x] 2.3 创建 `DistributionFile` 时传入 `team` 参数

## 3. 删除接口修改

- [x] 3.1 在 `OpenFileDeleteView.delete()` 中获取当前用户的 team
- [x] 3.2 修改查询条件：`DistributionFile.objects.get(id=file_id, file_key=file_key, team=user_team)`

## 4. 测试验证

- [x] 4.1 更新 `test_open_upload.py` 中的上传测试，验证 team 被正确保存
- [x] 4.2 添加删除测试：同组删除成功
- [x] 4.3 添加删除测试：跨组删除失败（返回 deleted=0）
- [x] 4.4 运行 `make test` 确保所有测试通过
