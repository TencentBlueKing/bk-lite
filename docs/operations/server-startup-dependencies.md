# Server 启动顺序与服务依赖边界

本文记录 Server 生产容器的启动顺序、初始化与运行期边界，以及修改相关代码时
必须遵守的依赖规则。图片用于辅助理解，本文文字和当前代码、配置是实现判断的
依据。

## 事实来源

修改启动脚本、初始化命令、服务依赖或部署配置前，必须核对：

- `server/support-files/release/startup.sh`
- `server/apps/core/management/commands/batch_init.py`
- `server/support-files/release/supervisor/`

## 阶段定义与启动不变量

- **启动期**：从 `startup.sh` 开始到执行 `supervisord -n` 之前，包括
  `batch_init` 及其调用的所有管理命令。
- **运行期**：`supervisord -n` 执行后，由 Supervisor 拉起并守护的 API、
  Worker、Beat、Listener 和 Bridge 等进程。
- `batch_init` 完成前，所有 Supervisor 管理的进程都必须视为**不存在且未就绪**；
  不得根据端口可访问、Broker 可连接或配置已生成推断其消费者已经启动。
- 基础设施可连接只表示传输通道存在，不表示对应的 API、消息消费者、RPC
  responder 或任务执行器已就绪。
- Supervisor 中相同 `priority` 只表示同一启动阶段，不保证进程间的启动顺序或
  就绪顺序。

## Server 生产容器启动顺序

1. `migrate`（关键初始化；失败时保留原始退出码并阻断后续启动）
2. `createcachetable`
3. `collectstatic`
4. `batch_init`（启动硬门禁，失败会使 `startup.sh` 退出）
5. 条件清理配置并设置进程数
6. `supervisord -n`
7. Supervisor 才启动 Django API、默认 Celery Worker、独立 Dashboard Report
   Render Worker、Celery Beat、`nats_listener` 和 SNMP Bridge 等运行期进程。
   若 `INSTALL_APPS` 为空（全装）或包含 `opspilot`，另有独立 OpsPilot Celery
   Worker 消费 `opspilot_channel` / `opspilot_wiki` / `opspilot_maintenance`；
   未安装 opspilot 时 `startup.sh` 删除该 supervisor 配置，不拉起该进程。
   默认 Celery Worker 只听默认队列，不消费上述 OpsPilot 队列。

迁移失败时，启动脚本保留 `manage.py migrate` 的标准错误与退出码并停止容器，
不会执行缓存表、静态资源、批量初始化或 Supervisor。运维应先按迁移原始错误修复
数据库连通性、权限、锁冲突或坏迁移，再重新启动容器；若当前版本无法完成迁移，
回滚到上一镜像，并按迁移是否可逆决定是否执行 `manage.py migrate <app> <target>`。
数据库 Schema 是所有 Server ORM 读写和权限数据完整性的共同前提；旧或部分 Schema
会使核心 API、Worker 和 Listener 读取不存在的表或字段，并可能在混合 Schema 上产生
部分写入。因此迁移属于关键初始化，失败后继续拉起运行期进程不具备安全服务条件。

Dashboard Report Render Worker 只消费 `dashboard_report_render` 队列，默认并发
为 2。它和默认 Celery Worker 均属于运行期进程，只能在 `batch_init` 成功后由
Supervisor 启动；启动期不得投递任务并等待它消费。

生产环境必须为 Render Worker 和后续 Delivery Worker 配置同一个受控共享目录
`DASHBOARD_REPORT_ARTIFACT_ROOT`。该目录只保存当前发送及必要重试窗口内的
短期 PDF，并按 Execution 子目录隔离；未配置时 Render 明确失败，不回退到容器
本地 `/tmp`。临时文件清理属于运行期能力，不得加入 `batch_init`。

## Stargazer 独立服务启动边界

Stargazer 已移除 ARQ Worker。其容器只启动 Sanic 进程；Sanic 在
`before_server_start` 中建立普通异步 Redis Client、初始化统一采集运行时，并在
`after_server_start` 启动事件循环延迟采样和 Host Remote callback sweeper。

- 不再要求“先启动 Stargazer Worker”，仓库也不再包含 Worker Supervisor 配置；
- Redis 可连接是新采集任务安全接纳的硬条件，因为运行租约和 fencing 采用 fail-closed；
- NATS responder 和 Host Remote 下游仍属于运行期依赖，不能在 Server `batch_init` 中调用并等待；
- callback sweep、重试和可重建状态对账只能在 Sanic 启动后执行，失败不得形成 Server 启动循环；
- 停服时先停止接纳，宽限等待/取消运行，再停止 callback/观测任务并关闭 NATS、Redis。

## 启动期允许与禁止事项

`batch_init` 只能执行确定性的本地初始化、必要的数据库初始化，以及明确属于
启动硬依赖的基础设施操作。所有操作都应可重复执行；非关键、可重建的外部资源
失败不得阻断服务启动。

禁止在启动期：

- 调用 Django API、Celery Worker、Celery Beat、`nats_listener`、SNMP Bridge
  或其他由当前容器 Supervisor 启动的进程。
- 发起需要上述进程消费或响应的 HTTP、RPC、NATS request/reply、消息投递确认
  或异步任务，并同步等待结果。
- 用 `sleep`、延长超时、无限重试或健康检查等待尚未进入启动阶段的运行期进程。
- 仅捕获异常后继续保留错误阶段的依赖；容错不能消除循环依赖。
- 因为 NATS Broker 可连接，就假定 Server 的 NATS responder 已经就绪。

需要运行期服务的对账、同步和外部资源声明，应移到 Supervisor 启动后的运行期
入口，例如幂等的后台任务、定时任务或带重试和补偿的对账流程。必要时启动期只
记录“待处理”状态，由运行期消费者接管，不得同步等待处理完成。

APM 的 Collector、Trace/Metric Store 和通知 responder 健康检查属于这类运行期
任务。通知 responder 必须通过 System Management 公开探针实际确认消费者已注册；
探针超时或 responder 缺失只更新 `notification_responder=degraded`，不得退出或重启
API、Worker、Listener，也不得被移动到 `batch_init`。

## 已知故障链

下面的依赖会形成自锁，禁止重新引入：

```text
startup.sh
→ batch_init
→ cmdb / reconcile_node_mgmt_sync
→ 发起 NATS RPC
→ nats_listener 尚未启动，RPC 失败或超时
→ batch_init 非零退出
→ startup.sh exit 1，supervisord 不执行
→ nats_listener 始终无法启动
```

增加重试、延长超时或捕获异常都不会消除这条循环依赖。正确处理方式是把对账
操作移到运行期，或由启动期仅记录待处理状态，再由运行期任务幂等接管。

## CMDB 实例 UUID 清洗（运行期收敛，非启动硬依赖）

CMDB 实例 UUID 结构迁移为 Django `0045_instance_uuid_transition`（仅 schema）。
存量图节点 / 边端点 / PostgreSQL 活动引用的数据清洗（含订阅快照、采集
instances/结果快照、Operation snapshot/未成功 Outbox；不迁变更历史 JSON 与
系统操作日志）：

- 维护命令：`migrate_cmdb_instance_uuid_refs --dry-run|--apply|--verify`
- 维护命令：`migrate_oa_cmdb_instance_uuid_refs --dry-run|--apply|--verify`
- 运行期任务：`apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime`

部署链路约定：

- `batch_init` **只**调用 `ensure_uuid_migration_periodic_task()` 并
  `migrate_cmdb_instance_uuid_runtime.delay()`（消息入队，等 Worker 起来后执行）；
- **禁止**在 `batch_init` / `startup.sh` 同步执行 `--apply` 并阻断 `supervisord`；
- Worker/Beat 起来后幂等 `--apply`；失败只打日志并由 `*/5` 周期任务重试；
- 多 Worker 用缓存锁互斥；清洗完成可禁用周期任务减少空跑。

大流量切换仍可用维护窗口停写后手动 `--apply/--verify` 留证据；见
`docs/operations/cmdb-instance-uuid-cutover.md`。

禁止把清洗失败用 `migrate || true`、吞异常或 `sleep` 掩盖后继续恢复写流量
（指启动硬门禁路径；运行期任务的失败重试不属于启动门禁）。


## Agent 修改检查清单

新增或调整初始化操作前，必须逐项确认：

1. 标明调用方和被调用方分别属于启动期、运行期还是独立基础设施。
2. 查明被调用方由谁、在何时启动；若由当前容器 Supervisor 启动，则启动期
   禁止依赖。
3. 区分“Broker/端口可达”和“消费者/responder 已就绪”，不得混为一谈。
4. 明确失败是否应阻断启动；非关键操作必须移到运行期并具备幂等、重试和补偿。
5. 覆盖依赖缺失、响应超时、重复执行和容器重启场景的测试。
6. 启动顺序或依赖关系发生变化时，同步更新本文及下列图表。

## 图表

- [项目服务与依赖拓扑](../project-service-dependency.png)
- [Server 启动顺序、初始化边界与禁止依赖](../server-startup-dependency.png)
- [两页可编辑 Draw.io 源文件](../project-service-dependency.drawio)
### Stargazer 采集运行时的 Redis 例外

Stargazer 的 Redis 运行状态不是可延后声明的外部资源：任务重入、租约心跳、fencing 和跨 Pod 回调抢占都依赖它保证同一任务不会并发产生副作用。因此启动时的 `PING` 失败会主动阻止 Stargazer 就绪；这属于采集安全的关键依赖，而不是用同步等待掩盖 Supervisor 内部启动顺序。ARQ 队列及其 worker 依赖已移除。
