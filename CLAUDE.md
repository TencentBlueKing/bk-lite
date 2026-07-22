# BK-Lite Agent Guide

> 本文件是仓库级 Agent 协作的唯一入口；`AGENTS.md` 软链接到本文件。只保留跨模块、长期稳定且会影响执行的规则。

## 先读什么

| 任务 | 事实源 |
|---|---|
| 术语与共享语言 | `CONTEXT.md` |
| 产品定位与默认取舍 | `PRODUCT.md` |
| UI 总入口 | `DESIGN.md` |
| 系统与模块边界 | `docs/engineering/architecture.md` |
| 开发、部署与日常命令 | `docs/operations.md` |
| 后端工程规则 | `docs/backend-coding-guide.md` |
| 前端工程规则 | `docs/engineering/frontend.md` |
| 安全、可靠性、质量 | `docs/governance/{security,reliability,quality}.md` |
| 长期能力契约 | `specs/capabilities/<capability>.md` |
| 跨会话变更 | `specs/changes/<feature>/spec.md` |
| 难以回滚的决定 | `docs/adr/` |

只读当前任务需要的事实源。不要把整套文档当作固定开工清单。

## 执行路由

清晰小改直接走：

```text
核对当前事实 -> 实现 -> 聚焦验证 -> commit/push
```

- 根因不明、反复出现或性能退化：`$diagnosing-bugs`。
- 新功能或缺陷修复需要测试接缝：`$tdd`。
- 需求存在多条合理分支、跨域或难以回滚：用户显式调用 `$grill-with-docs`。
- 单会话实现：`$implement`；跨会话先 `$to-spec`，确有阻塞边再 `$to-tickets`。
- 完成前按变更范围运行新鲜验证；需要双轴复核时调用 `$code-review`。

完整工作流见 `docs/agents/workflow.md`，Skill 清单见 `docs/agents/skills.md`。

## 就近规则

- 改 `server/`：先读 `docs/backend-coding-guide.md`；涉及鉴权、下发、启动或回滚，再读对应 governance 文档。
- 改 `web/` 页面、组件、样式或 Storybook：先读 `docs/engineering/frontend.md`、`web/DESIGN.md` 与 `web/COMPONENT_GOVERNANCE.md`。
- Web 组件先搜索 Ant Design、`web/src/components`、目标 app 的 `components` 与 Storybook；能复用不新建。单 app 组件留在 app 内，至少两个 app 实际使用后才提升 shared。
- 改算法、Stargazer、Mobile 或 WebChat：以目标目录的 README、Makefile/package scripts 和测试为准，不把其他模块约定外推过去。

## 全局红线

- 只改任务相关文件，保留无关脏状态；不全仓格式化。
- 回答、注释、提交、PR 和文档优先使用中文。
- Secrets 只通过部署环境注入；`.env`、keystore、token 不入库、不进日志。
- 数据库统一使用 Django ORM，禁止 raw SQL、`.raw()`、`RawSQL`、`cursor.execute`。
- 非关键、可重建的外部资源初始化不得阻断服务启动。
- 向目标主机下发必须有 dry-run、资源边界、幂等性、回滚路径和测试。
- 不保留旧入口的兼容影子；无法确认时写 `TODO:` 并标明确认位置与关键词。

## 最小门禁

| 改动范围 | 命令 |
|---|---|
| `server/` | `cd server && make test` |
| `web/` | `cd web && pnpm lint && pnpm type-check` |
| `mobile/` | `cd mobile && pnpm lint && pnpm type-check` |
| `webchat/` | `cd webchat && npm run build && npm run test` |
| `agents/stargazer/` | `cd agents/stargazer && make lint` |
| `algorithms/<svc>/` | `cd algorithms/<svc> && uv run pytest` |

门禁不可运行或存在与本次改动无关的基线失败时，保留原始证据并明确说明，不把失败伪装成通过。

## 文档防腐

- 根目录只放稳定入口：`AGENTS.md`/`CLAUDE.md`、`CONTEXT.md`、`PRODUCT.md`、`DESIGN.md` 和 README。
- 专题工程规则放 `docs/engineering/`，强制性红线放 `docs/governance/`，一次性报告和变更总结放 `docs/archive/`。
- 同一规则只允许一个权威位置；其他文档只链接，不复制。
- 业务事实写 capability，临时实现取舍写 change spec，长期且难回滚的取舍写 ADR；具体符号和测试断言由代码承担。
- 移动、删除或替换权威文档时，同一提交修正所有引用。
