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
