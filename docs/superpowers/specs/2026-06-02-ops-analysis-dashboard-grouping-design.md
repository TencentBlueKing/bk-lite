# Ops Analysis 仪表盘分组设计

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
