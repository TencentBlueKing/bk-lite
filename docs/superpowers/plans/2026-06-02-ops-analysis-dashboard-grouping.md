# Ops Analysis 仪表盘分组实施说明

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
