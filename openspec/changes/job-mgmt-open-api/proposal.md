## Why

胡彦团队将补丁管理作为第三方 app 对接到 bk-lite，需要调用作业管理的脚本执行、文件分发、任务查询等核心能力。当前这些能力仅通过 REST API + 前端鉴权暴露，无法供内网第三方 app 直接调用。需要在 NATS 网络上开放一组服务接口，并提供一个 REST 文件上传接口（因 NATS 消息体大小限制不适合传输二进制文件）。

## What Changes

- 新增 4 个 NATS handler（`bklite.job.script_execute`、`bklite.job.file_distribute`、`bklite.job.status_batch_query`、`bklite.job.detail_query`），无 token 鉴权，信任内网 NATS 通道
- 新增 1 个 REST API（`POST /api/job_mgmt/open/upload_file`），使用 `UserAPISecret` token 鉴权
- 新增回调机制：异步任务（脚本执行、文件分发）完成后，通过 HTTP POST 调用方传入的 `callback_url` 通知结果，失败重试 3 次（指数退避）
- JobExecution model 新增 `callback_url` 字段，记录回调地址
- 所有通过此接口创建的 execution 记录 `trigger_source` 设为 `api`

## Capabilities

### New Capabilities
- `job-open-api`: 作业管理对外开放接口，包含 NATS 服务接口（脚本执行、文件分发、状态查询、详情查询）、REST 文件上传接口、以及任务完成回调机制

### Modified Capabilities
（无）

## Impact

- **代码**：`apps/job_mgmt/nats_api.py`（新增 handler）、`apps/job_mgmt/views/`（新增 open upload view）、`apps/job_mgmt/models/`（JobExecution 加字段）、`apps/job_mgmt/services/execution_base_service.py`（回调逻辑）
- **API**：新增 1 个 REST endpoint，新增 4 个 NATS subject
- **依赖**：无新依赖，复用现有 nats_client、JetStreamService、APISecretAuthBackend
- **数据库**：JobExecution 表新增 `callback_url` nullable 字段，需要 migration
