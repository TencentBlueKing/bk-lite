# 运营分析通信关系图 Implementation Plan

> **For agentic workers:** 按任务顺序 TDD 实现；规格见 `specs/changes/ops-analysis-node-graph/spec.md`。未要求 git commit 时跳过各任务的 Commit 步。

**Goal:** 新增通用数据源图表 `nodeGraph`（通信关系图）：把 instant 排行聚成有向流量图，支持 IP↔IP 与源 IP→目的 IP:端口。

**Architecture:** 纯函数把行列表变成 nodes/edges；组件用已有 `@antv/x6` + `@antv/layout` 的 `ForceLayout` 画图；配置提交与 TopN 同路。不新开 NATS，不改网络状态拓扑 / 关系拓扑契约，不改 Flow YAML。

**Tech Stack:** Next.js、Ant Design、X6、`@antv/layout`、Django 仅改草稿允许的图表类型集合与数据源 `chart_type`。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `web/src/app/ops-analysis/utils/nodeGraphData.ts` | 行 → 图模型：粒度、聚合、自环丢弃、截断、平行边偏移 |
| `web/src/app/ops-analysis/utils/__tests__/nodeGraphData.test.ts` | 上述外部行为 |
| `web/src/app/ops-analysis/components/widgets/nodeGraph/index.tsx` | 仪表盘/大屏渲染：力导向、边宽、悬停 |
| `web/src/app/ops-analysis/components/widgetConfig/sections/nodeGraphSettingsSection.tsx` | 字段映射 + 粒度 |
| `web/src/app/ops-analysis/components/widgetRegistry.ts` | 注册 `nodeGraph` |
| `web/src/app/ops-analysis/components/widgetConfig/utils/submitConfig.ts` | 持久化映射/粒度/单位 |
| `web/src/app/ops-analysis/utils/topologyMapWidgetContract.ts` | `hasRenderableChartData` 认 `nodeGraph` |
| `server/apps/operation_analysis/support-files/source_api.json` | 受控指标排行 `chart_type` 加上 `nodeGraph` |
| `server/apps/operation_analysis/services/canvas_draft/constants.py` | 草稿允许 `nodeGraph` |

不要改 Flow 样例 YAML。不要改 `topologyMapData.ts` 或网络状态拓扑取数。

验证命令（在对应目录跑，路径相对 `web/` 或 `server/`）：

```bash
cd web && pnpm exec tsx --test \
  src/app/ops-analysis/utils/__tests__/nodeGraphData.test.ts \
  src/app/ops-analysis/components/widgetConfig/utils/__tests__/submitConfig.nodeGraph.test.ts \
  src/app/ops-analysis/constants/__tests__/chartTypeList.test.ts \
  src/app/ops-analysis/utils/__tests__/topologyMapWidgetContract.test.ts

cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest apps/operation_analysis/tests/test_flow_dashboard_datasource_definitions.py --no-cov
```

---

### Task 1: 行到图纯函数

**Files:**
- Create: `web/src/app/ops-analysis/utils/nodeGraphData.ts`
- Test: `web/src/app/ops-analysis/utils/__tests__/nodeGraphData.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_NODE_GRAPH_MAX_EDGES,
  buildNodeGraph,
  isNodeGraphMappingComplete,
} from '../nodeGraphData';

const mapping = {
  identityMode: 'ip' as const,
  sourceField: 'src',
  targetField: 'dst',
  valueField: 'value',
};

test('incomplete mapping is not ready and builds an empty graph', () => {
  assert.equal(isNodeGraphMappingComplete({ sourceField: 'src' }), false);
  assert.deepEqual(buildNodeGraph([{ src: '10.0.0.1', dst: '10.0.0.2', value: 9 }], {
    sourceField: 'src',
    targetField: 'dst',
  }), { nodes: [], edges: [] });
});

test('service mode requires a destination port field', () => {
  assert.equal(
    isNodeGraphMappingComplete({
      identityMode: 'service',
      sourceField: 'src',
      targetField: 'dst',
      valueField: 'value',
    }),
    false,
  );
});

test('ip mode aggregates duplicate pairs and drops self-loops and blank rows', () => {
  const graph = buildNodeGraph(
    [
      { src: '10.0.0.1', dst: '10.0.0.2', value: 8 },
      { src: '10.0.0.1', dst: '10.0.0.2', value: 2 },
      { src: '10.0.0.2', dst: '10.0.0.2', value: 99 },
      { src: '', dst: '10.0.0.3', value: 4 },
      { src: '10.0.0.3', dst: '10.0.0.1', value: 5 },
    ],
    mapping,
  );
  assert.deepEqual(
    graph.edges.map((edge) => [edge.source, edge.target, edge.value]),
    [
      ['10.0.0.1', '10.0.0.2', 10],
      ['10.0.0.3', '10.0.0.1', 5],
    ],
  );
  const nodeById = Object.fromEntries(graph.nodes.map((node) => [node.id, node]));
  assert.equal(nodeById['10.0.0.1'].outbound, 10);
  assert.equal(nodeById['10.0.0.1'].inbound, 5);
  assert.equal(nodeById['10.0.0.2'].inbound, 10);
  assert.equal(nodeById['10.0.0.3'].outbound, 5);
});

test('service mode uses destination IP:port and skips missing ports', () => {
  const graph = buildNodeGraph(
    [
      { src: '10.0.0.1', dst: '10.0.0.9', dst_port: 443, value: 7 },
      { src: '10.0.0.2', dst: '10.0.0.9', dst_port: 443, value: 3 },
      { src: '10.0.0.1', dst: '10.0.0.9', value: 50 },
    ],
    {
      identityMode: 'service',
      sourceField: 'src',
      targetField: 'dst',
      targetPortField: 'dst_port',
      valueField: 'value',
    },
  );
  assert.deepEqual(
    graph.edges.map((edge) => [edge.source, edge.target, edge.value]),
    [
      ['10.0.0.1', '10.0.0.9:443', 7],
      ['10.0.0.2', '10.0.0.9:443', 3],
    ],
  );
});

test('keeps the highest-traffic edges up to the cap', () => {
  const rows = Array.from({ length: 5 }, (_, index) => ({
    src: `10.0.0.${index + 1}`,
    dst: '10.0.0.9',
    value: index + 1,
  }));
  const graph = buildNodeGraph(rows, { ...mapping, maxEdges: 2 });
  assert.equal(graph.edges.length, 2);
  assert.equal(graph.edges[0].value, 5);
  assert.equal(graph.edges[1].value, 4);
  assert.equal(DEFAULT_NODE_GRAPH_MAX_EDGES, 100);
});

test('unwraps { items: [...] } like other rank widgets', () => {
  const graph = buildNodeGraph(
    { items: [{ src: 'a', dst: 'b', value: 1 }] },
    mapping,
  );
  assert.equal(graph.edges[0].source, 'a');
});
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd web && pnpm exec tsx --test src/app/ops-analysis/utils/__tests__/nodeGraphData.test.ts
```

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 `nodeGraphData.ts`**

要点（实现必须满足上面的断言）：

- `unwrap`：数组原样；对象则取 `items` / `data` / `list` 中第一个数组（与 TopN 相同习惯）。
- 单元格：`getValueByPath` + `String(...).trim()`；数值 `Number`，非有限则丢行。
- `ip`：`source = src`，`target = dst`。
- `service`：`target = `${dst}:${port}``；端口空则丢行。
- 自环（source===target）丢弃。
- 按 `(source,target)` 求和；再按 `value` 降序截断到 `maxEdges ?? 100`。
- 节点 `outbound`/`inbound` 只统计截断后的边。
- 导出 `assignNodeGraphParallelOffsets(edges)`：同一无序节点对多条边时给 `parallelOffset`（对称 …,-12,0,12,…），单边为 0。可照 `parallelEdges.ts` 的算法，step 用 16。

- [ ] **Step 4: 再跑测试**

Expected: PASS。

---

### Task 2: 图表类型与数据源声明

**Files:**
- Modify: `web/src/app/ops-analysis/constants/common.ts`（`getChartTypeList` 增加 `{ label: 'dataSource.nodeGraph', value: 'nodeGraph' }`，放在 `topologyMap` 旁）
- Modify: `web/src/app/ops-analysis/types/dataSource.ts` 的 `ChartType` 联合加上 `'nodeGraph'`
- Modify: `web/src/app/ops-analysis/types/screen.ts` 的 `ScreenWidgetChartType` 加上 `'nodeGraph'`
- Modify: `web/src/app/ops-analysis/locales/zh.json` 与 `en.json`：
  - `dataSource.nodeGraph`：通信关系图 / Communication Graph
  - `opsAnalysis.screen.widgets.nodeGraph` 同上
  - `opsAnalysis.screen.widgetDescriptions.nodeGraph`：展示 IP 或服务之间的有向流量 / Show directed traffic between IPs or services
  - `topology.nodeConfig.nodeGraphIdentity`：节点粒度 / Node grain
  - `topology.nodeConfig.nodeGraphIdentityIp`：IP ↔ IP
  - `topology.nodeConfig.nodeGraphIdentityService`：源 IP → 目的 IP:端口 / Source IP → dest IP:port
  - `topology.nodeConfig.nodeGraphSourceField`：源字段 / Source field
  - `topology.nodeConfig.nodeGraphTargetField`：目的字段 / Destination field
  - `topology.nodeConfig.nodeGraphValueField`：流量字段 / Traffic field
  - `topology.nodeConfig.nodeGraphTargetPortField`：目的端口字段 / Destination port field
  - `dashboard.nodeGraphMappingRequired`：请完整配置源、目的和流量字段 / Map source, destination, and value fields
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/constants/widgets.ts` 增加一项，宽高对齐 `topologyMap`（620×420）
- Modify: `server/apps/operation_analysis/support-files/source_api.json` 受控指标排行 `"chart_type"` 改为 `["topN", "table", "single", "pie", "nodeGraph"]`
- Modify: `server/apps/operation_analysis/tests/test_flow_dashboard_datasource_definitions.py` 的 `test_metric_series_instant_source_supports_rank_charts`：`chart_type` 集合 `>= {"topN", "table", "single", "pie", "nodeGraph"}`
- Modify: `web/src/app/ops-analysis/constants/__tests__/chartTypeList.test.ts`：`getChartTypeList` 含 `nodeGraph`；报表表面即使数据源声明 `nodeGraph` 也不返回它（沿用 `resolveDatasourceChartTypes(..., surface: 'report')`）

- [ ] **Step 1: 先改测试再改实现**（chartTypeList 与 pytest 断言）
- [ ] **Step 2: 跑**

```bash
cd web && pnpm exec tsx --test src/app/ops-analysis/constants/__tests__/chartTypeList.test.ts
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest apps/operation_analysis/tests/test_flow_dashboard_datasource_definitions.py --no-cov
```

Expected: 测试改完先红，实现后绿。

---

### Task 3: 配置提交与表单

**Files:**
- Modify: `web/src/app/ops-analysis/types/dashBoard.ts` `ValueConfig` 增加：

```ts
  nodeGraphIdentityMode?: 'ip' | 'service';
  nodeGraphSourceField?: string;
  nodeGraphTargetField?: string;
  nodeGraphValueField?: string;
  nodeGraphTargetPortField?: string;
```

- Modify: `web/src/app/ops-analysis/components/widgetConfig/utils/submitConfig.ts`
  - `WidgetConfigFormValues` 增加同样字段
  - `VALUE_FORMAT_CHART_TYPES` 加入 `'nodeGraph'`
  - `chartType === 'nodeGraph'` 时写入上述字段；`identityMode` 缺省 `'ip'`；`service` 时才写 `nodeGraphTargetPortField`
- Create: `web/src/app/ops-analysis/components/widgetConfig/utils/__tests__/submitConfig.nodeGraph.test.ts`
- Create: `web/src/app/ops-analysis/components/widgetConfig/sections/nodeGraphSettingsSection.tsx`（照 `topNSettingsSection.tsx`：粒度 Select + 三个字段 Select；`identityMode === 'service'` 时再出目的端口 Select；选项来自 `field_schema`）
- Modify: `web/src/app/ops-analysis/components/widgetConfig.tsx`
  - 加载/重置这些字段（与 `topNLabelField` 并列）
  - `chartType === 'nodeGraph'` 渲染 `NodeGraphSettingsSection`，其后若 `VALUE_FORMAT_CHART_TYPES` 已含 `nodeGraph` 会自动出现单位区
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts`：`VALUE_FORMAT_CHART_TYPES` 加 `nodeGraph`；`chartType === 'nodeGraph'` 时写入同样字段

提交测试：

```ts
import assert from 'node:assert/strict';
import test from 'node:test';
import { buildWidgetSubmitConfig } from '../submitConfig';

const base = {
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: [],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
};

test('nodeGraph submit persists mapping, service port, and unit conversion', () => {
  const result = buildWidgetSubmitConfig({
    ...base,
    chartType: 'nodeGraph',
    values: {
      name: '通信关系图',
      chartType: 'nodeGraph',
      dataSource: 57,
      nodeGraphIdentityMode: 'service',
      nodeGraphSourceField: 'src',
      nodeGraphTargetField: 'dst',
      nodeGraphValueField: 'value',
      nodeGraphTargetPortField: 'dst_port',
      unitId: 'bps',
      conversionFactor: 8,
      decimalPlaces: 1,
    },
  });
  assert.equal(result.error, undefined);
  assert.equal(result.config?.chartType, 'nodeGraph');
  assert.equal(result.config?.nodeGraphIdentityMode, 'service');
  assert.equal(result.config?.nodeGraphSourceField, 'src');
  assert.equal(result.config?.nodeGraphTargetField, 'dst');
  assert.equal(result.config?.nodeGraphValueField, 'value');
  assert.equal(result.config?.nodeGraphTargetPortField, 'dst_port');
  assert.equal(result.config?.unitId, 'bps');
  assert.equal(result.config?.conversionFactor, 8);
  assert.equal(result.config?.decimalPlaces, 1);
  assert.equal('sceneWidgetType' in (result.config || {}), false);
});

test('nodeGraph ip mode omits destination port', () => {
  const result = buildWidgetSubmitConfig({
    ...base,
    chartType: 'nodeGraph',
    values: {
      name: '通信关系图',
      chartType: 'nodeGraph',
      nodeGraphIdentityMode: 'ip',
      nodeGraphSourceField: 'src',
      nodeGraphTargetField: 'dst',
      nodeGraphValueField: 'value',
      nodeGraphTargetPortField: 'dst_port',
    },
  });
  assert.equal(result.config?.nodeGraphIdentityMode, 'ip');
  assert.equal('nodeGraphTargetPortField' in (result.config || {}), false);
});
```

```bash
cd web && pnpm exec tsx --test src/app/ops-analysis/components/widgetConfig/utils/__tests__/submitConfig.nodeGraph.test.ts
```

---

### Task 4: 渲染、注册、可渲染判定

**Files:**
- Create: `web/src/app/ops-analysis/components/widgets/nodeGraph/index.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetRegistry.ts`：`nodeGraph: NodeGraph`
- Modify: `web/src/app/ops-analysis/utils/componentParamSwitch.ts`：`COMPONENT_SWITCH_CHART_TYPES` 加入 `'nodeGraph'`（与 TopN 一样切指标）
- Modify: `web/src/app/ops-analysis/utils/topologyMapWidgetContract.ts`：`hasRenderableChartData` 在 `nodeGraph` 时：
  - 映射不完整 → `false`（走配置提示，不当成有数据）
  - `buildNodeGraph(data, config).edges.length > 0`
  - 把 `config` 参数类型扩成可含 nodeGraph 字段（调用方已传整个 `valueConfig`）
- Modify: `web/src/app/ops-analysis/utils/__tests__/topologyMapWidgetContract.test.ts` 增加两例：会话行 + 完整映射为 true；空数组为 false
- Modify: `server/apps/operation_analysis/services/canvas_draft/constants.py`：`WIDGET_CHART_TYPES` 加入 `"nodeGraph"`

组件行为（不要测像素）：

- props 与 TopN 对齐：`rawData`、`loading`、`config`、`onReady`、`errorMessage`、`screenRenderContext`。
- 映射不完整：`WidgetState` + `t('dashboard.nodeGraphMappingRequired')`，`onReady(true)`（避免报告卡 loading）。
- 空图：现有 `WidgetState` 空状态。
- 有边：X6 `Graph`，`ForceLayout`（`@antv/layout`，参考 `web/src/app/cmdb/(pages)/assetData/detail/relationships/networkTopo.tsx` 的 force 调用）。节点小圆+文字，**大小固定**。边 `strokeWidth` 按 `value` 线性映射到 1–8；箭头；`assignNodeGraphParallelOffsets` 的偏移用 connector 错开互访边。
- 悬停边：源、目的、`formatVisibleChartValue(edge.value, config)`。悬停节点：id、入/出合计（同样格式化）。
- 不保存坐标；`rawData` 变化则重新 `buildNodeGraph` + 布局。
- 暗色主题用 `getOpsChartThemeByMode` 的文字/边颜色，禁止硬编码主题蓝以外的业务色；可用现有图表蓝。
- 布局用 Tailwind；不要新建 SCSS Module。

```bash
cd web && pnpm exec tsx --test src/app/ops-analysis/utils/__tests__/topologyMapWidgetContract.test.ts
```

---

### Task 5: 收口验证

- [ ] 跑 Task 1–4 列出的全部命令，全部绿。
- [ ] `rg "nodeGraph" server/apps/operation_analysis/support-files/flow_dashboard.yaml` 无命中（本变更不改样例盘）。
- [ ] 未改 `topologyMapData.ts`、网络状态拓扑 API。
- [ ] 若改了 `widgetConfig.tsx` 类型，跑 `cd web && pnpm type-check`（或至少确认无新增 TS 错误）。

---

## Spec coverage

| 规格条目 | 任务 |
|---|---|
| 通用 `nodeGraph`，非 scene | 2、3、4 |
| instant 行聚合，不新 NATS | 1、4 |
| `ip` / `service` 粒度，源端口不上图 | 1、3 |
| 自环/缺字段丢弃、100 边截断 | 1 |
| 力导向、互访双边、边宽、不存坐标 | 4 |
| 悬停格式化流量 | 4 |
| 空选择空图 | 1+4（空数组 → empty） |
| 单位配置 | 3 |
| 受控指标排行声明图表 | 2 |
| 不进报表表面 | 2 |
| 不改 Flow YAML | 5 |
| 草稿允许该类型 | 4（`WIDGET_CHART_TYPES`） |
