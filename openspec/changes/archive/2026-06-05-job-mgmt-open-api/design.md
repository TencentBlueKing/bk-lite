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
