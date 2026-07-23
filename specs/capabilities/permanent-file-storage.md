# permanent-file-storage

> 支持文件上传时指定永久保存，跳过 7 天自动清理（仅对外 API）

## Requirements

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
