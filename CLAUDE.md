# BK-Lite Agent Guide

`AGENTS.md` 软链接到本文件。本文件只记录仓库特有且会影响实现的约束。

## 事实入口

| 内容 | 位置 |
|---|---|
| 领域术语与产品取舍 | `CONTEXT.md`、`PRODUCT.md` |
| 长期业务与工程事实 | `specs/capabilities/` |
| 后端编码与高风险规则 | `specs/capabilities/backend-engineering.md` |
| 安全、可靠性与质量红线 | `specs/capabilities/{platform-security,platform-reliability,engineering-quality}.md` |
| 对外 API 暴露与网关规范 | `specs/capabilities/openapi-gateway.md` |
| 当前跨会话变更 | `specs/changes/<feature>/spec.md` |
| UI 与组件约定 | `DESIGN.md`、`web/DESIGN.md`、`web/COMPONENT_GOVERNANCE.md` |
| 开发、验证与运行命令 | `DEVELOP.md` |
| Server 启动顺序与依赖边界 | `docs/operations/server-startup-dependencies.md` |
| 长期架构决定 | `docs/adr/` |
| 发布记录 | `docs/changelog/` |

按任务读取相关入口，并以当前代码、配置和测试为最终证据。修改 `server/` 或
`agents/` 前，按影响范围阅读后端工程、安全、可靠性和质量 capability；只读取
本次任务相关章节。

## Web UI 硬约束

修改 `web/src/**`、`web/src/stories/**` 的页面、组件或样式时遵守本段短清单；
**不要默认通读** `web/DESIGN.md` 全文。

- **布局**：优先 Tailwind `className`；禁止新增大段行内布局，也勿为普通布局新建 SCSS Module。
  行内 `style` 仅限动态值 / AntD 契约 / 画布瞬时尺寸。
- **统一尺寸常量勿拆**：若多处表单控件共用 `FORM_CONTROL_WIDTH`（或同类常量）以
  `style={{ width: CONST }}` 对齐，**保留该常量**；禁止为了「改成 Tailwind」拆成
  多处散落的 `w-[300px]` 等任意值，否则失去单点改宽能力。
- **颜色**：语义 token（`var(--color-*)` / `globals.css`）；禁止硬编码主题色。
- **组件**：Ant Design → `src/components` → app-local；升 shared 须 ≥2 真实 app，
  并遵守 `web/COMPONENT_GOVERNANCE.md`。
- **按需深读**（只读相关章节）：新建视觉组件、改 token/设计语义、组件治理大迁移、
  设计走查，或短规则不够用时 → `web/DESIGN.md` 的 Layout & Styling + Do/Don't；
  归属争议 → `COMPONENT_GOVERNANCE.md`；改色值 → `globals.css`。
- 纯文案 / 接 API / 改 props 且不动布局与主题时，不必深读 DESIGN。

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
- `server/apps/<app>/` 引入日志统一用 `from apps.core.logger import {app_name}_logger as logger`（见 `server/apps/core/logger.py`），禁止 `loguru` 或就地 `logging.getLogger`。
- 非关键、可重建的外部资源失败不得阻断服务启动。
- 新增对外 API 一律经 OpenAPI 网关暴露（内部函数用 `@openapi_expose`，外部服务写 KV 注册表），不得新增散落的 `open_api` 端点或对外端口；暴露端点必须附双租户测试并登记。见 `specs/capabilities/openapi-gateway.md`。
- 向目标主机下发或执行操作必须有资源边界、幂等/回滚和相应测试。
- Web 改动优先复用 Ant Design、现有组件和 Storybook；共享抽象必须已有多个真实使用方。
  视觉与布局细则见上文「Web UI 硬约束」，勿每次通读 `web/DESIGN.md`。

## Cursor Cloud specific instructions

云上默认没有本机 Postgres/Redis/NATS。开发依赖由 `.cursor/environment.json` 的 `install` 安装（`server`/`stargazer` 的 `uv sync --all-groups --all-extras`，`web` 的 `pnpm install`，`webchat` 的 `npm ci`）。验证时用 sqlite，不要为跑单测去起整套中间件。

- Server：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest <paths> --no-cov`
- Web：`cd web && pnpm lint` / 相关 `pnpm test:*`；改了类型或布局再跑 `pnpm type-check`
- 缺 `server/.env` 时按上面的 sqlite 变量补一份即可；不要写入真实密钥

## 交付

修改前核对相关事实，修改后运行与影响范围匹配的新鲜验证。无法运行或遇到基线失败时，保留原始证据并明确说明。
