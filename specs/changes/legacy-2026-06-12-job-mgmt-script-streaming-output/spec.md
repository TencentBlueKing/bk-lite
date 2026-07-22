# Historical Superpowers change: 2026-06-12-job-mgmt-script-streaming-output

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-12-job-mgmt-script-streaming-output-design.md

- 日期：2026-06-12
- 状态：已评审，待实现
- 工作区：`.claude/worktrees/musing-chatterjee-a480b8`（分支 `claude/musing-chatterjee-a480b8`）

## 1. 背景与目标

job_mgmt 的脚本执行当前是**阻塞式**：`script_execution_runner` 用阻塞的 `execute_ssh` / `execute_local` RPC 调用，执行完才一次性把全量结果写入 `JobExecution.execution_results`。用户在长耗时脚本执行期间看不到任何输出，体验差。

目标：让脚本执行支持**实时流式输出**——用户停在执行详情页时，脚本 stdout/stderr 像终端一样逐行实时滚出；中途打开/刷新/断网重连时，能先看到该目标截至当前的**完整历史**，再接着实时滚动。

### 关键现状（已存在的能力，本设计复用）

| 环节 | 现状 |
|------|------|
| Go agent SSH 执行 | ✅ 已支持按行把 `streamEvent{execution_id, stream, line, timestamp}` publish 到 NATS 主题 `stream_log_topic`（`agents/nats-executor/ssh/executor.go`） |
| Go agent 本地执行（sidecar） | ❌ 仅对 SCP 做 debug 日志，stdout/stderr 不发 NATS（`agents/nats-executor/local/executor.go`） |
| Python RPC 客户端 | ✅ 已有 `execute_ssh_stream()`，带 `stream_logs` / `stream_log_topic` 参数（`server/apps/rpc/executor.py`） |
| Django 订阅 NATS | ✅ 已有 `subscribe_lines_sync()`（`server/nats_client/clients.py`）；JetStream 可用（`server/apps/rpc/jetstream.py`） |
| 前端 SSE 代理 | ✅ Next.js 代理自动识别并透传 `text/event-stream`（`web/src/app/(core)/api/proxy/[...path]/route.ts`） |
| 参考实现 | node_mgmt 安装器已把 `execute_ssh_stream` + `subscribe_lines_sync` 串成边订阅边落库（`server/apps/node_mgmt/tasks/installer.py`） |

因此本需求本质是**把已有的流式管道接到 job_mgmt 上**，并补齐回放缓冲、SSE 端点、前端展示，以及本地/Ansible 两条尚未支持流式的路径。

## 2. 设计决策（已与用户确认）

1. **交付方式**：真·实时推送，Django `StreamingHttpResponse(text/event-stream)`，非轮询。
2. **覆盖路径**：三条全覆盖，但**分阶段**——P1 SSH、P2 本地、P3 Ansible。
3. **迟到/重连行为**：需要「完整历史 + 继续实时」。
4. **回放缓冲**：NATS JetStream（复用现有 NATS 基建，不引入 Redis）。

## 3. 总体架构

```
┌─────────────┐  per-line publish        ┌────────────────────┐
│   agent     │ ───────────────────────► │  JetStream 流       │
│ (三条路径)   │  job.stream.{id}.{tk}    │  JOB_LOG_STREAM     │
└─────────────┘                          │  subjects=          │
                                         │   job.stream.>      │
                                         │  MaxAge=1h          │
                                         └─────────┬──────────┘
                                                   │ 临时有序消费者
                                                   │ filter=job.stream.{id}.>
                                                   │ DeliverPolicy.ALL
                                                   │ (历史回放 + 实时 tail 一条搞定)
┌─────────────┐   SSE(text/event-stream)          ▼
│  前端详情页  │ ◄──────────────────────── Django SSE 端点
│ 多目标终端   │  /executions/{id}/stream/  (StreamingHttpResponse, ASGI)
└─────────────┘
                  最终全量仍写 execution_results（权威历史，缓冲 TTL 后兜底）
```

**核心不变量**：`execute_*_stream` 这类 RPC **仍然是请求/响应**——执行结束照常返回全量结果写进 `execution_results`。流式只是「额外」边执行边 publish 行。最终结果的权威来源不变，流式是纯增量叠加，**对现有落库逻辑零侵入、低风险**。

## 4. 主题与数据模型

### 4.1 NATS 主题约定

```
job.stream.{execution_id}.{target_key}
```

- `target_key`：沿用 runner 里现有的 `target_info.get("node_id") or str(target_info.get("target_id"))`，与 `execution_results[].target_key` 一致，便于前端按目标分组。
- 行事件结构（沿用 agent 现有 `streamEvent`）：

```json
{ "execution_id": "...", "stream": "stdout|stderr", "line": "...", "timestamp": "RFC3339" }
```

- **结束哨兵**（新增）：finalize 时每个 target 发一条：

```json
{ "execution_id": "...", "target_key": "...", "type": "done", "status": "success|failed|timeout|cancelled" }
```

### 4.2 JetStream 流

- 流名：`JOB_LOG_STREAM`
- subjects：`job.stream.>`
- 保留：`MaxAge=3600s`（1h），`MaxBytes` 设一个合理上限（如 256MB），`Discard=Old`
- 幂等声明：服务启动时（`apps.py ready()` 或专用 management command）`add_stream`，已存在则跳过/更新配置。
- 自动过期，无需手动清理单次执行的数据。

> 注：agent 当前用核心 NATS `nc.Publish` 发到该主题。只要 JetStream 配置了捕获 `job.stream.>` 的流，核心发布会被 JetStream 自动落盘，**P1 无需改 Go agent**。

## 5. 分阶段实现

### P1 — SSH 手动目标（MANUAL）

改动集中在 Python 服务端 + SSE 端点 + 前端，agent 不动。

1. `ScriptExecutionRunner.execute_script_on_target`：SSH 分支由 `executor.execute_ssh(...)` 改为 `executor.execute_ssh_stream(..., execution_id=str(execution_id), stream_log_topic=f"job.stream.{execution_id}.{target_key}")`。返回值处理逻辑不变（仍取全量结果）。
2. `finalize_execution`（或 runner 收尾处）：每个 target 完成后向其主题 publish 一条 `done` 哨兵。
3. 新增 SSE 端点（见 §6）。
4. 新增前端实时终端（见 §7）。
5. 启动时声明 JetStream 流（见 §4.2）。

### P2 — 节点本地执行（NODE_MGMT / SYNC）

1. Go `agents/nats-executor/local/executor.go`：新增 `streamLogWriter`（按行 publish 到 `stream_log_topic`），结构照搬 `ssh/executor.go:142` 的 `newStreamLogWriter` / `Write` / `Flush` / `publish`；在 `req.StreamLogs` 为真时用 `io.MultiWriter` 同时写 outputCapture 和 streamWriter。`local/entity.go` 加 `StreamLogs` / `StreamLogTopic` / `ExecutionID` 字段。
2. Python `apps/rpc/executor.py`：新增 `execute_local_stream(...)`，与 `execute_ssh_stream` 对称，传 `stream_logs` / `stream_log_topic` / `execution_id`。
3. `execute_script_on_target` 本地分支改调 `execute_local_stream`。
4. Go 侧单测：照搬 `ssh/stream_writer_test.go`。

### P3 — Ansible / WinRM

1. `agents/ansible-executor`：用 ansible-runner 的 `event_handler` 回调，把每个事件的可读输出按行 publish 到 `stream_log_topic`。
2. Python 侧在提交 Ansible 任务时下发 `stream_log_topic`（`playbook_execution` / `execute_script_via_ansible` 相关入口）。
3. 结束哨兵：Ansible 是回调式异步，回调落库时补发 `done` 哨兵。

> P3 改动最大且与回调机制耦合，作为最后阶段；P1/P2 完成后骨架已稳定，P3 仅是新增一个生产端。

## 6. SSE 端点

- 路由：`GET /api/v1/job_mgmt/executions/{id}/stream/`
- 返回：`StreamingHttpResponse(async_generator, content_type="text/event-stream")`（ASGI，参考 `apps/core/utils/async_utils.py` 与 opspilot 的 SSE 实现）。
- **鉴权**：复用 job_mgmt 现有 team_authz / 权限校验，确认当前用户可见该 `execution`；无权返回 403（在进入流式前）。
- 逻辑：
  1. 校验执行存在 + 权限。
  2. 若执行已是终态：不建消费者，直接基于 `execution_results` 输出一次性历史后关闭（或返回普通 JSON 由前端走非流式分支，见 §7）。
  3. 否则 `nc = await get_nc_client()`，`js = nc.jetstream()`，建**临时有序/推送消费者**：`filter_subject=f"job.stream.{id}.>"`，`deliver_policy=ALL`。
  4. 迭代消息：行事件 → 按 `target_key` 包装成 SSE `data:` 事件下发；`done` 哨兵 → 标记该 target 完成。
  5. 关闭条件：所有 target 收到 `done`，或 DB 中 execution 已终态且流已 drain，或客户端断开。
  6. `finally`：`unsubscribe` + `nc.close()`，确保不泄漏连接。
- **降级**：JetStream 不可用/建消费者失败 → 不抛错阻断，转为输出 `execution_results` 当前快照 + 提示前端走轮询兜底。
- **限流/边界**：单连接行数/字节上限；行长度截断（Go 侧已有 output limit，JS 流 MaxBytes 兜底）。

## 7. 前端（执行详情页）

- **执行中**（status 非终态）：打开 `EventSource`（经代理）连 SSE 端点；按 `target_key` 渲染**多个终端面板**（与 `execution_results` 的 per-target 结构一致），逐行追加、自动滚动到底；区分 stdout/stderr 样式。
- **连接关闭 / 执行结束 / 收到全部 done**：回落展示 `execution_results` 的全量 stdout/stderr（权威结果）。
- **打开时已是终态**：不连 SSE，直接渲染 `execution_results`。
- 位置：`web/src/app/job/(pages)/execution/...` 执行详情/记录相关组件。

## 8. 错误处理与边界

- JetStream 不可用：SSE 降级为只读 `execution_results`，功能不阻断。
- agent publish 失败：仅影响实时观感，最终结果仍由 RPC 返回值落库，不影响正确性。
- 多目标并发：每个 target 独立子主题，互不串扰；前端独立面板。
- 取消执行：已有 `is_cancelled` 逻辑不变；取消的 target 发 `done{status:cancelled}`。
- 连接生命周期：SSE generator 内开/关 NATS 连接与消费者，客户端断开即清理。
- 敏感信息：脚本输出可能含敏感数据；SSE 端点复用现有脱敏/权限边界，不额外放宽。

## 9. 测试

### 9.0 方法与覆盖率要求（硬性约束）

- **严格 TDD**：每个新增/改动的函数都遵循 Red-Green-Refactor——先写失败测试、亲眼看它因「功能缺失」而失败、再写最小实现转绿、最后重构保持绿色。**禁止先写生产代码再补测试。**
- **覆盖率目标：新增/改动的 Python 模块行覆盖率 ≥ 90%**，用 `pytest-cov` 度量。范围限定为本功能新增/改动的模块（SSE 端点视图、runner 流式接线、`done` 哨兵、降级逻辑、`execute_local_stream` 等），不把真实 NATS/ASGI 端到端链路计入「单元」覆盖。
- **测量命令**（虚拟环境 `D:\app\venv\bkliteserver`）：
  ```
  uv run pytest apps/job_mgmt/tests/ \
    --cov=apps.job_mgmt.services.script_execution_runner \
    --cov=apps.job_mgmt.views.execution \
    --cov-report=term-missing
  ```
  （随实现补齐 `--cov` 目标模块；CI 阈值可加 `--cov-fail-under=90` 守门。）
- **Go 侧独立统计**：`local` executor 的流式代码用 `go test -cover` 覆盖，不计入上面的 Python 90%。
- 统一遵循 `server/docs/testing-guide.md` 分层（`_pure` / `_service` / `_views`）。

### 9.1 后端 `_views`：SSE 端点

- 鉴权拒绝（无权用户 403），在进入流式前返回。
- 终态执行 → 直接返回历史、不建消费者。
- mock JetStream 消费者：验证「先回放历史行 → 再实时行 → 收到全部 done 后关闭」。
- 部分 target 完成、其余进行中 → 不提前关闭。
- 客户端断开 → `finally` 正确清理（unsubscribe + close）。
- JetStream 不可用 / 建消费者抛错 → 降级返回 `execution_results` 快照、不抛 500。
- SSE 事件格式正确（`data:` + 按 `target_key` 分组 + stdout/stderr 区分）。

### 9.2 后端 `_service`：runner 接线

- SSH 分支以正确的 `stream_log_topic`（`job.stream.{id}.{target_key}`）/ `execution_id` 调用 `execute_ssh_stream`。
- 本地分支以正确参数调用 `execute_local_stream`。
- `execute_*_stream` 返回值仍正确映射到 `result`（success/failed/timeout 分支全覆盖）。
- finalize 为每个 target 发出 `done` 哨兵；取消的 target 发 `done{status:cancelled}`。
- 高危命令拦截、Windows 手动目标走 Ansible 等既有分支不回归。

### 9.3 Go：`local` executor `streamLogWriter`

- 照搬 `ssh/stream_writer_test.go`：按 `\n` 切分逐行 publish、Flush 残留、空行不发、`StreamLogs=false` 时零副作用。

### 9.4 回归

- 确认 `execution_results` 落库与现有行为一致（流式为纯增量，不改变最终结果）。
- 既有 job_mgmt 测试全绿。

## 10. 交付与验证流程

- 本任务**未经本地验证确认前，不合入 master**（不自动同步）。
- 每阶段（P1/P2/P3）独立可交付、独立验证。
- 功能完成后提供本地验证场景（含 SSH 实时滚动、中途刷新看完整历史、断网重连、多目标并发、JetStream 不可用降级）。

## 11. 范围外（YAGNI）

- 不做 WebSocket（SSE 足够，且代理已支持）。
- 不引入 Redis。
- 不做跨执行的日志检索/归档（JetStream 1h 过期 + `execution_results` 永久兜底即可）。
- 不改 Ansible 回调的整体机制（P3 仅新增事件 publish）。
