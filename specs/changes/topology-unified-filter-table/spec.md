# Topology Unified Filter Table

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/topology-unified-filter-table/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

拓扑图当前缺乏与仪表盘一致的统一筛选能力。用户在拓扑图中添加图表/单值节点后，无法像仪表盘那样通过顶部筛选栏统一控制多个节点的筛选条件。此外，拓扑图还缺少：
- 表格类型节点支持
- 取消编辑按钮（恢复到进入编辑模式时的状态）
- 筛选配置入口

需要将仪表盘的统一筛选能力复用到拓扑图，保持两个视图的交互一致性。

## What Changes

- 新增拓扑图顶部统一筛选栏，复用仪表盘的 `UnifiedFilterBar` 组件
- 新增命名空间选择器，从 chart/single-value/table 节点提取可用命名空间
- 新增筛选配置按钮（编辑模式下显示），复用 `UnifiedFilterConfigModal`
- 新增取消编辑按钮，恢复到进入编辑模式时的图状态
- 新增表格类型节点（table），复用仪表盘的 `ComTable` 组件
- 扩展节点 `valueConfig` 支持 `filterBindings` 和 `tableConfig`
- 点击搜索时刷新所有关联了筛选项的 chart/single-value/table 节点
- 拓扑图保存/加载时包含 `filters` 字段

## Capabilities

### New Capabilities

- `topology-unified-filter`: 拓扑图统一筛选功能，复用仪表盘筛选组件
- `topology-table-node`: 拓扑图表格节点支持

### Modified Capabilities

- `topology-edit-mode`: 新增取消编辑功能，恢复到进入编辑模式时的状态

## Impact

- **前端**:
  - `web/src/app/ops-analysis/(pages)/view/topology/index.tsx` - 集成筛选栏、筛选配置、取消按钮
  - `web/src/app/ops-analysis/(pages)/view/topology/components/toolbar.tsx` - 添加筛选配置和取消按钮
  - `web/src/app/ops-analysis/(pages)/view/topology/components/tableNode.tsx` - 新增表格节点组件
  - `web/src/app/ops-analysis/(pages)/view/topology/components/chartNode.tsx` - 扩展支持 table 类型
  - `web/src/app/ops-analysis/(pages)/view/topology/components/nodeSidebar.tsx` - 添加表格节点拖拽选项
  - `web/src/app/ops-analysis/(pages)/view/topology/hooks/useGraphData.ts` - 保存/加载 filters
  - `web/src/app/ops-analysis/(pages)/view/topology/hooks/useGraphOperations.ts` - 筛选刷新逻辑
  - `web/src/app/ops-analysis/(pages)/view/topology/utils/registerNode.ts` - 注册 table 节点
  - `web/src/app/ops-analysis/types/topology.ts` - 扩展类型定义

- **复用组件**（无需修改）:
  - `web/src/app/ops-analysis/components/unifiedFilter/` - 筛选栏和配置弹窗
  - `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/comTable.tsx` - 表格组件
  - `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx` - 已在拓扑图中使用

- **数据存储**:
  - 拓扑图 `view_sets` 结构扩展，添加 `filters` 字段

## Implementation Decisions

## Context

拓扑图已具备以下基础设施：
- X6 图形引擎，支持节点拖拽、连线、缩放等操作
- `chart` 和 `single-value` 节点类型，通过 `valueConfig` 配置数据源
- `ViewConfig` 组件用于配置图表节点（已复用仪表盘组件）
- `useGraphData` hook 处理拓扑图的保存/加载
- `useGraphOperations` hook 处理图形操作和节点数据刷新

仪表盘已实现的统一筛选功能：
- `UnifiedFilterBar` 组件渲染筛选栏
- `UnifiedFilterConfigModal` 组件配置筛选项
- `useUnifiedFilter` hook 管理筛选状态
- `collectNamespaceOptions` 从组件提取命名空间选项
- `buildFiltersFromLayout` 从组件构建筛选定义

本设计复用仪表盘组件，最小化新增代码。

## Goals / Non-Goals

**Goals:**
- 拓扑图顶部显示统一筛选栏，与仪表盘交互一致
- 命名空间选择器从 chart/single-value/table 节点提取选项
- 编辑模式下显示筛选配置按钮，打开配置弹窗
- 编辑模式下显示取消按钮，恢复到进入编辑模式时的状态
- 新增表格节点类型，复用 `ComTable` 组件
- 点击搜索时刷新所有关联节点
- 拓扑图保存/加载包含 filters 配置

**Non-Goals:**
- 不实现拓扑图专属的筛选控件类型（复用仪表盘的 string/timeRange）
- 不实现节点显示/隐藏联动（仅刷新数据）
- 不实现跨拓扑图共享筛选状态
- 不修改后端 API（复用现有 topology API）

## Decisions

### D1: 筛选栏位置

**决策**: 筛选栏放在工具栏下方、画布上方，与仪表盘布局一致

**理由**:
- 保持两个视图的交互一致性
- 筛选栏不占用画布空间，不影响节点拖拽

### D2: 命名空间选项提取

**决策**: 从 X6 Graph 节点提取，适配 `collectNamespaceOptions` 函数

**理由**:
- 拓扑图节点结构与仪表盘 LayoutItem 不同，需要适配
- 仅从 chart/single-value/table 节点提取，其他节点（icon/text/basic-shape）不参与

**实现**:
```typescript
const collectNamespaceOptionsFromNodes = (
  graphInstance: Graph,
  dataSources: DatasourceItem[],
  namespaceList: Array<{ id: number; name: string }>
): NamespaceOption[] => {
  const namespaceIds = new Set<number>();

  graphInstance.getNodes().forEach(node => {
    const nodeData = node.getData();
    if (['chart', 'single-value', 'table'].includes(nodeData.type)) {
      const dsId = nodeData.valueConfig?.dataSource;
      const ds = dataSources.find(d => d.id === dsId);
      if (ds?.namespaces) {
        ds.namespaces.forEach(id => namespaceIds.add(id));
      }
    }
  });

  return namespaceList
    .filter(ns => namespaceIds.has(ns.id))
    .map(ns => ({ label: ns.name, value: ns.id }));
};
```

### D3: 取消编辑的状态恢复

**决策**: 进入编辑模式时保存完整图状态（`graphInstance.toJSON()`），取消时恢复

**理由**:
- X6 提供 `toJSON()` / `fromJSON()` 方法，可完整保存/恢复图状态
- 包括节点位置、连线、数据等所有信息

**风险**:
- `rawData`（图表数据）可能不在 JSON 中，需要重新加载
- Mitigation: 恢复后触发一次全量刷新

### D4: 筛选刷新机制

**决策**: 点击搜索时遍历所有节点，根据 `filterBindings` 判断是否需要刷新

**理由**:
- 与仪表盘的 `searchKey` 机制不同，拓扑图节点是 X6 React 节点
- 需要主动调用 `loadChartNodeData` / `updateSingleNodeData` 刷新数据

**实现**:
```typescript
const refreshFilteredNodes = (filterValues: Record<string, FilterValue>) => {
  graphInstance.getNodes().forEach(node => {
    const nodeData = node.getData();
    if (!['chart', 'single-value', 'table'].includes(nodeData.type)) return;

    const bindings = nodeData.valueConfig?.filterBindings;
    if (!bindings || !hasActiveBindings(bindings, filterValues)) return;

    if (nodeData.type === 'chart' || nodeData.type === 'table') {
      loadChartNodeData(node.id, nodeData.valueConfig, filterValues);
    } else if (nodeData.type === 'single-value') {
      updateSingleNodeData(nodeData, filterValues);
    }
  });
};
```

### D5: 表格节点实现

**决策**: 创建 `tableNode.tsx`，复用 `ComTable` 组件，与 `chartNode.tsx` 结构类似

**理由**:
- 表格组件已在仪表盘中实现，直接复用
- 表格节点需要处理分页、筛选等内部状态

**注意**:
- 表格节点默认尺寸需要比图表节点大（建议 400x300）
- 表格内部筛选与统一筛选独立，不冲突

### D6: 数据持久化

**决策**: 拓扑图保存数据结构扩展为 `{ name, view_sets: { nodes, edges }, filters }`

**理由**:
- 与仪表盘结构对齐
- `filters` 存储 `UnifiedFilterDefinition[]`

## Risks / Trade-offs

**[Risk] X6 状态恢复不完整** → `toJSON()` 可能不包含 React 节点的运行时数据
- Mitigation: 恢复后触发全量刷新；测试验证恢复完整性

**[Risk] 表格节点性能** → 大数据量表格在拓扑图中渲染可能卡顿
- Mitigation: 表格默认分页 20 条；用户可调整节点大小

**[Trade-off] 复用 vs 定制**
- 选择最大化复用仪表盘组件，减少代码量
- 代价：拓扑图特有需求可能需要后续扩展

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-23
```

## Work Checklist

## 1. 类型定义扩展

- [x] 1.1 在 `web/src/app/ops-analysis/types/topology.ts` 中扩展 `TopologyValueConfig`，添加 `filterBindings?: FilterBindings` 和 `tableConfig?: TableConfig` 字段
- [x] 1.2 在 `web/src/app/ops-analysis/types/topology.ts` 中扩展 `TopologySaveData`，添加 `filters?: UnifiedFilterDefinition[]` 字段

## 2. 工具栏改造

- [x] 2.1 修改 `web/src/app/ops-analysis/(pages)/view/topology/components/toolbar.tsx`，添加 `onCancel` 和 `onFilterConfig` props
- [x] 2.2 在编辑模式下添加「筛选配置」按钮，点击触发 `onFilterConfig`
- [x] 2.3 在编辑模式下添加「取消」按钮，点击触发 `onCancel`，按钮位置在保存按钮左侧

## 3. 主组件集成筛选栏

- [x] 3.1 在 `web/src/app/ops-analysis/(pages)/view/topology/index.tsx` 中添加筛选相关状态：`definitions`, `filterValues`, `originalDefinitions`, `searchKey`, `selectedNamespaceId`
- [x] 3.2 添加 `originalGraphState` 状态，用于取消编辑时恢复
- [x] 3.3 在工具栏下方、画布上方集成 `UnifiedFilterBar` 组件
- [x] 3.4 集成 `UnifiedFilterConfigModal` 组件
- [x] 3.5 实现 `handleCancelEdit` 函数，恢复图状态和筛选定义
- [x] 3.6 实现 `handleFilterConfigConfirm` 函数，更新筛选定义

## 4. 命名空间选项提取

- [x] 4.1 创建 `collectNamespaceOptionsFromNodes` 函数，从 X6 节点提取命名空间选项
- [x] 4.2 在主组件中使用 `useMemo` 计算命名空间选项
- [x] 4.3 实现命名空间选择器，选择变化时触发节点刷新

## 5. 筛选刷新逻辑

- [x] 5.1 使用 `searchKey` 状态触发筛选刷新（与仪表盘一致）
- [x] 5.2 命名空间选择变化时递增 `searchKey` 触发刷新
- [x] 5.3 筛选值变化时递增 `searchKey` 触发刷新
- [x] 5.4 筛选配置确认时递增 `searchKey` 触发刷新

## 6. 取消编辑功能

- [x] 6.1 在进入编辑模式时保存 `graphInstance.toJSON()` 到 `originalGraphState`
- [x] 6.2 在进入编辑模式时保存 `definitions` 到 `originalDefinitions`
- [x] 6.3 实现取消编辑时恢复图状态：`graphInstance.fromJSON(originalGraphState)`
- [x] 6.4 实现取消编辑时恢复筛选定义：`setDefinitions([...originalDefinitions])`
- [x] 6.5 恢复后触发全量节点刷新

## 7. 表格节点支持

- [x] 7.1 表格作为图表类型，无需单独创建 tableNode.tsx
- [x] 7.2 表格作为图表类型，无需单独注册节点
- [x] 7.3 表格作为图表类型，通过 ViewConfig 选择 chartType=table
- [x] 7.4 在 `chartNode.tsx` 的 `componentMap` 中添加 `table: ComTable`
- [x] 7.5 表格使用 CHART_NODE 默认尺寸 400x220

## 8. 数据持久化

- [x] 8.1 修改 `useGraphData.ts` 中的 `handleSaveTopology`，保存时包含 `filters` 字段
- [x] 8.2 修改 `useGraphData.ts` 中的 `handleLoadTopology`，加载时读取 `filters` 字段并返回
- [x] 8.3 在主组件加载拓扑时设置 `definitions` 和 `originalDefinitions`

## 9. 筛选定义构建

- [x] 9.1 创建 `buildFiltersFromNodes` 函数，从 X6 节点构建筛选定义（类似仪表盘的 `buildFiltersFromLayout`）
- [x] 9.2 创建 `convertNodesToLayoutItems` 函数，用于 UnifiedFilterConfigModal
- [x] 9.3 筛选定义通过 UnifiedFilterConfigModal 手动配置

## 10. ViewConfig 集成

- [x] 10.1 确认 `ViewConfig` 组件已支持 `filterBindings` 配置（仪表盘已实现）
- [x] 10.2 确认 `ViewConfig` 组件已支持 `tableConfig` 配置（仪表盘已实现）
- [x] 10.3 在拓扑图中传递 `filterDefinitions` 给 `ViewConfig`

## 11. 测试与验证

- [x] 11.1 执行 `cd web && pnpm lint && pnpm type-check` 确保类型检查通过
- [ ] 11.2 手动验证：拓扑图添加图表节点，筛选栏正确显示
- [ ] 11.3 手动验证：配置筛选项并保存，刷新后回显正确
- [ ] 11.4 手动验证：点击搜索，关联节点正确刷新
- [ ] 11.5 手动验证：取消编辑，图状态正确恢复
- [ ] 11.6 手动验证：添加表格节点，数据正确显示
- [ ] 11.7 手动验证：命名空间选择器正确过滤节点数据
