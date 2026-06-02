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
