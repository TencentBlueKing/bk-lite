## ADDED Requirements

### Requirement: 系统必须支持在告警中心全局配置中管理告警等级

系统 MUST 在告警中心全局配置页提供告警等级管理能力，并按 `event`、`alert`、`incident` 三类分别维护等级。

#### Scenario: 全局配置页展示三类等级卡片
- **WHEN** 用户进入告警中心全局配置页
- **THEN** 系统 MUST 展示 `event`、`alert`、`incident` 三个独立等级管理区域
- **AND** 每个区域 MUST 按 `level_id` 升序展示等级列表

#### Scenario: 新增等级默认填充下一顺序号
- **WHEN** 用户在某个等级类型下点击新增
- **THEN** 系统 MUST 默认填充该类型当前 `max(level_id) + 1`
- **AND** 用户 MUST 可以将该默认值手工修改为同类型下唯一的非负整数

#### Scenario: 编辑已有等级时禁止修改编号
- **WHEN** 用户编辑已存在的等级
- **THEN** 系统 MUST 禁止修改该等级的 `level_id`
- **AND** 系统 MUST 允许编辑显示名、颜色和图标

### Requirement: 系统必须统一维护等级图标来源并支持默认与自定义图标

系统 MUST 允许等级图标同时支持默认内置图标和用户上传的自定义图片，并通过同一 `icon` 字段存储图标渲染源。

#### Scenario: 用户选择默认图标
- **WHEN** 用户在等级编辑表单中选择默认图标
- **THEN** 系统 MUST 将该图标保存为可供前端 iconfont 渲染的标识值

#### Scenario: 用户上传自定义图标
- **WHEN** 用户上传 `png`、`jpg`、`jpeg` 或 `svg` 图片作为等级图标
- **THEN** 系统 MUST 将该图片保存为 `data:image/...` 格式的图标值
- **AND** 系统 MUST 校验上传图片大小不超过 200KB

#### Scenario: 页面回显默认图标
- **WHEN** 等级的 `icon` 为默认图标标识值
- **THEN** 告警中心页面 MUST 按 iconfont 方式渲染该图标

#### Scenario: 页面回显自定义图标
- **WHEN** 等级的 `icon` 为 `data:image/...` 图标值
- **THEN** 告警中心页面 MUST 按图片方式渲染该图标

### Requirement: 系统必须在删除等级时检查业务数据与配置引用

系统 MUST 在删除等级前同时检查业务数据引用和配置引用，只要存在任一引用就阻止删除。

#### Scenario: 被业务数据引用时禁止删除
- **WHEN** 待删除等级已被事件、告警或事故数据引用
- **THEN** 系统 MUST 拒绝删除该等级
- **AND** 错误提示 MUST 明确说明该等级已被业务数据引用

#### Scenario: 被配置引用时禁止删除
- **WHEN** 待删除等级已被分派策略、匹配规则或缺失检测策略引用
- **THEN** 系统 MUST 拒绝删除该等级
- **AND** 错误提示 MUST 明确说明该等级已被配置引用

#### Scenario: built_in 等级删除规则与普通等级一致
- **WHEN** 待删除等级为 `built_in` 等级
- **THEN** 系统 MUST 按与普通等级相同的引用校验和最少保留规则处理

#### Scenario: 每个类型至少保留一个等级
- **WHEN** 用户尝试删除某个类型下的最后一个等级
- **THEN** 系统 MUST 拒绝删除

### Requirement: 前端必须统一从等级主数据回显名称、颜色和图标

告警中心前端 MUST 将等级名称、颜色和图标视为主数据元信息，并统一从公共等级缓存中回显，而不能在业务页面写死展示值。

#### Scenario: 列表页从公共等级缓存回显等级信息
- **WHEN** 告警列表、事件列表或事故列表展示某条记录的等级
- **THEN** 页面 MUST 基于 `level_type + level_id` 从公共等级缓存中获取显示名、颜色和图标

#### Scenario: 等级配置更新后刷新公共回显
- **WHEN** 用户在等级管理中保存等级配置变更成功
- **THEN** 系统 MUST 刷新告警中心公共等级缓存
- **AND** 后续页面展示 MUST 使用最新的显示名、颜色和图标
