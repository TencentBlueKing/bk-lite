## MODIFIED Requirements

### Requirement: 许可管理页面必须通过稳定设置路由加载企业版实现

系统 MUST 保留 `/system-manager/settings/license` 作为稳定访问路径，并由该路径加载企业版许可管理页面实现。

#### Scenario: 公共设置页访问许可页
- **WHEN** 用户访问 `/system-manager/settings/license`
- **THEN** 系统 MUST 通过公共路由壳加载 enterprise 许可管理页面，而不是在公共页内直接实现许可业务

#### Scenario: 许可页使用统一弹窗组件
- **WHEN** 页面展示“添加许可”或“设置许可提醒”弹窗
- **THEN** 系统 MUST 使用仓库现有 `OperateModal` 组件承载弹窗交互

#### Scenario: 系统管理信息架构重构后许可仍位于平台设置
- **WHEN** 系统管理一级菜单重构为“用户管理 / 应用管理 / 通知渠道 / 平台设置”
- **THEN** 系统 MUST 继续将许可入口挂载在“平台设置”下
- **AND** 许可入口 MUST 继续使用 `/system-manager/settings/license` 作为稳定路由
