# Add Alert Level Management Panel

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/add-alert-level-management-panel/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

告警中心已经存在 `alerts_level` 主数据、初始化脚本和前端动态消费逻辑，但缺少统一的等级管理入口。当前等级展示信息分散消费，无法在全局配置中对 `event`、`alert`、`incident` 三类等级进行可视化维护，也缺少删除引用校验、编号编辑约束和图标管理能力。

需要在全局配置中新增“告警等级管理” panel，将现有等级主数据正式开放为可管理能力，并统一前端对等级名称、颜色、图标的回显来源。

## What Changes

- 在告警中心全局配置页新增“告警等级管理” panel，按 `event`、`alert`、`incident` 三列卡片展示。
- 复用现有 `alerts_level` 模型和 `/alerts/api/level/` 接口，不新建等级模型。
- 新增等级时默认填充当前类型 `max(level_id) + 1`，但允许用户手工修改为同类型下唯一的非负整数。
- 编辑已有等级时禁止修改 `level_id`，仅允许编辑显示名、颜色和图标。
- 图标支持两类来源：默认内置图标选择，以及用户上传自定义图片。
- 删除等级时同时检查业务数据引用和配置引用；若存在任一引用则阻止删除。
- `built_in` 等级允许删除，但与普通等级遵循完全相同的删除校验规则。
- 每个 `level_type` 至少保留 1 个等级，不允许删空。
- 将前端等级回显统一为基于等级主数据的全局缓存，统一回显名称、颜色和图标。

## Capabilities

### New Capabilities
- `alert-level-management`: 在告警中心全局配置中管理 `event`、`alert`、`incident` 告警等级，并统一等级展示元数据的维护与回显。

### Modified Capabilities
- `alert-level-management`: 现有基于等级列表的前端回显逻辑改为统一消费等级主数据缓存，兼容默认图标和自定义上传图片。

## Impact

- `web/src/app/alarm/(pages)/settings/globalConfig/page.tsx`: 新增告警等级管理 panel。
- `web/src/app/alarm/context/common.tsx`: 扩展等级主数据缓存结构，支持统一回显名称、颜色、图标，并在设置修改后刷新。
- `web/src/app/alarm/(pages)/alarms/**`, `incidents/**`, `integration/**`, `settings/**`: 统一消费新的等级展示元数据。
- `server/apps/alerts/views/level.py`: 增加新增默认编号、编辑编号限制、删除引用检查和最少保留一条规则。
- `server/apps/alerts/serializers/level.py`: 增加 `level_id`、图标和删除规则相关校验。
- `server/apps/alerts/models/models.py`: 继续复用现有 `Level` 模型，不新增模型结构；`icon` 字段正式支持 iconfont type 或 data image。
- 需要补充对应前后端测试，覆盖删除阻止、编号规则、图标兼容渲染和公共缓存刷新。

## Implementation Decisions

## 设计概述

本次变更复用现有 `alerts_level` 主数据，在告警中心全局配置页增加一个“告警等级管理” panel。目标不是重做等级体系，而是把已有模型管理化，并统一前端所有等级名称、颜色、图标的回显来源。

核心原则：

- 继续以 `level_type + level_id` 作为等级标识。
- `event`、`alert`、`incident` 三类等级独立维护。
- 业务数据继续只存等级编号，展示信息从等级主数据中查询，不向业务表冗余名称、颜色或图标。
- 图标方案采用最小实现：同一个 `icon` 字段同时兼容默认 iconfont 和自定义上传图片。

## 现状

后端现状：

- `alerts_level` 已存在，字段包含 `level_id`、`level_display_name`、`color`、`icon`、`level_type`、`built_in`。
- `/alerts/api/level/` 已存在，但当前只是裸 `ModelViewSet` + 裸 serializer，缺少编号和删除约束。
- 初始化命令已经会将默认等级写入数据库。

前端现状：

- 告警中心通过 `CommonContext` 一次性拉取等级列表。
- 多个页面已按 `level_id` 动态回显等级名称、颜色、图标。
- 当前图标字段虽在模型注释中写为 base64，但前端现有展示大量按 `iconfont type` 渲染。

## 数据模型与字段语义

不新增 `Level` 模型字段，复用现有结构：

- `level_id`: 同类型下唯一的非负整数；数字越小表示越严重。
- `level_display_name`: 页面回显名称。
- `color`: 标签与筛选项颜色。
- `icon`: 等级图标渲染源。
- `level_type`: `event`、`alert`、`incident`。
- `built_in`: 是否系统预置，只表示来源，不表示不可编辑或不可删除。

### icon 字段语义调整

`icon` 字段统一定义为“图标渲染源”，兼容两种格式：

1. 默认图标：存 iconfont type，例如 `gantanhao1`
2. 自定义图标：存 `data:image/...;base64,...`

这样可以：

- 兼容历史默认图标值
- 不引入新的文件上传后端接口
- 直接支持用户上传自定义图片

## 后端规则

### 新增等级

- 列表返回继续按 `level_id asc` 排序。
- 新增接口支持前端先带默认值 `max(level_id) + 1`。
- 后端仍需校验：
  - `level_id` 必须为非负整数
  - 同一 `level_type` 下不得重复

### 编辑等级

- 允许编辑：
  - `level_display_name`
  - `color`
  - `icon`
- 不允许编辑：
  - `level_id`
  - `level_type`

如果请求中尝试修改已有记录的 `level_id`，接口必须拒绝。

### 删除等级

删除时必须同时检查：

1. 业务数据引用
2. 配置引用
3. 类型最少保留一条约束

#### 业务数据引用范围

- `alerts_event.level`
- `alerts_alert.level`
- `alerts_incident.level`

#### 配置引用范围

- `AlertAssignment.notification_frequency`
- 各类 `match_rules` 中的 `level_id`
- `AlarmStrategy.params.alert_template.level`

#### 删除判定

```text
删除 level(type=T, id=N)
  -> 若该 type 仅剩 1 条，拒绝
  -> 若存在业务数据引用，拒绝
  -> 若存在配置引用，拒绝
  -> 否则允许删除
```

`built_in` 等级与普通等级完全同规则处理，不做额外豁免，也不额外禁止。

### 删除失败提示

错误提示需区分：

- 已被业务数据引用，无法删除
- 已被配置引用，无法删除

如实现成本可接受，可进一步带出引用类别，例如“已被分派策略引用”。

## 前端页面设计

### 页面结构

在 `/alarm/settings/globalConfig` 中新增一个等级管理区域，展示为三列卡片：

- Event
- Alert
- Incident

每列卡片展示：

- 编号 `level_id`
- 显示名 `level_display_name`
- 颜色预览
- 图标预览
- 编辑/删除操作

### 表单交互

新增：

- 默认填充当前类型 `max(level_id) + 1`
- 允许用户手工修改为唯一非负整数

编辑：

- `level_id` 置为禁用态
- 允许编辑显示名、颜色、图标

图标编辑采用两段式：

- 默认图标选择
- 自定义上传

### 默认图标选择

首版提供一小组固定候选，沿用现有告警中心的 iconfont 风格，不开放全量 iconfont 搜索。

### 自定义上传

- 支持 `png`、`jpg`、`jpeg`、`svg`
- 前端将文件转为 Data URL
- 写入 `icon` 字段
- 限制最大 200KB
- 推荐尺寸 24x24 或 32x32

## 前端回显设计

前端等级展示信息视为全局主数据，而不是页面本地常量。所有页面统一从等级主数据缓存中获取：

- `level_display_name`
- `color`
- `icon`

### 公共缓存结构

基于现有 `CommonContext` 扩展为“按 type 分桶 + 按 id 快速索引”的结构：

```text
alert:
  list
  byId

event:
  list
  byId

incident:
  list
  byId
```

其中 `byId` 保存完整等级元数据，而不只是颜色映射。页面回显时不再分别从列表和颜色映射拆取信息，而是直接取完整对象。

### 统一回显规则

所有告警中心页面都通过 `level_type + level_id` 查找等级元数据：

```text
getLevelMeta(type, id)
  -> { level_display_name, color, icon }
```

图标渲染规则：

```text
if icon startsWith("data:image/")
  -> 按图片渲染
else
  -> 按 iconfont type 渲染
```

这样能同时兼容：

- 历史内置图标
- 用户上传的自定义图标

### 刷新策略

等级管理保存成功后，设置页不能只刷新当前卡片，还需要刷新告警中心的公共等级缓存，使以下页面尽快看到新值：

- 告警列表
- 事件列表
- 事故列表
- 详情页
- 筛选项
- 规则配置中的等级选择项

因此，等级管理页面保存成功后必须触发 `CommonContext` 中等级数据的重新拉取或统一失效刷新。

## 兼容性

- 历史默认等级数据不需要迁移。
- 历史 `iconfont type` 值继续可用。
- 新增上传图片后，同一字段会同时存在 iconfont type 和 data image，两种格式均受支持。
- 业务数据无需回填展示信息。

## 不做的事

- 不重构 monitor 域的 severity 体系。
- 不为图标引入新的文件上传服务或对象存储依赖。
- 不在业务表中冗余名称、颜色、图标。
- 不支持编辑已有等级的 `level_id`。
- 不支持批量删除等级。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-25
```

## Capability Deltas

### alert-level-management

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

## Work Checklist

## 1. 后端等级管理规则

- [x] 1.1 为 `Level` 的新增/编辑增加校验：`level_id` 必须为非负整数、同类型唯一
- [x] 1.2 为 `Level` 的更新增加限制：已存在记录禁止修改 `level_id` 和 `level_type`
- [x] 1.3 为 `Level` 的删除增加“每个类型至少保留 1 个等级”校验
- [x] 1.4 为 `Level` 的删除增加业务数据引用检查：`Event`、`Alert`、`Incident`
- [x] 1.5 为 `Level` 的删除增加配置引用检查：`notification_frequency`、`match_rules.level_id`、`alert_template.level`
- [x] 1.6 细化删除失败错误提示，区分业务数据引用与配置引用

## 2. 前端全局配置页面

- [x] 2.1 在 `globalConfig` 页面新增告警等级管理 panel
- [x] 2.2 按 `event`、`alert`、`incident` 三列卡片展示等级列表
- [x] 2.3 列表中增加等级颜色和图标预览
- [x] 2.4 新增表单默认填充 `max(level_id) + 1`，并允许手工修改
- [x] 2.5 编辑表单中禁用 `level_id`

## 3. 图标方案

- [x] 3.1 提供一组固定的默认图标候选，复用现有告警中心 iconfont 风格
- [x] 3.2 支持上传 `png/jpg/jpeg/svg` 自定义图标
- [x] 3.3 前端上传时将图标转换为 Data URL，并写入 `icon`
- [x] 3.4 前端增加图标大小和格式校验（最大 200KB）
- [x] 3.5 前端统一图标渲染逻辑：兼容 iconfont type 与 data image

## 4. 前端回显与缓存刷新

- [x] 4.1 扩展 `CommonContext` 的等级缓存结构，增加按类型的 `byId` 元数据索引
- [x] 4.2 统一告警中心页面的等级回显逻辑，统一消费名称、颜色、图标元数据
- [x] 4.3 等级管理保存成功后触发公共等级缓存刷新

## 5. 验证

- [ ] 5.1 验证新增时支持默认编号和手工补空洞编号
- [ ] 5.2 验证编辑时无法修改既有 `level_id`
- [ ] 5.3 验证 `built_in` 与普通等级删除规则一致
- [ ] 5.4 验证业务数据引用和配置引用均能阻止删除
- [ ] 5.5 验证自定义上传图标和默认图标在告警列表、事件列表、事故列表中均可正确回显
