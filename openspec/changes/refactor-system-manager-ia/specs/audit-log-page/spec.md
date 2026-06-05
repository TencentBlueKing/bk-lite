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
