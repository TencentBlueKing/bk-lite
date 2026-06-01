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
