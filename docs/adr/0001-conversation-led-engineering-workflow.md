# ADR 0001：采用按风险分级的 Grill 工程工作流

Status: accepted

## Context

仓库曾同时维护 OpenSpec、OPSX、Superpowers、ProjectMem 和 CodeGraph。多套强制入口重复加载指令、制造额外工具回合，并让清晰的小改承担与风险不匹配的流程成本。

## Decision

- 清晰小改直接实现并聚焦验证。
- 模糊、跨域、破坏性或难回滚问题由用户显式进入 Grill。
- 长期能力事实存放在 `specs/capabilities/`。
- 跨会话变更使用一份 `specs/changes/<feature>/spec.md`，必要时再拆 tickets。
- 共享术语存放在 `CONTEXT.md`；只有难以回滚的真实取舍写 ADR。
- 不保留 OpenSpec 的 proposal/design/delta/tasks/sync/archive 仪式，也不保留旧工作流兼容入口。

## Consequences

日常上下文和 Token 开销下降；Agent 需要主动判断风险等级，并保证 capability、change 和代码之间不长期漂移。
