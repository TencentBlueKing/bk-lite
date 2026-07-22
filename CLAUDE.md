# BK-Lite Agent Guide

> 本文件是仓库级 Agent 协作的单一入口；`AGENTS.md` 软链接到本文件。

## 开工先读

- 共享术语：`CONTEXT.md`
- 系统边界：`ARCHITECTURE.md`
- 长期能力契约：`specs/capabilities/<capability>.md`
- 跨会话变更：`specs/changes/<feature>/spec.md`
- 难以回滚的决定：`docs/adr/`
- 开发与运行命令：`docs/operations.md`
- 后端规范：`docs/backend-coding-guide.md`
- Web UI：`DESIGN.md`、`FRONTEND.md`、`web/DESIGN.md`、`web/COMPONENT_GOVERNANCE.md`
- 安全、可靠性、质量：`SECURITY.md`、`RELIABILITY.md`、`QUALITY_SCORE.md`
- Agent 工作流：`docs/agents/workflow.md`

## 项目结构

- `server/`：Python 3.12、Django 4.2、Uvicorn、Celery。
- `web/`：Next.js 16、React 19、TypeScript、Ant Design。
- `mobile/`：Next.js 15、Tauri 2、TypeScript。
- `webchat/`：npm monorepo。
- `agents/stargazer/`：Python 3.12、Sanic。
- `algorithms/`：Python 算法服务，`uv` 管理。
- `deploy/`：Docker/Kubernetes 部署资产。

## 日常工作流

目标清晰的小改直接执行：

```text
核对当前事实 -> 实现 -> 聚焦验证 -> commit/push
```

不强制 Grill，也不创建 change spec。复杂或根因不明的缺陷显式使用 `$diagnosing-bugs`。

存在多条合理分支、跨产品/数据边界、破坏性迁移或难以回滚时，由用户显式进入：

```text
$grill-with-docs
  ├─ 单会话 -> $implement
  └─ 跨会话 -> $to-spec -> 必要时 $to-tickets
```

- Grill 一次只问一个真正需要用户裁定的问题；仓库可查事实由 Agent 自行核对。
- `$to-spec` 只整理已收敛结论，写入一份 `specs/changes/<feature>/spec.md`。
- `$to-tickets` 只在工作超出一个上下文窗口或存在真实阻塞边时使用。
- `$implement` 在合适接缝使用 `$tdd`，完成后 `$code-review`，再以新鲜验证证据收口。
- 没有 proposal/design/delta/tasks/sync/archive 仪式；完成的 change 原地更新状态。

完整路由见 `docs/agents/workflow.md`，Skills 清单见 `docs/agents/skills.md`。

## Web UI / 组件红线

修改 `web/` 页面、组件、样式或 Storybook 前：

1. 先读 `web/DESIGN.md` 与 `web/COMPONENT_GOVERNANCE.md`。
2. 搜索 Ant Design、`web/src/components`、目标 app 的 `components` 和 Storybook。
3. 已有组件能承载时复用；仅样式差异优先增加稳定 variant。
4. 单 app 专用组件放 `web/src/app/<app>/components`。
5. 只有两个及以上真实 app 接入后，才提升到 `web/src/components`；shared 变化同步 Storybook。
6. 交付时说明复用项；新建时说明现有组件为何不适用及其归属。

## 质量门禁

| 改动范围 | 提交前命令 |
|---|---|
| `server/` | `cd server && make test` |
| `web/` | `cd web && pnpm lint && pnpm type-check` |
| `mobile/` | `cd mobile && pnpm lint && pnpm type-check` |
| `webchat/` | `cd webchat && npm run build && npm run test` |
| `agents/stargazer/` | `cd agents/stargazer && make lint` |
| `algorithms/<svc>/` | `cd algorithms/<svc> && uv run pytest` |

只运行与改动相关的最小门禁；不得借机全仓格式化。

## 工程红线

- 仅修改需求相关文件，保留无关脏状态。
- 新功能和缺陷修复遵循 TDD；测试行为而非实现，改动代码覆盖率不低于 75%。
- Secrets 只通过部署环境注入；`.env`、keystore、token 不入库、不进日志。
- 数据库统一使用 Django ORM，禁止 raw SQL、`.raw()`、`RawSQL`、`cursor.execute`。
- 非关键、可重建的外部资源初始化不得阻断服务启动。
- 主机下发必须有 dry-run、资源边界、幂等性、回滚路径和对应测试。
- 不建立向后兼容影子入口；旧入口与当前事实冲突时直接迁到真实入口。
- 无法确认时写 `TODO:`，并标明确认位置和关键词。
- 回答、注释、提交、PR、文档优先使用中文。

## 规格与知识边界

- `CONTEXT.md` 只维护共享术语，不复制业务规则。
- `specs/capabilities/` 是长期业务、验收、架构和运行约束的事实源。
- `specs/changes/` 只保存跨会话的变更意图、实现决定、测试接缝和必要 tickets。
- `docs/adr/` 只记录难以回滚且存在真实取舍的决定。
- 具体表名、函数签名、组件树和测试断言由代码承担，不写入长期 capability。
