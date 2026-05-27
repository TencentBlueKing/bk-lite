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
