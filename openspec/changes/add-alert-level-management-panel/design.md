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
