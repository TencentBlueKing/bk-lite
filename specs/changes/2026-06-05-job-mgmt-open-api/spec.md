# 2026 06 05 Job Mgmt Open Api

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-job-mgmt-open-api/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

当前作业管理（job_mgmt）的核心能力（脚本执行、文件分发、任务查询）仅通过 Django REST API 暴露，依赖前端 session/JWT 鉴权。第三方 app（补丁管理）部署在内网，需要通过 NATS 网络直接调用这些能力。

现有基础设施：
- `nats_client` 框架：`@nats_client.register` 注册 handler，`nats_listener` 命令自动订阅，subject 格式 `{NATS_NAMESPACE}.{func_name}`
- `JetStreamService`：文件存储使用 NATS JetStream Object Store（非 MinIO/S3）
- `APISecretAuthBackend`：基于 `UserAPISecret.api_secret` 的 token 鉴权，已有实现
- `ExecutionTaskBaseService`：统一的执行基类，包含 `prepare_execution` → `finalize_execution` 生命周期
- `ansible_task_callback`：Ansible 异步执行完成后的回调入口，更新 JobExecution 状态

## Goals / Non-Goals

**Goals:**
- 开放 4 个 NATS 接口供第三方 app 调用作业管理能力
- 提供 1 个 REST 文件上传接口（NATS 消息体 1MB 限制不适合二进制文件传输）
- 任务完成后通过 HTTP POST 回调通知调用方
- 输出调用文档

**Non-Goals:**
- 不做 NATS 接口的 token 鉴权（信任内网 NATS 通道）
- 不支持 Playbook 执行（第三方仅需脚本执行和文件分发）
- 不改变现有作业管理 REST API 和前端逻辑
- 不引入消息队列做回调（用简单的 HTTP POST + 重试）

## Decisions

### 1. 文件上传走 REST API，其余走 NATS

**选择**：文件上传用 REST `multipart/form-data`，其余 4 个接口用 NATS request-reply。

**替代方案**：
- 全部走 NATS，文件 base64 编码放消息体 → 受 `max_payload`（默认 1MB）限制，补丁文件可能远超
- 全部走 NATS，文件分片传输 → 等于在 NATS 上重新实现 multipart upload，复杂度高、无现成库

**理由**：NATS 适合 JSON 消息交互，HTTP 适合二进制流传输。混合方案是最务实的选择。

### 2. NATS handler 复用现有 service 层逻辑

**选择**：NATS handler 内部直接调用 `execute_script_task` / `distribute_files_task`（Celery task 函数），与 REST view 走同一条执行路径。

**替代方案**：
- 抽取公共 service 函数供 view 和 NATS handler 共用 → 需要重构现有 view，改动面大

**理由**：现有 Celery task 函数已经封装了完整的执行流程（创建 execution → 调度执行 → 回调更新状态）。NATS handler 只需创建 `JobExecution` 记录并调用 task 函数即可，无需重构。

### 3. 回调机制：HTTP POST + 3 次指数退避重试

**选择**：任务终态时，检查 `callback_url` 字段，通过 `requests.post` 发送结果，失败重试 3 次（1s → 2s → 4s），超过后放弃。

**替代方案**：
- NATS publish 到调用方 subject → 调用方要求 HTTP POST
- 写入失败队列 + 管理界面 → 过度设计

**理由**：调用方（补丁管理）明确要求 HTTP POST 回调。重试 3 次后放弃是合理的，调用方可用 `status_batch_query` 兜底轮询。

### 4. 回调触发点

**选择**：在两个位置触发回调：
- `ExecutionTaskBaseService.finalize_execution()`：sidecar/节点管理 同步执行完成时
- `ansible_task_callback()`：Ansible 异步执行回调返回时

**替代方案**：
- 只在 `finalize_execution` 中触发 → 无法覆盖 Ansible 异步路径（Ansible 结果通过 NATS callback 回来，不经过 `finalize_execution`）
- 用 Django signal 监听 JobExecution status 变更 → 隐式触发，不如显式调用清晰

**理由**：当前执行路径有两条终态更新入口，必须在两处都加回调。抽取公共的 `_send_callback` 方法避免重复。

### 5. REST 文件上传鉴权

**选择**：使用 `UserAPISecret.api_secret` 作为 token，通过 `Authorization: Token <api_secret>` header 传递，复用 `APISecretAuthBackend` 验证。

**替代方案**：
- 使用现有 JWT token → 第三方 app 需要先登录获取 token，流程复杂
- 新建独立的 API Key 体系 → 过度设计

**理由**：`UserAPISecret` + `APISecretAuthBackend` 已有完整实现，直接复用。`api_secret` 绑定了 username + domain + team，满足权限隔离需求。

### 6. `callback_url` 存储

**选择**：JobExecution model 新增 `callback_url = CharField(max_length=512, null=True, blank=True)` 字段。

**理由**：回调 URL 是执行维度的属性，跟随 execution 记录存储最自然。nullable 表示非 NATS 调用的 execution 无需回调。

## Risks / Trade-offs

- **[回调丢失]** HTTP POST 失败 3 次后放弃，调用方可能漏收通知 → 调用方需实现 `status_batch_query` 轮询兜底
- **[无鉴权的 NATS 接口]** 内网任何 NATS 客户端均可调用 → 当前与现有 NATS handler（system_mgmt 40+ 接口）策略一致，风险可接受
- **[回调 URL 安全]** 恶意 NATS 调用者可设置任意 callback_url 做 SSRF → 可限制 callback_url 为内网地址，或后续加白名单，当前阶段信任内网
- **[两处触发回调]** `finalize_execution` 和 `ansible_task_callback` 都要加回调逻辑 → 抽取 `_send_callback` 公共方法，保持一致性

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-30
```

## Capability Deltas

### job-open-api

## ADDED Requirements

### Requirement: 脚本执行 NATS 接口
系统 SHALL 提供 NATS handler `bklite.job.script_execute`，接收脚本执行请求，创建 JobExecution 记录并异步执行，同步返回 task_id。

请求参数与现有 `QuickExecuteSerializer` 对齐：
- `name`（必填）：作业名称
- `target_source`（必填）：`node_mgmt` | `manual`
- `target_list`（必填）：目标列表，格式同现有 REST API
  - node_mgmt: `{node_id, name, ip, os, cloud_region_id}`
  - manual: `{target_id, name, ip}`
- `script_type`（必填）：`shell` | `python` | `powershell` | `bat`
- `script_content`（必填）：脚本内容
- `params`（可选）：参数列表 `[{name, value}]`
- `timeout`（可选，默认 600）：超时秒数
- `team`（必填）：团队 ID 列表
- `callback_url`（可选）：任务完成回调地址

返回：`{result: true, data: {task_id: <int>}}`

系统 SHALL 将 `trigger_source` 设为 `api`。
系统 SHALL 执行高危命令检测，命中禁止规则时返回错误。

#### Scenario: 成功提交脚本执行
- **WHEN** 第三方 app 通过 NATS 发送合法的脚本执行请求
- **THEN** 系统创建 JobExecution 记录（status=pending, trigger_source=api），触发异步执行，同步返回 `{result: true, data: {task_id}}`

#### Scenario: 脚本命中高危规则
- **WHEN** 请求的 script_content 命中 team 范围内的 forbidden 级别高危命令规则
- **THEN** 系统返回 `{result: false, message: "脚本包含高危命令，禁止执行: ..."}`，不创建 execution 记录

#### Scenario: 目标列表为空
- **WHEN** 请求的 target_list 为空数组
- **THEN** 系统返回 `{result: false, message: "目标列表不能为空"}`

### Requirement: 文件上传 REST 接口
系统 SHALL 提供 REST API `POST /api/job_mgmt/open/upload_file`，接收 multipart/form-data 文件上传，存储到 NATS JetStream Object Store，返回 file_id 和 file_key。

鉴权方式：`Authorization: Token <api_secret>`，通过 `UserAPISecret` + `APISecretAuthBackend` 验证。

返回：`{result: true, data: {file_id: <int>, file_key: <string>, original_name: <string>}}`

#### Scenario: 成功上传文件
- **WHEN** 携带合法 api_secret token 发送文件上传请求
- **THEN** 系统将文件存入 JetStream Object Store，创建 DistributionFile 记录，返回 file_id、file_key、original_name

#### Scenario: token 无效
- **WHEN** 请求未携带 token 或 token 无效
- **THEN** 系统返回 HTTP 401 Unauthorized

#### Scenario: 未携带文件
- **WHEN** 请求未包含 file 字段
- **THEN** 系统返回 HTTP 400 Bad Request

### Requirement: 文件分发 NATS 接口
系统 SHALL 提供 NATS handler `bklite.job.file_distribute`，基于已上传的 file_ids 创建文件分发任务，异步执行，同步返回 task_id。

请求参数与现有 `FileDistributionSerializer` 对齐：
- `name`（必填）：作业名称
- `file_ids`（必填）：已上传文件 ID 列表
- `target_source`（必填）：`node_mgmt` | `manual`
- `target_list`（必填）：目标列表
- `target_path`（必填）：目标路径
- `overwrite_strategy`（可选，默认 `overwrite`）：`overwrite` | `skip`
- `timeout`（可选，默认 600）：超时秒数
- `team`（必填）：团队 ID 列表
- `callback_url`（可选）：任务完成回调地址

返回：`{result: true, data: {task_id: <int>}}`

系统 SHALL 执行高危路径检测，命中禁止规则时返回错误。
系统 SHALL 验证 file_ids 对应的 DistributionFile 记录均存在。

#### Scenario: 成功提交文件分发
- **WHEN** 第三方 app 通过 NATS 发送合法的文件分发请求，file_ids 对应的文件均存在
- **THEN** 系统创建 JobExecution 记录（job_type=file_distribution, trigger_source=api），触发异步执行，返回 task_id

#### Scenario: 部分文件不存在
- **WHEN** file_ids 中包含不存在或已过期的文件 ID
- **THEN** 系统返回 `{result: false, message: "部分文件不存在或已过期"}`

#### Scenario: 目标路径命中高危规则
- **WHEN** target_path 命中 team 范围内的 forbidden 级别高危路径规则
- **THEN** 系统返回 `{result: false, message: "目标路径为高危路径，禁止分发: ..."}`

### Requirement: 批量查询作业状态 NATS 接口
系统 SHALL 提供 NATS handler `bklite.job.status_batch_query`，支持批量查询 JobExecution 状态。

请求参数：
- `task_ids`（必填）：任务 ID 列表

返回：
```json
{
  "result": true,
  "data": [
    {"task_id": 123, "status": "success", "total_count": 3, "success_count": 3, "failed_count": 0}
  ]
}
```

系统 SHALL 对不存在的 task_id 在结果中标记 `status: "not_found"`。

#### Scenario: 查询多个已存在的任务
- **WHEN** 传入多个有效的 task_ids
- **THEN** 系统返回每个任务的 status、total_count、success_count、failed_count

#### Scenario: 部分 task_id 不存在
- **WHEN** task_ids 中包含不存在的 ID
- **THEN** 不存在的 ID 在结果中返回 `{task_id, status: "not_found"}`，其余正常返回

### Requirement: 查询单个作业详情 NATS 接口
系统 SHALL 提供 NATS handler `bklite.job.detail_query`，返回单个 JobExecution 的完整信息。

请求参数：
- `task_id`（必填）：任务 ID

返回字段：task_id、name、job_type、status、script_type、script_content、timeout、started_at、finished_at、total_count、success_count、failed_count、target_list、execution_results。

execution_results 中每个目标包含：target_key、name、ip、status、stdout、stderr、exit_code、error_message。

#### Scenario: 查询已完成的任务
- **WHEN** 传入存在的 task_id，对应任务已完成
- **THEN** 系统返回完整的执行详情，包含每个目标的执行结果

#### Scenario: 查询不存在的任务
- **WHEN** 传入不存在的 task_id
- **THEN** 系统返回 `{result: false, message: "任务不存在"}`

### Requirement: 任务完成 HTTP 回调
当 JobExecution 进入终态（success / failed / timeout）且记录了 `callback_url` 时，系统 SHALL 通过 HTTP POST 向 `callback_url` 发送任务结果通知。

回调 Body：
```json
{
  "task_id": 123,
  "status": "success",
  "total_count": 3,
  "success_count": 3,
  "failed_count": 0,
  "finished_at": "2026-04-30T10:01:30Z"
}
```

系统 SHALL 在回调失败时进行最多 3 次重试，使用指数退避策略（1s → 2s → 4s）。
系统 SHALL 在 `finalize_execution` 和 `ansible_task_callback` 两个终态入口触发回调。
重试 3 次后仍失败时，系统 SHALL 记录日志并放弃（调用方可通过 status_batch_query 兜底查询）。

#### Scenario: 脚本执行完成后回调成功
- **WHEN** 携带 callback_url 的脚本执行任务完成（sidecar 路径，经 finalize_execution）
- **THEN** 系统 POST 回调数据到 callback_url，收到 2xx 响应后完成

#### Scenario: Ansible 异步任务完成后回调成功
- **WHEN** 携带 callback_url 的任务通过 Ansible 异步执行完成（经 ansible_task_callback）
- **THEN** 系统 POST 回调数据到 callback_url

#### Scenario: 回调失败后重试
- **WHEN** 首次 POST 回调返回非 2xx 或连接失败
- **THEN** 系统按 1s → 2s → 4s 间隔重试，最多 3 次

#### Scenario: 重试耗尽
- **WHEN** 3 次重试均失败
- **THEN** 系统记录 warning 日志，不再重试

#### Scenario: 无 callback_url 的任务
- **WHEN** JobExecution 的 callback_url 为空
- **THEN** 系统不执行回调，正常完成

## Work Checklist

## 1. Model 层变更

- [x] 1.1 JobExecution model 新增 `callback_url` 字段（CharField, max_length=512, null=True, blank=True）
- [x] 1.2 生成并执行 migration（`python manage.py makemigrations job_mgmt && python manage.py migrate`）

## 2. 回调机制

- [x] 2.1 新建 `apps/job_mgmt/services/callback_service.py`，实现 `send_callback(execution: JobExecution)` 方法：检查 callback_url 是否存在，POST 回调数据，3 次指数退避重试（1s → 2s → 4s）
- [x] 2.2 在 `ExecutionTaskBaseService.finalize_execution()` 末尾调用 `send_callback`（sidecar/节点管理 同步执行路径）
- [x] 2.3 在 `ansible_task_callback()` 任务完成更新状态后调用 `send_callback`（Ansible 异步执行路径）

## 3. NATS 接口实现

- [x] 3.1 在 `apps/job_mgmt/nats_api.py` 新增 `@register` handler `job_script_execute`：参数校验、高危命令检测、创建 JobExecution（trigger_source=api）、调用 execute_script_task，返回 task_id
- [x] 3.2 在 `apps/job_mgmt/nats_api.py` 新增 `@register` handler `job_file_distribute`：校验 file_ids、高危路径检测、创建 JobExecution（trigger_source=api）、调用 distribute_files_task，返回 task_id
- [x] 3.3 在 `apps/job_mgmt/nats_api.py` 新增 `@register` handler `job_status_batch_query`：根据 task_ids 批量查询 JobExecution 状态，不存在的 ID 返回 status=not_found
- [x] 3.4 在 `apps/job_mgmt/nats_api.py` 新增 `@register` handler `job_detail_query`：根据 task_id 查询单个 JobExecution 完整信息含 execution_results

## 4. REST 文件上传接口

- [x] 4.1 新建 `apps/job_mgmt/views/open_api.py`，实现 `OpenFileUploadView`：使用 `APISecretAuthBackend` 鉴权（`Authorization: Token <api_secret>`），接收 multipart/form-data，存储到 JetStream Object Store，创建 DistributionFile 记录，返回 file_id、file_key、original_name
- [x] 4.2 在 `apps/job_mgmt/urls.py` 注册路由 `POST /api/job_mgmt/open/upload_file`

## 5. 测试

- [x] 5.1 为 4 个 NATS handler 编写单元测试（mock NATS 调用和 task 执行）
- [x] 5.2 为文件上传 REST 接口编写单元测试（mock JetStream 和 APISecretAuthBackend）
- [x] 5.3 为 callback_service 编写单元测试（mock requests.post，验证重试逻辑）
- [x] 5.4 运行 `make test` 确保全量测试通过

## 6. 调用文档

- [x] 6.1 编写接口调用文档，包含：5 个接口的请求/响应 schema、鉴权方式说明、回调机制说明、调用流程示例
