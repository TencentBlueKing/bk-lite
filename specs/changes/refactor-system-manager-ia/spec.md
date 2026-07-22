# Refactor System Manager Ia

Status: done

## Migration Context

- Legacy source: `openspec/changes/refactor-system-manager-ia/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

系统管理当前的信息架构将“用户与认证”“审计与错误日志”“平台设置”混放在 `security_management` 与 `Setting` 两个入口下，已经与新的产品导航目标不一致。现在需要重构系统管理的菜单与路由归属，让用户管理、平台设置和审计入口按新的结构稳定落地，同时同步社区版与企业版菜单装配行为。

## What Changes

- 重构系统管理一级菜单，移除 `security_management`，将系统管理收敛为“用户管理 / 应用管理 / 通知渠道 / 平台设置”四个入口。
- 将“认证源”“安全策略”迁入“用户管理”，并将企业版“敏感信息”从原安全管理入口迁入“用户管理”。
- 保持“门户设置”“许可”继续位于“平台设置”下，并保留 `/system-manager/settings/portal`、`/system-manager/settings/license` 两个稳定企业版入口。
- 将“错误日志”迁入“平台设置”。
- 新增统一的“审计日志”页面，使用单一设置路由承载“操作日志 / 登录日志”两个内容页签，页签顺序为“操作日志在前、登录日志在后”，默认落到操作日志页签。
- 同步调整社区版菜单定义、企业版菜单 patch 与企业版 route manifest，使菜单结构、页面路由与企业入口位置一致；`/system-manager/settings` 本身仍按首个可见子菜单重定向，而不是额外定义 portal-first 默认落点。
- **BREAKING**：废弃原 `security/*` 下被迁移页面的旧访问路径，不提供兼容跳转。

## Capabilities

### New Capabilities
- `system-manager-navigation`: 定义系统管理的新信息架构，包括菜单层级、页面归属、社区版菜单定义与企业版菜单 patch 的统一装配规则。
- `audit-log-page`: 定义统一审计日志页的路由、页签顺序、默认选中策略以及统一页面级权限行为。

### Modified Capabilities
- `license-management`: 明确许可入口在系统管理信息架构重构后仍必须保留在 `/system-manager/settings/license`，并继续作为平台设置下的稳定企业版入口。

## Impact

- Affected code: `web/src/app/system-manager/constants/menu.json`、系统管理相关 page 路由与组件、`web/src/app/system-manager/locales/*`、企业版 `web/manifests/routes.json` 与 `web/manifests/menus.json`。
- Affected systems: 社区版 Web 菜单装配、企业版菜单注入、系统管理页面导航与审计日志入口。
- Affected permissions: 统一审计日志页改为使用单一 `audit_log-View` 页面权限，废弃 `user_logs-View`、`operation_logs-View` 与未落地的 `user_logs-Delete`。
- Affected risk surface: 旧 `security/*` URL 不再兼容，现有书签、文档链接和依赖旧地址的前端入口会失效。

## Implementation Decisions

## Context

当前系统管理前端的导航结构由社区版 `web/src/app/system-manager/constants/menu.json` 提供基础菜单，再由企业版 `web/manifests/menus.json` 通过 patch 注入“门户”“许可”“敏感信息”等增量入口。页面路由则由 Next App Router 的文件路径决定，企业版页面通过 `web/manifests/routes.json` 在构建期映射到社区路由树。

现状中的 `security_management` 同时承载认证源、安全策略、登录日志、操作日志、错误日志以及企业版敏感信息，而 `Setting` 同时承载 API 密钥与企业版门户、许可入口。这已经与新的产品信息架构不一致：需求要求直接移除 `security_management` 一级菜单，并把其子页面按“用户管理 / 平台设置”重新分发。

本次变更不是单纯调整菜单文案，而是同时涉及：社区版菜单定义、企业版菜单 patch、企业版 route manifest、社区版路由文件位置，以及统一审计日志页对应的权限模型收敛方式。由于旧 `security/*` 路径不再兼容，本次设计需要明确 breaking 影响与实施边界。

## Goals / Non-Goals

**Goals:**
- 在系统管理中移除 `security_management` 一级菜单，并重建“用户管理 / 应用管理 / 通知渠道 / 平台设置”四个一级入口。
- 将认证源、安全策略迁移到 `user/*` 路由；将企业版敏感信息迁移到 `user/sensitive-info`。
- 保持企业版门户与许可入口继续挂在 `settings/*` 下，避免破坏现有 enterprise overlay 入口语义。
- 将错误日志迁移到 `settings/error-logs`。
- 新增 `settings/audit-log` 页面，使用单页 Tabs 承载“操作日志 / 登录日志”，并保证操作日志页签优先、默认优先选中操作日志。
- 将统一审计日志页收敛为单一 `audit_log-View` 页面权限，前后端不再保留 `operation_logs` / `user_logs` 作为独立权限节点。

**Non-Goals:**
- 不修改后端日志 API 路由。
- 不改变企业版门户与许可的业务实现方式，不重新设计 enterprise overlay 机制。
- 不提供旧 `security/*` 路径的兼容跳转。
- 不在本次变更中处理已存量 `CustomMenuGroup.menus` 数据的自动迁移。

## Decisions

### 1. 菜单重构与路由重构同步进行

系统管理这次调整不只改变菜单分组，还同步改变目标页面 URL，使新的信息架构在导航与路径语义上保持一致。

新的目标映射：
- `security/auth-sources` → `user/auth-sources`
- `security/settings` → `user/security-settings`
- `security/sensitive-info` → `user/sensitive-info`
- `security/error-logs` → `settings/error-logs`
- `security/login-logs` + `security/operation-logs` → `settings/audit-log`

这样可以避免“菜单在用户管理，但 URL 仍然挂在 security 下”的长期语义错位。代价是旧书签和旧文档链接会失效，但这与本次不做兼容跳转的产品决策一致。

备选方案：
- 只改菜单层级，不改 URL：实现更小，但会留下长期路径语义债务。
- 保留旧 URL 并增加兼容跳转：风险更低，但不符合本次明确要求。

### 2. 企业版增量继续沿用 patch + route manifest 装配

企业版的接入方式不变，只更新注入位置与目标路径：
- `menus.json` 中“门户”“许可”继续 patch 到 `Setting`
- “敏感信息”从原安全管理分组改为 patch 用户管理稳定 key（`structure` / `organization`）
- `routes.json` 中敏感信息路由从 `/system-manager/security/sensitive-info` 改为 `/system-manager/user/sensitive-info`

这样可以最大限度复用现有 `prepare-enterprise.mjs` 与菜单合并机制，不引入新的 overlay 协议。

备选方案：
- 把敏感信息改回社区菜单内直写：会破坏企业增量边界。
- 为企业菜单引入新的分层协议：收益不足，复杂度过高。

### 3. 审计日志页采用“组合式单页 Tabs”，不做数据模型合并

新的 `settings/audit-log` 页面只负责页签状态、默认页签选择和权限控制，不把登录日志与操作日志重写成一套统一表结构。页面内部通过两个独立内容区承载：
- 操作日志内容组件（优先展示）
- 登录日志内容组件

原因：
- 当前登录日志已经是独立组件，且带有导出能力；
- 操作日志目前是 page 级实现，但其筛选条件、列定义与登录日志显著不同；
- 两类日志虽然都属于 audit trail，但并不共享同一数据结构。

因此应采用“page shell + tab content composition”，而不是“合并为单一日志模型”。

备选方案：
- 把两类日志并成一张统一表：会引入复杂的列、筛选和数据适配问题。
- 继续保留两个菜单页：不符合新的 IA 目标。

### 4. 统一审计日志页改为单一页面权限，不再按 Tab 拆分授权

后端权限编码统一收敛为：
- 审计日志页面：`audit_log-View`

新的审计日志页不再依据历史上的分离日志查看权限裁剪页签，而是将“操作日志”“登录日志”都视为统一页面下的固定内容：
- 用户具备 `audit_log-View`：可访问 `/system-manager/settings/audit-log`，并看到两个页签
- 用户不具备 `audit_log-View`：菜单与路由层不暴露该页面，接口访问由后端返回 403

这可以让权限模型与页面结构一致，避免依赖隐藏子菜单和局部权限判断来决定页签显隐。

备选方案：
- 继续保留分离日志查看权限：会让单页 Tabs 继续依赖隐藏权限节点，模型不干净。
- 为单页保留页签级无权限降级：与本次统一页面权限目标冲突。

### 5. 顶层目录页继续依赖首子菜单重定向，但目标子项需更新

`useRedirectFirstChild` 会在访问父级路径时跳到第一个子菜单 URL，因此本次重构后：
- `user/page.tsx` 会按照新的用户管理子菜单顺序重定向
- `settings/page.tsx` 会按照权限过滤后的平台设置首个可见子菜单顺序重定向
- `security/page.tsx` 将不再作为有效导航分组保留

这意味着新菜单排序本身就是导航行为的一部分。`/system-manager/settings` 的默认落点取决于权限过滤后的首个可见子菜单；企业版“门户”“许可”继续作为挂在平台设置下的稳定入口存在。

## Risks / Trade-offs

- **[Risk] 旧 `security/*` 直达链接失效** → 明确作为 breaking change 写入 proposal / specs，并在交付说明中提示。
- **[Risk] 企业版敏感信息 patch 目标失配导致菜单注入失败** → 同步更新企业 `menus.json` 的 target 与 `routes.json` 的 URL，并通过菜单加载结果验证 patch 命中。
- **[Risk] 旧角色仍只持有历史日志查看权限** → 本次不做自动迁移，需在资源同步后由产品界面手动调整角色权限到 `audit_log-View`。
- **[Risk] 操作日志当前实现位于 page 文件内，直接搬运会导致 page 与 component 职责混乱** → 先抽出可复用内容组件，再由新的 audit-log 页面组合。
- **[Trade-off] 不做兼容跳转可减少临时兼容层，但会放大 breaking 影响** → 接受该代价，以换取新的 IA 和 URL 语义一次到位。
- **[Trade-off] 不处理 `CustomMenuGroup` 存量数据迁移可减少范围，但可能导致用户已保存的自定义菜单与新默认结构脱节** → 本次只保证默认菜单与新代码路径正确，存量配置另行评估。

## Migration Plan

1. 先更新社区版系统管理菜单定义与本地化文案，确定新的一级菜单与目标 URL。
2. 迁移社区版相关 page 路径，并新增统一审计日志页；将旧 security 下的被迁移页面实现移动到新位置或重组为可复用组件。
3. 更新企业版 `routes.json` 与 `menus.json`，仅调整敏感信息的注入位置、路由路径与 route source，保持门户/许可不变。
4. 同步调整服务端 `system-manager.json` 菜单定义与日志接口鉴权，使系统管理权限树与统一 `audit_log-View` 保持一致。
5. 运行菜单加载、类型检查与目标路径访问验证，确保新菜单、企业 patch 和审计日志页面访问行为一致。
6. 若上线后需要回滚，以代码回滚恢复旧菜单定义、旧路由文件和旧企业 manifest；由于不做兼容跳转，回滚必须整体回滚而不能只回滚部分文件。

## Open Questions

- 服务端 `server/support-files/system_mgmt/menus/system-manager.json` 是否需要严格同步新的前端分组名称，还是只保持权限项存在即可？
- 对已存在的自定义菜单组数据，是否需要在后续单独补一轮迁移或重置策略？

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-26
```

## Capability Deltas

### audit-log-page

## ADDED Requirements

### Requirement: 系统必须提供统一的审计日志页面入口

系统 MUST 将原登录日志和操作日志页面整合为单一的“审计日志”页面入口，并挂载在平台设置下。

#### Scenario: 菜单进入统一审计日志页
- **WHEN** 用户点击“审计日志”菜单
- **THEN** 系统 MUST 进入 `/system-manager/settings/audit-log`

#### Scenario: 旧日志路径不再作为受支持入口
- **WHEN** 用户访问旧路径 `/system-manager/security/login-logs` 或 `/system-manager/security/operation-logs`
- **THEN** 系统 MUST 不再将其作为受支持的页面入口
- **AND** 系统 MUST 不提供兼容跳转

### Requirement: 审计日志页必须以页签方式承载操作日志与登录日志

系统 MUST 在统一审计日志页中使用页签切换操作日志与登录日志内容，而不是将两类日志合并为单一表格模型。

#### Scenario: 审计日志页展示两个页签
- **WHEN** 用户进入 `/system-manager/settings/audit-log`
- **THEN** 页面 MUST 展示“操作日志”和“登录日志”两个页签

#### Scenario: 页签顺序固定为操作日志在前
- **WHEN** 页面渲染审计日志页签
- **THEN** “操作日志”页签 MUST 位于“登录日志”页签之前

### Requirement: 审计日志页必须默认优先进入操作日志页签

系统 MUST 在统一审计日志页初始化时默认选中“操作日志”页签。

#### Scenario: 进入页面时默认进入操作日志
- **WHEN** 用户访问 `/system-manager/settings/audit-log`
- **THEN** 系统 MUST 默认选中“操作日志”页签

### Requirement: 审计日志页必须使用统一页面级权限

系统 MUST 使用单一 `audit_log-View` 权限控制统一审计日志页访问，而不是继续为操作日志与登录日志保留独立查看权限。

#### Scenario: 具备统一页面权限时展示完整审计日志页
- **WHEN** 用户具备 `audit_log-View`
- **THEN** 系统 MUST 允许访问 `/system-manager/settings/audit-log`
- **AND** 页面 MUST 展示“操作日志”和“登录日志”两个页签

#### Scenario: 不具备统一页面权限时不暴露审计日志页
- **WHEN** 用户不具备 `audit_log-View`
- **THEN** 系统 MUST 不向该用户暴露可访问的审计日志页面入口

### Requirement: 审计日志页必须复用现有日志能力边界

系统 MUST 保持登录日志与操作日志的现有接口边界和交互差异，而不是强行统一为单一数据模型。

### Requirement: 审计日志页必须容忍已知的运行时菜单分组残留

系统 MUST 在 `get_user_menus` 运行时响应仍可能出现旧的 `Security Management` 分组残留时，继续保证统一审计日志页的访问与鉴权行为不受影响。该残留源于后端资源同步当前不会更新既有 `Menu.menu_type`，属于已知限制，不在本次变更中处理。

#### Scenario: 后端返回旧分组残留但审计日志页行为保持正常
- **WHEN** `get_user_menus` 返回结果中仍包含旧的 `Security Management` 分组
- **THEN** 系统 MUST 继续保证 `/system-manager/settings/audit-log` 的页面进入与接口鉴权行为按当前变更定义工作
- **AND** 系统 MUST 不将该运行时分组残留视为阻塞当前变更验收的缺陷

#### Scenario: 登录日志维持既有导出能力
- **WHEN** 用户在统一审计日志页切换到“登录日志”页签
- **THEN** 系统 MUST 继续提供登录日志既有的导出能力

#### Scenario: 操作日志维持既有筛选维度
- **WHEN** 用户在统一审计日志页切换到“操作日志”页签
- **THEN** 系统 MUST 继续提供操作模块、操作类型和时间范围等既有筛选能力

### system-manager-navigation

## ADDED Requirements

### Requirement: 系统管理必须重构为新的一级菜单信息架构

系统 MUST 在系统管理中移除 `security_management` 一级菜单，并将顶层导航重构为“用户管理 / 应用管理 / 通知渠道 / 平台设置”四个入口。

#### Scenario: 一级菜单显示名称重命名
- **WHEN** 用户进入系统管理导航
- **THEN** 原显示名称“组织” MUST 显示为“用户管理”
- **AND** 原显示名称“应用” MUST 显示为“应用管理”
- **AND** 原显示名称“设置” MUST 显示为“平台设置”

#### Scenario: 一级菜单内部稳定 key 保持不变
- **WHEN** 系统重构系统管理一级菜单显示名称
- **THEN** 菜单展示层 MUST 只修改显示名称相关字段
- **AND** 菜单内部稳定 key、企业 patch target 和既有权限编码关联标识 MUST 保持不变，除非本变更另有明确说明

#### Scenario: 安全管理一级菜单被移除
- **WHEN** 用户进入系统管理导航
- **THEN** 系统 MUST 不再展示 `security_management` 一级菜单入口

### Requirement: 用户管理必须承接原安全管理中的用户与认证页面

系统 MUST 将认证源、安全策略以及企业版敏感信息迁移到“用户管理”入口下。

#### Scenario: 用户管理展示新的子菜单结构
- **WHEN** 用户展开“用户管理”
- **THEN** 系统 MUST 展示“组织架构”“超级管理员”“认证源”“安全策略”子菜单

#### Scenario: 认证源迁移到用户管理路由
- **WHEN** 用户点击“认证源”菜单
- **THEN** 系统 MUST 进入 `/system-manager/user/auth-sources`

#### Scenario: 安全策略迁移到用户管理路由
- **WHEN** 用户点击“安全策略”菜单
- **THEN** 系统 MUST 进入 `/system-manager/user/security-settings`

#### Scenario: 企业版敏感信息迁移到用户管理路由
- **WHEN** 企业版菜单 patch 注入“敏感信息”入口
- **THEN** 系统 MUST 将其挂载到“用户管理”下
- **AND** 点击后 MUST 进入 `/system-manager/user/sensitive-info`

### Requirement: 平台设置必须承接设置类与日志类页面

系统 MUST 将平台设置作为承载门户设置、审计日志、错误日志、API 密钥和许可入口的统一一级菜单。

#### Scenario: 平台设置展示新的子菜单结构
- **WHEN** 用户展开“平台设置”
- **THEN** 系统 MUST 展示“门户设置”“审计日志”“错误日志”“API密钥”子菜单
- **AND** 在企业版可用时 MUST 继续展示“许可”子菜单

#### Scenario: 错误日志迁移到平台设置路由
- **WHEN** 用户点击“错误日志”菜单
- **THEN** 系统 MUST 进入 `/system-manager/settings/error-logs`

#### Scenario: 门户与许可保留在平台设置下
- **WHEN** 企业版菜单 patch 注入“门户设置”与“许可”入口
- **THEN** 系统 MUST 继续将二者挂载在“平台设置”下
- **AND** 门户入口 MUST 指向 `/system-manager/settings/portal`
- **AND** 许可入口 MUST 指向 `/system-manager/settings/license`

#### Scenario: 平台设置父级路径跳转到首个可见子菜单
- **WHEN** 用户访问 `/system-manager/settings`
- **THEN** 系统 MUST 继续使用父级目录页重定向逻辑，将其跳转到平台设置下首个可见子菜单
- **AND** 该默认落点 MUST 由当前合并后的菜单顺序与权限过滤结果共同决定

#### Scenario: 门户作为稳定企业版入口
- **WHEN** 企业版菜单 patch 注入“门户设置”入口
- **THEN** 系统 MUST 保留 `/system-manager/settings/portal` 作为稳定企业版访问路径

### Requirement: 被迁移页面的旧 security 路径必须废弃

系统 MUST 废弃本次被迁移页面的旧 `security/*` 访问路径，且不得提供兼容跳转。

#### Scenario: 旧认证源路径不再作为有效入口
- **WHEN** 用户访问旧路径 `/system-manager/security/auth-sources`
- **THEN** 系统 MUST 不再将其作为受支持的页面入口

#### Scenario: 旧安全策略路径不再作为有效入口
- **WHEN** 用户访问旧路径 `/system-manager/security/settings`
- **THEN** 系统 MUST 不再将其作为受支持的页面入口

#### Scenario: 旧错误日志路径不再作为有效入口
- **WHEN** 用户访问旧路径 `/system-manager/security/error-logs`
- **THEN** 系统 MUST 不再将其作为受支持的页面入口

#### Scenario: 旧敏感信息路径不再作为有效入口
- **WHEN** 用户访问旧路径 `/system-manager/security/sensitive-info`
- **THEN** 系统 MUST 不再将其作为受支持的页面入口

## Work Checklist

## 1. 社区版系统管理菜单与路由重构

- [x] 1.1 更新 `web/src/app/system-manager/constants/menu.json`，移除 `security_management` 一级菜单，并将一级菜单显示名称调整为“用户管理 / 应用管理 / 通知渠道 / 平台设置”，同时保持内部稳定 key 不变。
- [x] 1.2 调整社区版系统管理页面路由结构，将认证源迁移到 `user/auth-sources`、安全策略迁移到 `user/security-settings`、错误日志迁移到 `settings/error-logs`。
- [x] 1.3 为被迁移页面创建新的 page 入口文件，并移除旧 `security/*` 菜单入口，不增加兼容跳转逻辑。
- [x] 1.4 更新 `web/src/app/system-manager/locales/zh.json` 与 `web/src/app/system-manager/locales/en.json`，补齐新的一级菜单显示名称与“审计日志”相关展示文案。

## 2. 企业版菜单 patch 与路由清单同步

- [x] 2.1 更新 `WeOpsX-Enterprise/web/manifests/menus.json`，保持“门户”“许可”继续挂载到 `Setting`，并将“敏感信息”改为挂载到用户管理稳定 key（`structure` / `organization`）。
- [x] 2.2 更新 `WeOpsX-Enterprise/web/manifests/routes.json`，将敏感信息页面路由从 `/system-manager/security/sensitive-info` 调整为 `/system-manager/user/sensitive-info`，并同步 route source。
- [x] 2.3 校验企业版敏感信息页面在新的用户管理路径下仍可通过社区版 enterprise route shim 机制装配成功。

## 3. 审计日志统一页面实现

- [x] 3.1 新增 `web/src/app/system-manager/(pages)/settings/audit-log/page.tsx`，作为统一审计日志入口页。
- [x] 3.2 复用现有登录日志能力，将登录日志内容接入统一审计日志页，不丢失既有导出与筛选能力。
- [x] 3.3 将当前操作日志 page 内实现抽离为可复用内容组件，并接入统一审计日志页。
- [x] 3.4 在统一审计日志页中实现页签顺序“操作日志在前、登录日志在后”，并默认选中操作日志页签。

## 4. 权限与导航行为收口

- [x] 4.1 将统一审计日志页的访问控制收敛到 `audit_log-View`，移除 `operation_logs` / `user_logs` 子权限节点与页面内本地权限裁剪逻辑。
- [x] 4.2 更新 `user/page.tsx`、`settings/page.tsx` 依赖的首子菜单顺序，确认 `useRedirectFirstChild` 在新信息架构下仍按首个可见子菜单落点重定向，并据此校验平台设置默认落点。
- [x] 4.3 同步调整 `server/support-files/system_mgmt/menus/system-manager.json` 与日志 viewset 鉴权，使系统管理服务端权限树与 `audit_log-View` 收敛后的前端 IA 对齐。

## 5. 验证与收尾

- [x] 5.1 验证社区版菜单加载结果与企业版 patch 注入结果，确认“敏感信息”进入用户管理，“门户/许可”继续留在平台设置。
- [x] 5.2 验证新的页面路径 `/system-manager/user/*`、`/system-manager/settings/error-logs`、`/system-manager/settings/audit-log` 均可正常访问，且旧 `security/*` 迁移页面路径不再作为受支持入口。
- [x] 5.3 运行 `cd web && pnpm type-check`，并对系统管理菜单、`/system-manager/settings` 首子菜单重定向行为、审计日志页签默认行为与统一页面权限访问行为进行人工检查。
