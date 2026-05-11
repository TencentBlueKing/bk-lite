## ADDED Requirements

### Requirement: 社区版必须承载敏感信息管理所需的基础数据与接口契约
系统 MUST 在社区版 `system_mgmt` 中提供敏感信息管理所需的基础数据承载，包括用户手机号字段、敏感信息保护全局配置、授权数据模型，以及供商业版读取/保存这些数据的基础接口契约。

#### Scenario: 用户模型增加手机号字段
- **WHEN** 系统为用户模型增加手机号字段
- **THEN** 该字段 MUST 定义为可选字符串字段，属性为 `max_length=32`、`null=True`、`blank=True`
- **AND** 该字段 MUST 不设置唯一约束
- **AND** 该字段 MUST 不在模型层强制手机号格式正则校验

#### Scenario: 敏感信息全局配置保存到系统设置
- **WHEN** 管理员在敏感信息管理中保存启用开关或敏感信息类型
- **THEN** 系统 MUST 将“启用敏感信息保护”和“敏感信息类型”保存到社区版 `SystemSettings` 中作为全局配置项

#### Scenario: 授权关系由社区版模型承载
- **WHEN** 系统保存敏感信息授权记录
- **THEN** 授权数据 MUST 存储在社区版 `system_mgmt` 的数据模型中
- **AND** 授权语义 MUST 表示全局“授权用户 + 敏感类型”关系

#### Scenario: 社区版提供敏感信息配置与授权接口契约
- **WHEN** 商业版页面需要读取或保存敏感信息全局配置与授权数据
- **THEN** 社区版 MUST 提供基于 `SystemSettings` 与 `SensitiveInfoAuthorization` 的基础接口契约
- **AND** 系统 MUST 提供当前请求用户已授权敏感类型的查询接口，供前端根据授权状态决定展示/编辑模式

### Requirement: 敏感信息授权记录的新增与删除操作必须纳入操作日志
系统 MUST 在敏感信息授权记录新增或删除成功后写入 `system_mgmt.OperationLog`，以便审计授权关系的变更来源、目标用户和敏感类型范围。

#### Scenario: 新增授权记录时写入创建日志
- **WHEN** 管理员成功新增一条敏感信息授权记录
- **THEN** 系统 MUST 写入一条 `OperationLog`
- **AND** 该日志 MUST 使用 `action_type = create` 与 `app = sensitive_info`
- **AND** 日志摘要 MUST 包含被授权用户的 `username@domain` 与本次授权的敏感类型文本

#### Scenario: 删除授权记录时写入删除日志
- **WHEN** 管理员成功删除一条敏感信息授权记录
- **THEN** 系统 MUST 写入一条 `OperationLog`
- **AND** 该日志 MUST 使用 `action_type = delete` 与 `app = sensitive_info`
- **AND** 日志摘要 MUST 包含被撤销授权用户的 `username@domain` 与被删除记录中的敏感类型文本

### Requirement: 商业版必须通过 enterprise 入口提供敏感信息菜单与页面，而社区版静态菜单源不得直接显示该入口
系统 MUST 通过现有 enterprise manifest 和 route/shim 机制接入“安全管理 / 敏感信息”菜单与页面，且社区版静态菜单源不得直接包含该菜单项。

#### Scenario: 商业版菜单通过 enterprise manifest 注入
- **WHEN** 商业版启用敏感信息管理菜单
- **THEN** 菜单项 MUST 存放于商业版 `web/manifests/menus.json`
- **AND** 菜单项 MUST 通过 patch 注入到 `security_management` 节点下

#### Scenario: 社区版静态菜单源不直接包含敏感信息入口
- **WHEN** 社区版前端加载 `web/src/app/system-manager/constants/menu.json`
- **THEN** 社区版静态菜单源 MUST 不直接包含“敏感信息”菜单项

#### Scenario: 商业版页面通过 enterprise route 与 generated shim 机制加载
- **WHEN** 用户访问敏感信息管理页面路由
- **THEN** 路由声明 MUST 存放于商业版 `web/manifests/routes.json`
- **AND** 页面实现 MUST 通过现有 enterprise route / generated shim 机制加载，而不是在社区版手写独立的商业版页面业务

### Requirement: 商业版必须对已接入的人类界面用户查询出口执行敏感字段展示控制
系统 MUST 在商业版中对当前已接入的人类界面用户查询出口执行邮箱和手机号的脱敏与明文放行控制，同时保持未接入展示控制的机器消费路径不受影响。

#### Scenario: 敏感信息保护关闭时维持现有展示行为
- **WHEN** 全局“启用敏感信息保护”配置为关闭
- **THEN** 已接入的人类界面用户查询结果 MUST 按现有行为返回邮箱和手机号字段值

#### Scenario: 敏感信息保护开启时默认脱敏
- **WHEN** 全局“启用敏感信息保护”配置为开启
- **THEN** 当前已接入的人类界面用户查询出口 MUST 对已纳入敏感信息类型配置的邮箱和手机号执行脱敏展示

#### Scenario: 授权用户可查看对应类型明文
- **WHEN** 当前请求用户已被授权查看某一敏感信息类型
- **THEN** 已接入的人类界面用户查询结果 MUST 仅对该已授权类型返回明文

#### Scenario: 超级管理员不天然豁免
- **WHEN** 当前请求用户是超级管理员但未被授予对应敏感信息类型权限
- **THEN** 系统 MUST 继续返回脱敏后的邮箱或手机号，而不能因超管身份直接返回明文

#### Scenario: 机器消费路径保持原值能力
- **WHEN** 未接入展示脱敏逻辑的机器消费路径读取用户联系方式用于系统动作
- **THEN** 系统 MUST 保持这些路径的原值读取能力
- **AND** 商业版展示脱敏逻辑 MUST 不影响诸如 `get_all_users` 之类机器消费路径的现有行为

### Requirement: 社区版必须提供手机号基础资料维护能力，并在接口层对手机号执行宽松校验
系统 MUST 在社区版用户管理中提供手机号作为基础资料字段的新增、编辑和查询能力，并在接口层对手机号执行宽松校验。

#### Scenario: 新增用户时维护手机号
- **WHEN** 管理员在系统管理新增用户并填写手机号
- **THEN** 社区版用户新增流程 MUST 支持保存手机号字段

#### Scenario: 编辑用户时维护手机号
- **WHEN** 管理员在系统管理编辑现有用户资料并修改手机号
- **THEN** 社区版用户编辑流程 MUST 支持更新手机号字段

#### Scenario: 用户查询结果包含手机号基础字段
- **WHEN** 社区版用户详情或列表接口返回用户基础资料
- **THEN** 系统 MUST 在其基础资料契约中支持手机号字段
- **AND** 商业版可以在此基础上进一步决定该字段返回明文还是脱敏值

#### Scenario: 手机号在接口层采用宽松校验
- **WHEN** 新增或编辑用户提交手机号
- **THEN** 系统 MUST 允许空值直接通过
- **AND** 对非空值 MUST 允许数字、空格、`+`、`-`、`(`、`)` 组成的宽松格式
- **AND** 在移除分隔符后 MUST 以 7~15 位数字作为有效值范围

### Requirement: 未授权查看敏感字段时，编辑用户流程必须采用显式覆盖语义而不是写侧拒绝
系统 MUST 在编辑用户场景中避免因脱敏展示造成误覆盖；当当前用户不能查看明文时，敏感字段修改必须以显式覆盖语义完成，而不能把“无查看权限”等同为“无写入权限”。

#### Scenario: 受保护且未授权的敏感字段进入 overwrite 模式
- **WHEN** 全局敏感信息保护开启、字段类型被纳入保护范围，且当前编辑用户未被授权查看该字段明文
- **THEN** 用户编辑弹窗中的对应敏感字段 MUST 进入 overwrite 模式
- **AND** 该字段在进入编辑前 MUST 以只读方式展示

#### Scenario: 用户必须显式确认敏感字段修改
- **WHEN** 用户在 overwrite 模式下点击敏感字段的编辑动作
- **THEN** 系统 MUST 清空当前表单值并等待用户输入新值
- **AND** 系统 MUST 提供确认/取消动作来显式完成或放弃本次修改

#### Scenario: 敏感字段仍处于编辑中时阻止整单提交
- **WHEN** 任一 overwrite 模式的敏感字段仍处于编辑中
- **THEN** 系统 MUST 阻止底部确认提交流程继续执行

#### Scenario: 未显式确认的敏感字段不得覆盖原值
- **WHEN** overwrite 模式下的敏感字段未被显式确认修改
- **THEN** 前端提交 payload MUST 省略该字段
- **AND** 后端更新用户时 MUST 保留原有邮箱/手机号值不变

#### Scenario: 显式提供的新敏感字段值仍允许更新
- **WHEN** 保护开启且当前用户没有对应敏感字段的明文查看授权，但其在 overwrite 模式下显式确认了新的邮箱或手机号
- **THEN** 系统 MUST 允许该新值被保存
- **AND** 系统 MUST 不因为缺少查看权限而额外拒绝这次显式修改
