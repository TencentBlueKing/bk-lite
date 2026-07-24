# BK-Lite Agent Guide

`AGENTS.md` 软链接到本文件。本文件只记录仓库特有且会影响实现的约束。

## 事实入口

| 内容 | 位置 |
|---|---|
| 领域术语与产品取舍 | `CONTEXT.md`、`PRODUCT.md` |
| 长期业务与工程事实 | `specs/capabilities/` |
| 当前跨会话变更 | `specs/changes/<feature>/spec.md` |
| UI 与组件约定 | `DESIGN.md`、`web/DESIGN.md`、`web/COMPONENT_GOVERNANCE.md` |
| 开发、验证与运行命令 | `DEVELOP.md` |
| 长期架构决定 | `docs/adr/` |
| 发布记录 | `docs/changelog/` |

按任务读取相关入口，并以当前代码、配置和测试为最终证据。

## 服务启动与初始化边界

修改启动脚本、初始化命令、服务依赖或部署配置前，必须先核对
`server/support-files/release/startup.sh`、
`server/apps/core/management/commands/batch_init.py` 和
`server/support-files/release/supervisor/`。

### 阶段定义与启动不变量

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

Server 生产容器的启动顺序是：

1. `migrate`（当前失败会被 `|| true` 忽略）
2. `createcachetable`
3. `collectstatic`
4. `batch_init`（启动硬门禁，失败会使 `startup.sh` 退出）
5. 条件清理配置并设置进程数
6. `supervisord -n`
7. Supervisor 才启动 Django API、Celery Worker、Celery Beat、`nats_listener`
   和 SNMP Bridge 等运行期进程

### 启动期允许与禁止事项

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

### 已知故障链

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

### Agent 修改检查清单

新增或调整初始化操作前，必须逐项确认：

1. 标明调用方和被调用方分别属于启动期、运行期还是独立基础设施。
2. 查明被调用方由谁、在何时启动；若由当前容器 Supervisor 启动，则启动期
   禁止依赖。
3. 区分“Broker/端口可达”和“消费者/responder 已就绪”，不得混为一谈。
4. 明确失败是否应阻断启动；非关键操作必须移到运行期并具备幂等、重试和补偿。
5. 覆盖依赖缺失、响应超时、重复执行和容器重启场景的测试。
6. 启动顺序或依赖关系发生变化时，同步更新下列图表和本节文字。

以下图表用于辅助理解，文字约束仍是 Agent 实现时必须遵守的判断依据：

- [项目服务与依赖拓扑](docs/project-service-dependency.png)
- [Server 启动顺序、初始化边界与禁止依赖](docs/server-startup-dependency.png)
- [两页可编辑 Draw.io 源文件](docs/project-service-dependency.drawio)

## 仓库约束

- 只改任务范围，保留无关工作区状态，不做全仓格式化。
- 中文交流和提交；代码标识符遵循现有项目风格。
- 凭据只由环境注入，不提交或记录 `.env`、keystore、token。
- 数据库访问使用 Django ORM，禁止 raw SQL、`.raw()`、`RawSQL`、`cursor.execute`。
- 非关键、可重建的外部资源失败不得阻断服务启动。
- 向目标主机下发或执行操作必须有资源边界、幂等/回滚和相应测试。
- Web 改动优先复用 Ant Design、现有组件和 Storybook；共享抽象必须已有多个真实使用方。

## 交付

修改前核对相关事实，修改后运行与影响范围匹配的新鲜验证。无法运行或遇到基线失败时，保留原始证据并明确说明。
