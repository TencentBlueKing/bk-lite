# AGENTS.md

> BK-Lite 工程 Agent 执行手册 —— **本仓库 Agent 协作的单一真相源**。任何 AI 编码 Agent 都读本文;Claude Code 经 `CLAUDE.md` 引用同一份内容,确保各工具开发过程一致。
> 基于仓库事实、面向可执行流程。本文是「入口 + 红线」,明细在下方导航的子文档里。

## 文档导航（先读这里）

| 我要… | 去 |
|-------|----|
| 完整命令 / 工作流 / Runbook | [docs/operations.md](docs/operations.md) |
| 后端编码规范 / 高频陷阱 | [docs/backend-coding-guide.md](docs/backend-coding-guide.md) |
| 系统结构 / 模块边界 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 「为什么这样设计」 / 工程信条 | [docs/design-docs/core-beliefs.md](docs/design-docs/core-beliefs.md) |
| 历史设计决策 / 学习项 | [docs/design-docs/learnings.md](docs/design-docs/learnings.md) |
| 设计 / 视觉 / 前端 | [DESIGN.md](DESIGN.md) · [FRONTEND.md](FRONTEND.md) · [web/DESIGN.md](web/DESIGN.md) |
| 安全红线 | [SECURITY.md](SECURITY.md) |
| 可靠性 / 回滚 | [RELIABILITY.md](RELIABILITY.md) |
| 「什么算合格」 | [QUALITY_SCORE.md](QUALITY_SCORE.md) |
| 产品取舍 | [PRODUCT_SENSE.md](PRODUCT_SENSE.md) |
| 计划 / 规格 | [PLANS.md](PLANS.md) · [openspec/](openspec/) |
| DB schema(生成式) | [docs/generated/db-schema.md](docs/generated/db-schema.md) |
| 外部参考资料 | [docs/references/README.md](docs/references/README.md) |

## 概览

### 技术栈（证据化）
- 后端 `server/`：Python 3.12 + Django 4.2 + Uvicorn + Celery（`server/pyproject.toml`、`server/Makefile`）
- Web `web/`：Next.js 16 + React 19 + TS + Ant Design（`web/package.json`）
- Mobile `mobile/`：Next.js 15 + Tauri 2 + TS（`mobile/package.json`）
- WebChat `webchat/`：npm monorepo(core/ui/demo)
- Stargazer `agents/stargazer/`：Python 3.12 + Sanic
- Algorithms `algorithms/`：Python 多算法服务(BentoML，`uv` 管理)

> 结构与模块边界详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

### 仓库目录（默认优先级）
`server/`(主后端) · `web/`(主控制台) · `mobile/` · `webchat/` · `agents/stargazer/`(采集代理) · `algorithms/`(算法集) · `deploy/`(K8s 模板)

### 默认工作目录与选择规则
- 默认在仓库根执行只读命令；进目标模块目录再执行开发命令,避免跨模块污染。
- 只改与任务相关文件,禁止顺手改动和全仓格式化。

## 快速开始（精简；完整命令见 [docs/operations.md](docs/operations.md)）

| 模块 | dev | test |
|------|-----|------|
| Server | `cd server && make install && make migrate && make dev`（:8011） | `make test` |
| Web | `cd web && pnpm install && pnpm dev`（:3000） | `pnpm lint && pnpm type-check` |
| Mobile | `cd mobile && pnpm dev`（:3001）/ `pnpm dev:tauri` | `pnpm lint && pnpm type-check` |
| WebChat | `cd webchat && npm install && npm run dev` | `npm run test` |
| Stargazer | `cd agents/stargazer && make install && make run`（:8083） | `make lint` |
| Algorithms | `cd algorithms/<svc> && make install && make serving`（:3000） | `uv run pytest` |

## 环境与配置（要点）

- 版本:Python `3.12`;Node Web=`24`(`web/.nvmrc`),WebChat≥18。
- 依赖:`uv`(Python)/`pnpm`(web、mobile,`only-allow` 强制)/`npm`(webchat)。
- Secrets(强制):仅用 `*.example`/`*.template` 样例;`.env`/keystore 不入库;凭据经部署环境注入,不写代码和日志。
- 完整 env 变量与模板清单见 [docs/operations.md §4](docs/operations.md) 与 [SECURITY.md](SECURITY.md)。

## 质量门禁（按改动模块,提交前必跑）

| 改动落在 | 命令 |
|----------|------|
| `server/` | `cd server && make test` |
| `web/` `mobile/` | `pnpm lint && pnpm type-check` |
| `agents/stargazer/` | `make lint` |
| `webchat/` | `npm run build && npm run test` |
| `algorithms/<svc>` | `uv run pytest` |

自动门禁:`.husky/pre-commit`(web/mobile)、`server/.pre-commit-config.yaml`(black/isort/flake8/check_migrate/check_requirements)。
> 红线清单与评分见 [QUALITY_SCORE.md](QUALITY_SCORE.md)。

## Agent 执行规则（红线）

- **项目快捷工作流**:
  - `/fix` / `/修复`: 缺陷修复流程。先系统化调试确认根因,经确认后 TDD 复现与最小修复,最后真实验证并收口。
  - `/feature` / `/功能`: 功能开发流程。先澄清与设计,必要时走 OpenSpec,多步骤实现先写计划,实现阶段 TDD,最后跑对应模块门禁。
  - 工具入口按会话类型同步维护:`.agents/skills/source-command-*`、`.claude/commands/`、`.claude/skills/`、`.opencode/command/`、`.opencode/skills/`、`.github/prompts/`。
- **最小 diff**:仅改需求相关文件与代码块。
- **避免格式化污染**:只格式化触及文件,不全仓格式化。
- **变更后必验**:至少跑对应模块最小门禁。
- **先读再写**:先提证据再下结论,不凭经验补步骤。
- **不做向后兼容影子设计**:旧入口与现状冲突时直接更新到当前真实入口。
- **TODO 策略**:无法确认的写 `TODO:` 并附「确认位置(路径+关键词)」。
- **中文优先**:回答、注释、commit、PR、文档一律中文。
- **测试红线**:新功能/bugfix **先写测试**(TDD 红-绿-重构);改动代码**覆盖率 ≥75%**;测行为不测实现,**不写凑数/无效测试**。见 [QUALITY_SCORE](QUALITY_SCORE.md)、`server/docs/testing-guide.md`。
- **下发红线**:向目标主机下发插件/作业,**绝不能致其崩溃、死机或数据丢失**;高危/不可逆操作须 dry-run + 资源边界 + 幂等/可回滚,并有对应测试。见 [RELIABILITY](RELIABILITY.md)。
- **禁用原生 SQL**:统一走 Django ORM,**禁止** raw SQL / `.raw()` / `RawSQL` / `cursor.execute`(`DB_ENGINE` 多方言,原生 SQL 跨库易碎)。

> 完整信条与「为什么」见 [docs/design-docs/core-beliefs.md](docs/design-docs/core-beliefs.md)。

## TODO（待确认项）

由各团队按内部约定追踪;新发现的待确认项写明「确认位置(路径+关键词)」,不散落在本文。
