# 2026 05 27 Add Permanent File Storage

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-27-add-permanent-file-storage/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

当前文件上传接口（`/api/open/upload_file`）上传的文件会在 7 天后被定时任务自动清理。第三方应用（如补丁管理）需要能够上传永久保存的文件，避免重要文件被意外删除。

## What Changes

- **仅对外 API** (`/api/open/upload_file`) 新增 `permanent` 参数，允许第三方应用指定文件永久保存
- `DistributionFile` 模型新增 `is_permanent` 字段标识文件保存策略
- 定时清理任务排除永久保存的文件
- 文件删除接口保持不变（永久文件仍可手动删除）
- **内部接口不变**：`DistributionFileViewSet` 等内部上传接口统一使用临时保存策略

## Capabilities

### New Capabilities

- `permanent-file-storage`: 仅对外 API 支持文件上传时指定永久保存，跳过 7 天自动清理

### Modified Capabilities

<!-- 无需修改现有 spec，这是新增能力 -->

## Impact

- **Model**: `apps/job_mgmt/models/distribution_file.py` - 新增字段，需要数据库迁移
- **API**: `POST /api/v1/job_mgmt/api/open/upload_file` - 新增可选参数 `permanent`（仅此接口）
- **Task**: `cleanup_expired_distribution_files_task` - 修改查询条件
- **内部接口**: `DistributionFileViewSet.upload` 等内部接口**不做修改**，保持临时保存
- **兼容性**: 向后兼容，`permanent` 参数默认为 `false`，现有调用方无需修改

## Implementation Decisions

## Context

当前 `DistributionFile` 模型仅记录 `original_name`、`file_key`、`created_at`，所有文件统一在 7 天后被 `cleanup_expired_distribution_files_task` 清理。第三方应用需要上传永久保存的文件（如补丁包、配置文件），当前机制无法满足。

**现有代码位置**：
- Model: `server/apps/job_mgmt/models/distribution_file.py`
- Upload API: `server/apps/job_mgmt/views/open_api.py` → `OpenFileUploadView`
- Cleanup Task: `server/apps/job_mgmt/tasks.py` → `cleanup_expired_distribution_files_task`

## Goals / Non-Goals

**Goals:**
- 仅对外 API 支持上传时指定文件永久保存
- 永久文件不被定时清理任务删除
- 向后兼容，现有调用方无需修改

**Non-Goals:**
- 不实现文件过期时间自定义（如 30 天、90 天）
- 不实现永久文件的配额限制
- **不修改内部文件上传接口**（`DistributionFileViewSet` 等）- 内部统一使用临时保存策略

## Decisions

### 1. 使用布尔字段 `is_permanent` 而非过期时间字段

**选择**: `is_permanent: BooleanField(default=False)`

**备选方案**:
- `expires_at: DateTimeField(null=True)` - null 表示永久

**理由**:
- 需求明确只需要"永久/临时"两种状态
- 布尔字段语义清晰，查询简单
- 避免过度设计，后续如需自定义过期时间可再扩展

### 2. API 参数使用 `permanent` 而非 `is_permanent`

**选择**: 请求参数名为 `permanent`（布尔值）

**理由**:
- API 参数命名习惯不带 `is_` 前缀
- 与内部字段名 `is_permanent` 区分，保持各层命名惯例

### 3. 参数通过 form-data 传递而非 query string

**选择**: `permanent` 作为 multipart/form-data 的一部分

**理由**:
- 与现有 `file` 字段保持一致的传递方式
- 避免 URL 参数与 body 混用

### 4. 仅对外 API 提供永久保存参数

**选择**: 只在 `OpenFileUploadView`（对外 API）添加 `permanent` 参数

**备选方案**:
- 所有上传接口统一支持 `permanent` 参数

**理由**:
- 内部使用场景（如 Playbook 执行临时文件）无需永久保存
- 限制永久文件入口，降低存储滥用风险
- 内部接口保持简单，减少维护成本

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 永久文件无限增长占用存储 | 保留手动删除接口；后续可增加配额/告警 |
| 误设为永久导致无法清理 | 默认 `permanent=false`，需显式指定 |
| 数据库迁移影响线上 | 新增字段有默认值，迁移无锁表风险 |
| 内部接口无法使用永久保存 | 设计如此，内部场景无此需求 |

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-27
```

## Capability Deltas

### permanent-file-storage

## ADDED Requirements

### Requirement: 对外文件上传接口支持永久保存参数

**仅对外** 文件上传接口 `POST /api/v1/job_mgmt/api/open/upload_file` SHALL 接受可选参数 `permanent`（布尔值），用于指定文件是否永久保存。

- 参数 `permanent` 默认为 `false`
- 当 `permanent=true` 时，文件 SHALL 被标记为永久保存
- 当 `permanent=false` 或未传递时，文件 SHALL 遵循现有 7 天清理策略
- **内部接口**（如 `DistributionFileViewSet.upload`）SHALL NOT 支持此参数，统一使用临时保存策略

#### Scenario: 对外 API 上传永久文件

- **WHEN** 第三方应用通过对外 API 上传文件并设置 `permanent=true`
- **THEN** 系统返回 `file_id` 和 `file_key`，文件记录的 `is_permanent` 字段为 `true`

#### Scenario: 对外 API 上传临时文件（默认行为）

- **WHEN** 第三方应用通过对外 API 上传文件且未传递 `permanent` 参数
- **THEN** 系统返回 `file_id` 和 `file_key`，文件记录的 `is_permanent` 字段为 `false`

#### Scenario: 内部接口始终临时保存

- **WHEN** 内部系统通过 `DistributionFileViewSet.upload` 上传文件
- **THEN** 文件记录的 `is_permanent` 字段始终为 `false`，无论是否传递任何参数

---

### Requirement: 定时清理任务排除永久文件

定时清理任务 `cleanup_expired_distribution_files_task` SHALL 仅清理 `is_permanent=false` 且创建时间超过 7 天的文件。

- 永久文件（`is_permanent=true`）SHALL NOT 被定时清理任务删除
- 永久文件仍可通过 `DELETE /api/open/delete_file` 接口手动删除

#### Scenario: 清理任务跳过永久文件

- **WHEN** 定时清理任务执行
- **THEN** 系统仅删除 `is_permanent=false` 且 `created_at < 7天前` 的文件记录及其存储文件

#### Scenario: 永久文件可手动删除

- **WHEN** 调用方对永久文件调用删除接口
- **THEN** 系统删除该文件的存储文件和数据库记录

---

### Requirement: 数据模型支持永久标识

`DistributionFile` 模型 SHALL 包含 `is_permanent` 字段：

- 类型：`BooleanField`
- 默认值：`False`
- 含义：`True` 表示永久保存，`False` 表示遵循 7 天清理策略

#### Scenario: 新字段向后兼容

- **WHEN** 数据库迁移执行
- **THEN** 现有记录的 `is_permanent` 字段自动设置为 `False`，保持原有清理行为

## Work Checklist

## 1. Model 层修改

- [x] 1.1 在 `DistributionFile` 模型添加 `is_permanent` 字段（`BooleanField(default=False)`）
- [x] 1.2 更新模型 docstring 说明新字段用途
- [x] 1.3 执行 `makemigrations` 生成迁移文件
- [x] 1.4 执行 `migrate` 应用迁移

## 2. 对外 API 层修改

- [x] 2.1 修改 `OpenFileUploadView.post` 方法，解析 `permanent` 参数
- [x] 2.2 创建 `DistributionFile` 记录时传入 `is_permanent` 值
- [x] 2.3 更新 API docstring 说明新参数
- [x] 2.4 **确认内部接口 `DistributionFileViewSet.upload` 不做修改**（保持临时保存）

## 3. 清理任务修改

- [x] 3.1 修改 `cleanup_expired_distribution_files_task` 查询条件，添加 `is_permanent=False` 过滤

## 4. 文档更新

- [x] 4.1 更新 `open_api.md` 文档，说明 `permanent` 参数用法

## 5. 测试验证

- [x] 5.1 更新 `test_open_upload.py`，添加永久文件上传测试用例
- [x] 5.2 运行 `make test` 确保所有测试通过
