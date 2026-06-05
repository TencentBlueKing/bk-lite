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
