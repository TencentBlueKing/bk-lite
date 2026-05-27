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
