# Historical Superpowers change: 2026-06-02-ops-analysis-dashboard-grouping

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-02-ops-analysis-dashboard-grouping.md

## 目标

在不改后端 `view_sets` 顶层结构的前提下，为 Ops Analysis 仪表盘补齐可用的分组编排能力，并为关键行为建立可执行护栏。

## 已落地实现

### 1. 运行时布局切换到 GridStack

- 前端画布已从 `react-grid-layout` 迁移到 GridStack。
- 分组采用“根网格 + 组内 sub-grid”的运行时结构。
- 持久化仍然回写为扁平布局，后端接口和 YAML 结构不需要跟着改。

### 2. 数据归组统一为显式 `groupId`

- 组件是否属于某个分组，只认显式 `groupId`。
- 已删除“组件刚好排在 group header 下方就自动视为同组”的兼容逻辑。

### 3. 禁止分组嵌套

- sub-grid 只接受 widget 节点。
- group 节点不能被别的 group 接收，避免出现组套组和 GridStack 销毁报错。

### 4. 补齐新增路径

- 支持从“新增视图到本分组”进入配置，再保存到目标分组。
- 普通新增组件不再使用 `y: Infinity`，改为显式计算落位，避免死循环。

### 5. 优化组内排布

- 分组内新增组件时，优先填补已有空位。
- 只有确实没有可用空位时，才落到分组底部。

### 6. 修正拖拽缩放手柄

- 缩放手柄定位回收到 GridStack item 的内容边距内。
- 样式恢复为旧版 `react-resizable` 的角标实现，避免自绘角标与旧视觉不一致。

## 主护栏

使用以下命令做分组需求主线回归验证：

```bash
cd web && pnpm run test:dashboard-groups
```

当前护栏覆盖：

- 分组 section 构建
- 折叠态过滤
- 整组拖拽预览
- 整组重排
- 组件拖入分组后的归属同步
- 删除分组头
- 空组承接
- 组内空位填充
- GridStack 布局转换和回写

静态校验建议至少执行：

```bash
cd web && pnpm exec eslint "src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardCanvas.tsx"
```

## 涉及文件

- `web/src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardCanvas.tsx`
- `web/src/app/ops-analysis/(pages)/view/dashBoard/index.tsx`
- `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewSelector.tsx`
- `web/src/app/ops-analysis/utils/dashboardGroups.ts`
- `web/src/app/ops-analysis/utils/dashboardGridStack.ts`
- `web/scripts/dashboard-groups-validation.ts`

## 维护约定

- 新增分组相关行为时，优先补到 `dashboard-groups-validation.ts`，不要只靠手工回归。
- 若未来后端需要迁移数据模型，应优先评估是否还能维持“前端运行时适配，持久化扁平回写”的方案。
- 若再出现分组拖拽异常，先检查 `dashboardCanvas.tsx` 中 root grid / sub-grid 的接收规则是否仍然是 widget-only。

## specs: 2026-06-02-ops-analysis-dashboard-grouping-design.md

## 背景

Ops Analysis 仪表盘需要支持类似 Grafana 的分组视图编排能力，但后端 `view_sets` 结构已经被多处依赖，不能为了前端交互整体改掉存储模型。

本次设计目标是在前端运行时引入更适合分组拖拽的布局能力，同时保持服务端和导入导出的顶层结构稳定。

## 目标

- 支持新增分组、分组重命名、删除分组。
- 支持将视图组件加入指定分组，并在分组内参与拖拽和缩放。
- 支持整组拖拽重排，体验贴近 Grafana。
- 支持分组折叠，折叠后只显示分组头。
- 保持现有仪表盘持久化结构不做破坏性调整。

## 非目标

- 不引入分组嵌套分组。
- 不兼容“仅靠 group header 相邻位置推断归组”的历史脏数据。
- 不改造后端接口或 YAML 顶层 schema。
- 不改动各类 widget 内部配置表单。

## 数据模型

持久化层继续使用扁平 `view_sets` 数组。

- 分组头使用 `itemType: 'group'` 标识。
- 普通组件通过显式 `groupId` 指向所属分组。
- 未分组组件显式使用 `groupId: null` 或不带 `groupId`，在前端规范化后统一按未分组处理。

这意味着：

- 分组关系以显式 `groupId` 为唯一事实来源。
- 不再根据组件在 group header 下方的相对位置隐式推断归组。

## 运行时布局策略

前端运行时采用 GridStack：

- 根网格负责未分组 block 和各分组 block 的顶层排序。
- 每个分组内部使用 sub-grid 管理组内 widget。
- 保存时再回写为扁平布局，保持外部契约不变。

## 关键交互约束

### 1. 禁止组嵌套组

sub-grid 仅接收 widget 节点，不接收 group 节点。

结果：

- 分组拖拽经过其他分组时，不会被错误吸入形成嵌套。
- 顶层拖拽始终只在“分组 block / 未分组 block”之间重排。

### 2. 分组内新增组件优先填空位

向分组新增组件时，不直接追加到整组底部，而是在当前分组内部按从上到下、从左到右寻找首个可放置空位。

结果：

- 组内存在由不同高度组件形成的空洞时，新组件会优先补洞。
- 视觉上更接近 Grafana 的紧凑排布。

### 3. 普通新增组件不再使用 Infinity 落位

新增未分组组件时，前端直接计算当前布局的下一个有效 `y` 坐标，避免布局引擎在运行时因 `Infinity` 产生异常回流或死循环。

### 4. 折叠态只保留分组头

分组折叠后：

- 画布可见布局中仅保留 group header。
- 组内 widget 继续保留在持久化布局中，不丢失位置关系。

## 关键文件

- `web/src/app/ops-analysis/utils/dashboardGroups.ts`
- `web/src/app/ops-analysis/utils/dashboardGridStack.ts`
- `web/src/app/ops-analysis/(pages)/view/dashBoard/index.tsx`
- `web/src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardCanvas.tsx`
- `web/scripts/dashboard-groups-validation.ts`

## 验证方式

当前以聚焦脚本作为主护栏：

- `cd web && pnpm run test:dashboard-groups`

该脚本覆盖的主线包括：

- 显式 `groupId` 归组
- 折叠态可见布局
- 整组拖拽预览与重排
- 组件拖入分组后的 `groupId` 同步
- 空组承接
- 组内空位填充
- GridStack 运行时布局与扁平布局 round-trip

## 预期结果

完成后，Ops Analysis 仪表盘分组能力在交互上贴近 Grafana，在数据契约上保持最小改动，并通过脚本护栏约束核心行为回归。
