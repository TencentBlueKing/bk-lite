## Why

运营分析参数输入存在两类问题：

1. **输入形态割裂**：组件配置抽屉和统一筛选分别处理输入框、下拉和单选，选项配置体验不一致。
2. **内置参数缺少声明式选项来源**：例如 `CMDB 3D机房布局.server_room_id` 应天然使用 CMDB 机房列表作为候选项，但当前只能手动配置或手动输入。

本变更把“参数选项配置”提升为“参数输入配置”：

- 输入控件支持输入框、下拉选择、单选按钮。
- 下拉/单选的选项来源支持静态列表和动态数据源。
- 内置数据源可用稳定的 `sourceRef/rest_api` 声明动态选项来源，不依赖数据库生成 ID。
- 组件配置抽屉和统一筛选共用同一个编辑器内部交互。
- 数据源管理参数表不提供手动选项配置入口，避免全局配置入口过重。

## What Changes

- 新增统一模型 `InputControlConfig`，替代本分支早期的 `optionsConfig` 作为新主模型。
- 新增/改造共享编辑器 `paramInputConfigEditor.tsx`：
  - 控件类型：输入框 / 下拉选择 / 单选按钮
  - 选项来源：自定义选项 / 数据源选项
- 新增/改造运行渲染组件 `paramInputControl.tsx`：
  - `input` 渲染原始参数输入控件
  - `select` 渲染 Select
  - `radio` 渲染 Radio.Group
  - 动态来源失败或无选项时回退原始输入控件，不阻断参数配置
- 组件配置抽屉：
  - 消费数据源定义中的 `inputConfig`
  - 允许 widget 级覆盖写入 `valueConfig.dataSourceParams[i].inputConfig`
- 统一筛选：
  - 使用同一个 `paramInputConfigEditor.tsx`
  - 新配置写入 `UnifiedFilterDefinition.inputConfig`
  - select/radio 运行态走同一套消费逻辑
- 数据源管理参数表：
  - 删除/不新增“选项”列和编辑入口
  - 只维护参数名、类型、默认值、过滤类型等基础字段
- CMDB 首个落地：
  - 注册 `CMDB 机房列表` 内置数据源（`rest_api: "cmdb/get_room_list"`）
  - `CMDB 3D机房布局.server_room_id.inputConfig` 声明引用 `cmdb/get_room_list`

## Capabilities

### New Capabilities

- `param-input-source`: 运营分析参数输入配置能力；支持输入框、下拉选择、单选按钮；下拉/单选支持静态选项与动态数据源选项；内置数据源可通过 `sourceRef/rest_api` 声明默认选项来源。

### Modified Capabilities

- 统一筛选配置：select 与 radio 的选项编辑和运行消费改为统一 `InputControlConfig` 模型。
- 组件参数配置：查询参数输入控件改为消费 `InputControlConfig`，并允许 widget 级覆盖。
- 内置数据源初始化：`source_api.json` 中参数可携带 `inputConfig`。

## Impact

- **前端**:
  - `web/src/app/ops-analysis/types/dataSource.ts` - 新增 `InputControlConfig`，扩展 `ParamItem.inputConfig`
  - `web/src/app/ops-analysis/types/dashBoard.ts` - 扩展 `UnifiedFilterDefinition.inputConfig`
  - `web/src/app/ops-analysis/components/paramInputConfigEditor.tsx` - 新增/替换共享编辑器
  - `web/src/app/ops-analysis/components/paramInputControl.tsx` - 新增/替换运行渲染组件
  - `web/src/app/ops-analysis/utils/paramInputConfigUtils.ts` - 新增归一化与动态来源解析工具
  - `web/src/app/ops-analysis/components/paramsConfig.tsx` - 按 `inputConfig` 渲染参数输入
  - `web/src/app/ops-analysis/components/widgetConfig.tsx` - 写入 widget 级 `inputConfig`
  - `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx` - 使用统一编辑器
  - `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx` - select/radio 共用统一运行渲染
  - `web/src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx` - 移除本分支新增的选项配置入口
  - `web/src/app/ops-analysis/locales/zh.json` + `en.json` - 新增/调整 i18n key

- **后端**:
  - 新增 `cmdb/get_room_list` NATS handler 与服务函数
  - 不需要数据库 schema 变更

- **数据存储**:
  - `inputConfig` 存在现有 JSON 字段中，无数据库迁移
  - 旧 `options` 只做读取兼容，写入新配置时只写 `inputConfig`

## Out of Scope

- 不做数据源管理页面的全局选项来源手动编辑。
- 不做“恢复内置默认”按钮。
- 不做动态来源参数映射。
- 不做多种 `sourceRef` 类型，首版只支持 `rest_api`。
- 不做 TTL 缓存、选项快照或复杂空态过滤。
- 不做数据库迁移。

## 首个落地案例：CMDB 机房列表内置选项源

让 `CMDB 3D机房布局.server_room_id` 默认显示当前用户可见机房列表。

实现方式：

- 后端提供 `cmdb/get_room_list`，返回 CMDB 原始字段 `_id`、`inst_name` 等，并复用现有权限过滤。
- `source_api.json` 注册 `CMDB 机房列表`，`chart_type: []`。
- `CMDB 3D机房布局.server_room_id.inputConfig` 使用：

```json
{
  "control": "select",
  "optionsSource": {
    "type": "dynamic",
    "sourceRef": {
      "type": "rest_api",
      "value": "cmdb/get_room_list"
    },
    "valueField": "_id",
    "labelField": "inst_name"
  }
}
```
