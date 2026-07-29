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
| Server 启动顺序与依赖边界 | `docs/operations/server-startup-dependencies.md` |
| 长期架构决定 | `docs/adr/` |
| 发布记录 | `docs/changelog/` |

按任务读取相关入口，并以当前代码、配置和测试为最终证据。

## Server 启动硬约束

修改启动脚本、初始化命令、服务依赖或部署配置前，必须阅读
`docs/operations/server-startup-dependencies.md`，并核对当前代码和配置。

- `batch_init` 完成前，所有由当前容器 Supervisor 管理的进程都视为不存在且
  未就绪；启动期不得依赖它们的 HTTP、RPC、消息响应或异步任务。
- Broker 或端口可连接不代表消费者、RPC responder 或 API 已就绪；相同
  Supervisor `priority` 也不代表存在就绪顺序。
- 非关键对账、同步和外部资源声明必须移到运行期，并提供幂等、重试和补偿；
  失败不得阻断服务启动。
- 禁止用 `sleep`、延长超时、无限重试或仅捕获异常来掩盖启动期与运行期之间的
  循环依赖。

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
