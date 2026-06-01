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
