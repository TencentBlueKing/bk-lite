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

1. `migrate`（当前失败会被 `|| true` 忽略）
2. `createcachetable`
3. `collectstatic`
4. `batch_init`（启动硬门禁，失败会使 `startup.sh` 退出）
5. 条件清理配置并设置进程数
6. `supervisord -n`
7. Supervisor 才启动 Django API、Celery Worker、Celery Beat、`nats_listener`
   和 SNMP Bridge 等运行期进程

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
