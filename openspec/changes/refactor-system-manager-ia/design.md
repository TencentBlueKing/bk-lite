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
