# 运营分析画布分类拆分设计

日期：2026-06-29

## 背景

运营分析当前已经具备 `Dashboard`、`Topology`、`Architecture` 三类内容视图，以及数据源、命名空间、目录、权限、导入导出、内置画布等基础能力。近期为了满足展示类场景，部分固定分辨率、全屏展示、标题、时钟、装饰框、暗色大屏主题和发光效果被加入到拓扑图链路中，导致拓扑图逐渐同时承担“关系定位”和“大屏展示”两种产品语义。

同时，仪表盘也容易和报表混用：仪表盘适合在线分析、筛选、联动和下钻，报表则面向周期沉淀、结论输出和归档。若继续把展示、分析、关系、输出混在现有画布里，后续新增 Screen、Report、外部数据源和模板体系时，会出现入口、权限、导入导出、组件归属和代码复用边界不清的问题。

本设计先统一画布分类和代码演进边界，不进入完整大屏编辑器或完整报表系统建设。

## 现状依据

后端内容对象当前为三张相似表：

- `Dashboard`：包含 `filters`、`other`、`view_sets`、`directory`、`groups`、内置标识等字段。
- `Topology`：包含 `other`、`view_sets`、`directory`、`groups`、内置标识等字段。
- `Architecture`：包含 `other`、`view_sets`、`directory`、`groups`、内置标识等字段。

证据：`server/apps/operation_analysis/models/models.py`

导入导出当前只登记 `dashboard`、`topology`、`architecture`、`datasource`、`namespace`。证据：`server/apps/operation_analysis/constants/import_export.py`

前端主视图页按 `dashboard`、`topology`、`architecture` 硬编码渲染对应页面。证据：`web/src/app/ops-analysis/(pages)/view/page.tsx`

拓扑图中已经混入大屏能力，包括：

- `screen-title`、`screen-clock`、`decorative-frame` 节点生成。
- `TopologyPresentationConfig`、`TopologyViewportConfig`。
- 固定分辨率、letterbox 全屏、`tech-blue` 背景。
- `TopologyPresentationModal`、`useTopologyPresentation`。
- `screen-dark` 图表主题和 `panelChrome*` 玻璃面板样式在拓扑图表节点中可被使用。

证据：`web/src/app/ops-analysis/(pages)/view/topology/index.tsx`、`web/src/app/ops-analysis/(pages)/view/topology/components/presentationModal.tsx`、`web/src/app/ops-analysis/(pages)/view/topology/hooks/useTopologyPresentation.ts`、`web/src/app/ops-analysis/utils/chartTheme.ts`

## 产品决策

本期采用“现有三类保留 + 新增 Screen/Report”的口径：

| 类型 | 状态 | 产品定位 |
|---|---|---|
| `dashboard` | 已有，保留 | 仪表盘，面向日常分析、筛选、联动、趋势、明细和下钻。 |
| `topology` | 已有，保留并清理 | 拓扑图，面向关系表达、路径定位、影响范围和健康态叠加。 |
| `architecture` | 已有，继续作为正式类型保留 | 架构图，面向系统结构、业务结构、技术架构等结构表达，不被 Screen 替代。 |
| `screen` | 新增 | 大屏，面向值班总览、汇报展示、态势感知和固定分辨率展示编排。 |
| `report` | 新增基础类型 | 报表，面向周期沉淀、汇总输出、结论和归档；一期只做基础架构。 |
| `scene` | 后续 | 场景，作为主题容器，组织同一主题下的多类内容。 |

对原始需求中“Architecture 收敛到大屏/展示视图”的表述，本项目修订为：

`Architecture` 继续作为架构表达类画布保留，新增入口、编辑入口和查看入口均保留。它不承接固定分辨率、标题、时钟、装饰背景、screen 主题等大屏能力，这些能力统一归属 `Screen`。

## 目标

1. 新增 `Screen` 作为独立大屏内容类型，承接从拓扑图剥离的大屏能力。
2. 新增 `Report` 作为独立报表内容类型，一期只建设基础对象和内容结构，不建设完整报表系统。
3. 保留 `Dashboard`、`Topology`、`Architecture` 三类已有对象。
4. 从 `Topology` 中清理大屏化能力，让拓扑图回到关系画布边界。
5. 将 `screen-dark`、`screen-light`、发光图表、玻璃面板、标题、时钟、装饰框、固定分辨率等能力限制为 `Screen` 使用。
6. 建立统一画布类型注册机制，减少新增类型时在前端、后端、导入导出、权限和菜单里的分散硬编码。

## 非目标

1. 不建设完整大屏模板市场、轮播、多屏拼接、复杂动效。
2. 不建设完整报表生成、定时任务、数据快照、历史版本、订阅、分享、审批。
3. 不把三张已有画布表立即合并成统一 `Canvas` 表。
4. 不考虑旧拓扑图中已经保存的大屏配置兼容。
5. 不做大量兼容兜底和历史数据迁移逻辑。
6. 不改变 `Architecture` 的新增、编辑、查看能力。

## 画布能力边界

### Dashboard

保留能力：

- 折线图、柱状图、饼图、单值卡、Gauge、表格、事件表、TopN。
- 统一筛选、时间范围、命名空间切换。
- 组件分组、刷新、全屏查看、PDF 临时导出。
- 表格操作列和下钻。
- 值映射、单位格式化、同比/对比。

不新增能力：

- 固定分辨率展示编排。
- 标题、时钟、装饰框、展示背景等大屏 chrome。
- 周期报表生成、归档和快照。

### Topology

保留能力：

- 普通节点、连线、关系边、层级、依赖、影响面。
- 单值节点、轻量图表节点；这些节点必须服务于关系理解。
- 健康态、告警态、颜色态、路径高亮。
- 节点下钻。
- 缩放、适配视图、普通全屏。
- 编辑、保存、撤销、重做、选择模式、删除。
- 统一筛选和刷新。

清理能力：

- 固定分辨率和 letterbox 全屏。
- 标题、时钟、装饰框、展示背景。
- `screen-dark`、`screen-light` 作为拓扑节点可选主题。
- `glass`、大屏科技边框、玻璃面板、`panelChrome*`。
- `TopologyPresentationModal`、`useTopologyPresentation`、`TopologyPresentationConfig`、`TopologyViewportConfig` 等大屏语义。

### Architecture

保留能力：

- 作为架构图正式类型继续存在。
- 保留新增、编辑、查看、删除、导入导出等既有入口。
- 用于系统结构、业务结构、技术架构等结构表达。

不承接能力：

- 不承接 Screen 的固定分辨率、大屏主题、标题、时钟、装饰背景和边界内编排规则。
- 不作为 Screen 的替代或过渡入口。

### Screen

一期基础能力：

- 新建、编辑、删除、查看。
- 创建时由系统写入默认分辨率，创建后可在 Screen 页面内调整目标分辨率，支持常用预设和自定义尺寸；暂不改造通用创建弹窗。
- 固定分辨率画布，组件不得超出边界。
- 全屏展示和按容器等比缩放。
- 本轮只完成画布级交互闭环；标题、时钟、背景、主题、装饰框和组件编排后续单独实现。
- 后续可复用通用图表组件：单值卡、Gauge、折线图、柱状图、饼图、TopN、事件表。
- 后续可支持 `screen-dark`、`screen-light` 主题和发光/玻璃面板等展示效果。
- 后续可复用只读型关系展示区块，例如网络状态拓扑或局部拓扑块，但不承接拓扑图重编辑能力。

不做能力：

- 不做复杂节点连线编辑。
- 不做撤销重做为核心的关系建模。
- 不做深度排障推理流程。
- 不做完整模板市场和轮播编排。

### Report

一期基础能力：

- 新建、编辑、删除、查看。
- 标题、描述、时间范围。
- 基础内容块结构，预留图表块、表格块、文本块、摘要块。
- 可复用数据源和部分通用图表渲染能力。

不做能力：

- 不做定时生成。
- 不做生成时数据快照。
- 不做历史版本。
- 不做 PDF/Excel 高级导出。
- 不做分享链接、订阅和审批。

## 后端设计

### 模型策略

本期不合并已有 `Dashboard`、`Topology`、`Architecture`，避免大规模迁移风险。新增：

- `Screen`
- `Report`

`Screen` 和 `Report` 采用与现有画布对象一致的基础字段：

- `name`
- `desc`
- `directory`
- `other`
- `view_sets`
- `groups`
- `is_build_in`
- `build_in_key`

其中 `Screen.view_sets` 表达固定分辨率画布内容，建议结构为：

```json
{
  "viewport": {
    "width": 1920,
    "height": 1080
  },
  "items": [],
  "decorations": {}
}
```

本轮不在 `viewport` 中预留 `theme`、`background` 字段。主题、背景、标题、时钟和装饰能力等到对应交互实现时再扩展结构，避免提前引入无消费方字段。

`Report.view_sets` 表达报表内容块，建议结构为：

```json
{
  "time_range": null,
  "sections": []
}
```

### 共享服务

现有 `DashboardModelViewSet`、`TopologyModelViewSet`、`ArchitectureModelViewSet` 重复度较高。新增 `Screen`、`Report` 前应抽取轻量共享能力，但不修改公共 `AuthViewSet`：

- 内置对象只读保护。
- 目录可见范围校验。
- create/update/partial_update/destroy 审计日志模板。
- 画布基础 serializer mixin。

建议新增模块：

```text
server/apps/operation_analysis/services/canvas/
  registry.py
  viewset_mixins.py
  viewset_serializers.py
```

`registry.py` 负责集中声明类型元信息：

```python
CANVAS_TYPE_REGISTRY = {
    "dashboard": {...},
    "topology": {...},
    "architecture": {...},
    "screen": {...},
    "report": {...},
}
```

这样后续导入导出、目录树、权限和菜单不再继续依赖分散判断。

### 导入导出

新增对象类型：

- `screen`
- `report`

`CANVAS_TYPES` 扩展为 `dashboard / topology / architecture / screen / report`。

YAML schema 版本需要升级，例如从 `1.0.0` 到 `1.1.0`，因为对象类型和章节增加。新增章节：

```yaml
screens: []
reports: []
```

本期不考虑旧拓扑大屏配置向 Screen 自动迁移。拓扑导入导出只保留拓扑关系画布结构；Screen 导入导出承接固定分辨率和展示编排结构。

## 前端设计

### 画布类型注册

新增统一画布类型注册表，替代 `ViewPage`、`Sidebar`、导入导出、创建菜单中的分散硬编码。

建议路径：

```text
web/src/app/ops-analysis/constants/canvasTypes.ts
```

建议结构：

```ts
export const canvasTypeRegistry = {
  dashboard: {
    labelKey: 'canvas.dashboard',
    api: 'dashboard',
    component: Dashboard,
    permissionKey: 'directory.dashboard',
  },
  topology: {
    labelKey: 'canvas.topology',
    api: 'topology',
    component: Topology,
    permissionKey: 'directory.topology',
  },
  architecture: {
    labelKey: 'canvas.architecture',
    api: 'architecture',
    component: Architecture,
    permissionKey: 'directory.architecture',
  },
  screen: {
    labelKey: 'canvas.screen',
    api: 'screen',
    component: Screen,
    permissionKey: 'directory.screen',
  },
  report: {
    labelKey: 'canvas.report',
    api: 'report',
    component: Report,
    permissionKey: 'directory.report',
  },
};
```

`ViewPage` 应从注册表解析组件、ref 和未保存检查能力，避免继续扩展 `selectedItem.dashboard/topology/architecture` 这种固定结构。

### Screen 页面结构

建议新增：

```text
web/src/app/ops-analysis/(pages)/view/screen/
  index.tsx
  components/
    screenToolbar.tsx
    screenCanvas.tsx
    screenConfigModal.tsx
    screenWidgetFrame.tsx
  hooks/
    useScreenCanvas.ts
    useScreenPresentation.ts
  utils/
    viewport.ts
```

`Screen` 不复用拓扑图的 X6 关系编辑器作为核心。Screen 应有自己的固定分辨率画布和绝对定位/边界内编排模型。图表内容可复用 `WidgetRenderer` 和已有 widget。

Screen 的大屏视觉由容器控制：

- `ScreenCanvas` 控制固定分辨率和缩放。
- `ScreenConfigModal` 控制分辨率预设和自定义宽高。
- `ScreenToolbar` 控制画布设置和全屏预览入口。
- `ScreenWidgetFrame` 后续控制玻璃面板、装饰框、标题区；本轮不实现。
- `chartThemeMode` 后续由 Screen 统一注入或在 Screen 组件配置中选择；本轮不新增主题字段。

通用 widget 继续保持数据渲染职责，不直接承担大屏外框和装饰。

### Screen 第一阶段交互补充

本轮优先补齐大屏区别于普通画布的最小可用交互闭环，只包含默认分辨率、分辨率配置、固定比例画布和全屏预览。

#### 默认分辨率

创建 Screen 时不要求用户先选择分辨率。创建接口或前端默认值直接写入初始 `view_sets.viewport`：

```json
{
  "viewport": {
    "width": 1920,
    "height": 1080
  },
  "items": [],
  "decorations": {}
}
```

这样创建入口保持轻量，用户进入 Screen 详情页后再通过“画布设置”调整分辨率。

#### 画布设置

Screen 详情页顶部新增“画布设置”入口。点击后打开配置弹窗，用户可以选择常用分辨率或填写自定义宽高。

常用预设：

- `1920 × 1080`
- `1366 × 768`
- `3840 × 2160`

自定义宽高要求：

- 宽度和高度必须为正整数。
- 保存时写入 `view_sets.viewport.width` 和 `view_sets.viewport.height`。
- 不写入 `theme`、`background`、标题、时钟等字段。

#### 固定比例画布

Screen 主体区域渲染固定比例画布。画布使用 `viewport.width / viewport.height` 计算宽高比，在可用容器内等比缩放。

画布需要展示：

- 当前分辨率。
- 清晰的画布边界。
- 空状态提示，说明组件编排能力后续补充。

画布暂不支持：

- 组件添加。
- 拖拽编排。
- 数据绑定。
- 标题、时钟、背景和主题配置。

#### 全屏预览

Screen 工具栏新增“全屏预览”入口。进入全屏后：

- 隐藏设置按钮、普通页面说明和非展示 chrome。
- 保留固定比例画布。
- 画布按屏幕可用空间等比缩放。
- 提供退出全屏能力。

全屏预览仍是查看态，不提供编辑交互。

### Report 页面结构

建议新增：

```text
web/src/app/ops-analysis/(pages)/view/report/
  index.tsx
  components/
    reportToolbar.tsx
    reportEditor.tsx
    reportSection.tsx
```

一期 Report 只实现内容对象壳和基础内容结构。完整生成、快照、导出和历史版本后续单独设计。

### Topology 清理

从拓扑中删除或迁出：

- `TopologyPresentationModal`
- `useTopologyPresentation`
- `TopologyViewportConfig`
- `TopologyPresentationConfig`
- `presentationConfig`
- `viewportConfig`
- `letterboxLayout`
- `screen-title`
- `screen-clock`
- `decorative-frame`
- `tech-blue`
- `screenCanvasBackground`
- 工具栏中的大屏/演示配置入口
- 拓扑保存/加载中的 `viewport`、`presentation` 写入逻辑
- 拓扑配置中的 `chartThemeMode` 入口
- 拓扑节点中的大屏 `panelChrome*` 样式

保留普通全屏查看。普通全屏不等于固定分辨率大屏，仍属于拓扑图查看能力。

### 图表主题边界

`chartTheme.ts` 中的 `screen-dark`、`screen-light` 和发光图表能力保留为后续 Screen 能力，但本轮不新增主题配置入口和数据字段。

Dashboard 和 Topology 默认只使用普通亮色/暗色主题。若已有通用 widget 通过 `chartThemeMode` 支持大屏主题，保留函数实现；配置入口等 Screen 主题交互实现时再暴露。

## 后续数据结构建议

### Screen item（组件编排阶段）

以下结构用于后续组件编排阶段，本轮不落地 `chartThemeMode`、`frame` 等主题和装饰配置：

```json
{
  "id": "widget-1",
  "type": "widget",
  "x": 40,
  "y": 80,
  "w": 360,
  "h": 220,
  "zIndex": 1,
  "valueConfig": {
    "chartType": "line",
    "dataSource": 1
  },
  "frame": {
    "variant": "glass",
    "showTitle": true
  }
}
```

### Report section

```json
{
  "id": "section-1",
  "type": "chart",
  "title": "告警趋势",
  "valueConfig": {
    "chartType": "line",
    "dataSource": 1
  }
}
```

## 实施顺序建议

1. 新增画布类型注册表，收敛前端类型硬编码。
2. 后端新增 `Screen`、`Report` 基础模型、serializer、viewset、路由。
3. 扩展目录树，让 `screen`、`report` 与现有类型并列出现。
4. 新增 Screen 基础页面、分辨率配置、固定比例画布、全屏预览和最小保存查看闭环。
5. 新增 Report 基础页面和对象壳。
6. 从 Topology 删除大屏配置入口和 presentation 相关链路。
7. 后续将 Screen 主题、标题、时钟、装饰框、玻璃面板能力归入 Screen 页面。
8. 扩展导入导出 schema 支持 `screen`、`report`。
9. 更新 ops-analysis 设计文档和用户可见文案。

## 验收标准

1. 创建入口中 `Dashboard`、`Topology`、`Architecture`、`Screen`、`Report` 类型边界清晰。
2. `Architecture` 仍可新增、编辑、查看，不被 Screen 替代。
3. `Topology` 不再出现固定分辨率、大屏配置、标题、时钟、装饰背景、screen 主题配置入口。
4. `Topology` 仍保留节点、连线、关系编辑、筛选、刷新、普通全屏、撤销重做。
5. `Screen` 可配置分辨率，并以固定比例画布展示该分辨率边界。
6. `Screen` 支持全屏预览，预览态按可用屏幕空间等比缩放。
7. 本轮 `Screen` 不新增主题、背景、标题、时钟、组件编排和数据绑定能力。
8. `Report` 作为独立类型存在，具备基础新建、编辑、查看能力，但不承诺完整报表系统。
9. 导入导出、目录树和前端类型注册均识别 `screen`、`report`。
10. 代码中新增画布类型不需要在多个页面重复追加硬编码分支。

## 风险与控制

| 风险 | 控制 |
|---|---|
| 同时新增 Screen 和 Report 导致范围扩大 | Report 一期只做对象壳和基础结构，复杂能力后置。 |
| Screen 与 Dashboard 组件重复 | 图表渲染复用 `WidgetRenderer`，Screen 只负责固定分辨率和展示容器。 |
| Screen 与 Topology 关系区块重复 | Screen 只复用只读关系展示块，不提供拓扑重编辑能力。 |
| Architecture 与 Screen 边界再次混淆 | Architecture 负责架构表达；Screen 负责固定分辨率展示编排。 |
| 导入导出 schema 变化影响已有能力 | 通过 schema 版本升级和类型注册集中扩展，不在各服务散落判断。 |

## 待后续单独设计

- Scene 场景容器模型与导航。
- Screen 模板、轮播、多屏拼接和高级动效。
- Report 定时生成、数据快照、导出、历史版本和分享。
- 外部数据源接入后与 Screen/Report 的模板联动。
