# Live User Locale Timezone Sync

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/live-user-locale-timezone-sync/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

用户在个人信息抽屉中修改语言和时区后，当前页面不会立即切换，通常要依赖重新登录或完整刷新才能看到变化。这会造成偏好设置已保存但运行态仍使用旧值，导致页面文案、Ant Design 组件语言、前端时间展示以及后端按用户时区返回的数据彼此不一致。

## What Changes

- 为用户语言与时区引入统一的运行时偏好同步机制，使保存后当前页面文案与时间立即切换。
- 扩展当前认证会话载荷，确保 locale 与 timezone 在保存后可被前端上下文和后续请求立即消费，而不需要重新登录。
- 统一前端语言和时间相关消费者的取值来源，覆盖 React 国际化文案、Ant Design locale、dayjs locale 以及依赖用户时区的时间格式化逻辑。
- 明确后端请求上下文中的用户时区生效路径，并补齐关键接口的时间序列化，使接口返回按最新用户时区输出。

## Capabilities

### New Capabilities
- `user-preference-runtime-sync`: 定义用户修改语言和时区后，当前前端运行态、认证会话和后端时间返回必须立即同步生效的行为。

### Modified Capabilities

## Impact

- Web 前端认证与运行时上下文：next-auth session、LocaleProvider、ThemeProvider、用户信息抽屉、时间格式化 hooks。
- Server 用户偏好读取与时间序列化：用户基础信息更新接口、基于 token 的用户信息装载、依赖用户时区的接口输出。
- 相关系统：用户偏好持久化、认证态同步、国际化文案加载、时间展示与时间字段接口返回。

## Implementation Decisions

## Context

当前用户语言和时区设置存在多处状态源：用户信息抽屉保存到后端用户资料；前端 React 国际化文案由 LocaleProvider 管理；Ant Design locale 与 dayjs locale 由 ThemeProvider 在初始化时从 localStorage 读取；部分时间格式化逻辑依赖 next-auth session；后端请求上下文中的 locale/timezone 则由 token 验证结果决定。由于这些状态源缺少统一同步路径，保存用户偏好后，当前页面与后续请求会在一段时间内继续使用旧值。

本次变更横跨 web 前端运行时上下文、next-auth 会话载荷、server 用户偏好读取与时间序列化，属于跨模块的一致性修复，需要先明确状态边界和同步顺序。

## Goals / Non-Goals

**Goals:**
- 在用户保存 locale 和 timezone 后，当前页面文案、Ant Design 组件语言和前端时间显示立即切换。
- 让 next-auth session 持有最新 locale 和 timezone，并作为前端认证态的统一同步入口。
- 让后续 API 请求在无需重新登录的前提下使用最新用户时区。
- 为关键时间字段接口建立按用户时区输出的明确序列化策略。

**Non-Goals:**
- 不重构整站所有国际化实现，只修复用户偏好即时生效所经过的核心链路。
- 不变更用户偏好存储模型或引入新的外部依赖。
- 不承诺一次性清理仓库中所有历史时间处理代码，仅覆盖本次链路涉及和关键可见接口。

## Decisions

### 1. 以“保存成功后的显式同步”替代“等待重新登录”

保存用户基础信息成功后，前端 SHALL 立即执行一次偏好同步流程，而不是仅刷新右上角用户信息。该流程需要同时更新运行时 locale/timezone、刷新或重建 next-auth session 载荷，并触发依赖语言与时区的上下文重新渲染。

选择原因：当前问题的根因不是持久化失败，而是保存后的运行态没有被更新。继续依赖重新登录只是在用一次完整重建掩盖状态源分裂。

备选方案：
- 仅更新 localStorage。否决，因 ThemeProvider、session 消费方和后端请求不会自动感知变化。
- 保存后直接整页刷新。否决，虽然简单，但不满足“当前页面立即切换且不需要重新登录”的目标。

### 2. 将 locale 与 timezone 一并纳入前端认证会话载荷

next-auth token/session SHALL 同时包含 locale 和 timezone，并提供保存后更新当前会话的能力。前端所有依赖登录用户偏好的上下文，应优先从统一的会话同步结果或其派生状态读取，而不是分别从 localStorage、旧 session 字段或临时组件状态读取。

选择原因：现有代码已经把 locale 部分接入 next-auth，但 timezone 未接入，且保存后没有刷新 session，导致前端多个消费者读到不同来源。把 locale 与 timezone 同时纳入会话载荷，可以让当前页面和后续请求共享同一份用户偏好快照。

备选方案：
- 完全引入独立的用户偏好全局 store。暂不采用，这会扩大改动面，并引入与 next-auth 会话并行的另一套事实源。

### 3. 前端上下文按职责拆分，但必须订阅同一份偏好变化

LocaleProvider 继续负责 React 国际化文案，ThemeProvider 继续负责 Ant Design locale 与 dayjs locale，但两者都必须响应保存后同步得到的最新 locale。时间格式化 hooks 则必须改为读取最新 timezone，而不是依赖缺失的旧字段名或未刷新的 session 数据。

选择原因：当前上下文边界已经存在，完全合并成本高；但它们可以共享同一份偏好变化事件或状态，避免再次各自读取不同初始化来源。

备选方案：
- 合并 LocaleProvider 与 ThemeProvider。暂不采用，这不是本次修复的必要条件。

### 4. 后端以“每请求用户时区激活 + 关键序列化显式转换”为准则

后端认证链路 SHALL 在每个请求中基于最新用户资料激活 locale/timezone；依赖 DRF DateTimeField 的接口可沿用当前激活时区；对手写时间序列化或直接 `isoformat()` 的关键返回路径，需要补充显式按用户时区转换，避免同一页面中不同接口返回不一致。

选择原因：当前 token 验证结果已经包含 timezone，且用户资料变更会清理 token_info 缓存，因此“后续请求使用新时区”具备基础条件。但如果序列化层没有统一转换策略，接口仍可能返回旧的 UTC 或服务端默认时区结果。

备选方案：
- 全仓统一替换所有时间序列化逻辑。暂不采用，范围过大，先覆盖用户当前可见链路与关键系统管理接口。

## Risks / Trade-offs

- [前端仍保留多层上下文] → 通过统一的保存后同步入口和明确的取值优先级减少分叉，而不是一次性重构全部上下文。
- [session 更新机制受 next-auth 版本能力限制] → 优先复用现有 next-auth 流程；若客户端 session update 能力不足，则通过重新获取会话或重建认证态实现同等效果。
- [后端存在两套 User 模型入口] → 变更时需要确认用户偏好最终以 token 验证链路返回的数据为准，避免只更新控制台模型而遗漏认证侧读取。
- [部分接口仍手写时间格式化] → 在实现阶段识别关键接口并补测试，剩余历史路径列入后续清理范围。

## Migration Plan

1. 先为 OpenSpec 中定义的前端即时同步与后端时区返回要求补实现与测试。
2. 部署时无需数据迁移，仅需发布 web 与 server 代码。
3. 若出现偏好同步异常，可回滚至旧版本；用户资料表中的 locale/timezone 字段保持兼容，不需要数据回退。

## Open Questions

- 是否需要把更多非系统管理模块的手写时间序列化一并纳入本次范围，还是仅覆盖用户信息抽屉触达的关键页面与接口。
- 当前 next-auth 客户端更新会话的最佳接入方式是否可以直接复用现有流程，还是需要补充定制接口以返回最新用户偏好。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-14
```

## Capability Deltas

### user-preference-runtime-sync

## ADDED Requirements

### Requirement: 保存用户偏好后当前页面必须立即切换语言与时间
当已认证用户在个人信息设置中保存新的 locale 和 timezone 后，系统 MUST 在当前页面立即应用新的语言和时区，而不要求用户重新登录。

#### Scenario: 当前页面文案立即切换
- **WHEN** 用户保存新的 locale 且保存请求成功
- **THEN** 当前页面的 React 国际化文案和 Ant Design 组件语言 MUST 切换为新的 locale

#### Scenario: 当前页面时间立即切换
- **WHEN** 用户保存新的 timezone 且当前页面存在依赖用户时区显示的时间内容
- **THEN** 当前页面已渲染的相关时间内容 MUST 按新的 timezone 重新计算并显示

### Requirement: 认证会话必须同步最新的 locale 和 timezone
系统 MUST 在用户偏好保存成功后，使当前认证会话携带最新的 locale 和 timezone，以便当前页面与后续前端逻辑读取一致的偏好值。

#### Scenario: 保存后会话偏好更新
- **WHEN** 用户保存新的 locale 和 timezone 且请求返回成功
- **THEN** 当前认证会话中的 locale 和 timezone MUST 更新为保存后的值

#### Scenario: 页面内后续消费者读取新偏好
- **WHEN** 保存成功后的页面内上下文、hooks 或组件再次读取用户偏好
- **THEN** 它们 MUST 读取到与最新保存结果一致的 locale 和 timezone

### Requirement: 后续请求必须按最新用户时区返回时间字段
用户保存新的 timezone 后，系统 MUST 使后续请求在无需重新登录的前提下，以最新用户时区返回时间相关字段。

#### Scenario: 后续接口返回新时区时间
- **WHEN** 用户保存新的 timezone 后发起新的受认证请求
- **THEN** 返回的关键时间字段 MUST 按最新用户 timezone 序列化

#### Scenario: 认证链路使用最新时区
- **WHEN** 服务端处理保存成功后的后续受认证请求
- **THEN** 请求上下文中的用户 timezone MUST 与最新保存的 timezone 一致

## Work Checklist

## 1. 会话与偏好同步

- [x] 1.1 梳理 web 中 locale 和 timezone 的当前取值来源，确定保存成功后的统一同步入口。
- [x] 1.2 扩展 next-auth token/session 载荷以包含 timezone，并补齐 locale/timezone 的保存后刷新机制。
- [x] 1.3 调整用户信息抽屉保存流程，使保存成功后立即同步当前运行态偏好，而不是仅刷新右上角用户信息。

## 2. 前端即时生效链路

- [x] 2.1 改造 LocaleProvider 和 ThemeProvider，使 React 文案、Ant Design locale 与 dayjs locale 响应保存后的最新 locale。
- [x] 2.2 改造依赖用户时区的时间格式化逻辑，使其读取最新 timezone 并在当前页面重新计算显示时间。
- [x] 2.3 检查并修正依赖 localStorage 或旧 session 字段的语言/时区消费者，避免再次出现多状态源分叉。

## 3. 后端最新时区返回

- [x] 3.1 确认用户偏好更新接口与认证链路使用的用户资料来源一致，并补齐 locale/timezone 更新后的关键缓存失效行为。
- [x] 3.2 检查关键受认证接口的时间字段序列化路径，补齐按请求用户 timezone 输出的转换逻辑。
- [x] 3.3 为系统管理等当前用户可见链路增加时区返回验证，确保保存后后续请求无需重新登录即可返回最新时区时间。

## 4. 验证与回归

- [x] 4.1 为 web 补充或更新与用户偏好即时生效相关的类型与行为验证，并执行 `cd web && pnpm type-check`。
- [x] 4.2 为 server 补充或更新与用户时区返回相关的测试或最小验证用例，并执行对应最小测试命令。
- [ ] 4.3 进行一次端到端手动验证：修改语言与时区后，当前页面文案立即切换，时间立即更新，后续接口返回按最新时区输出。
