# 运营分析大屏响应式渲染 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为运营分析 `screen` 大屏建立清晰的响应式渲染体系，让画布适配、标题/时钟、组件外框、表格和常用图表在不同内容区域与设计分辨率下保持专业一致。

**Architecture:** 保留固定设计坐标系，使用 `fitScale = min(contentWidth / designWidth, contentHeight / designHeight)` 适配画布。新增 screen metrics 工具统一输出 `fitScale`、`screenDensity`、`screenUiScale`，Screen Canvas 发布全局 CSS 变量，Screen Widget Frame 发布组件级 CSS 变量，shared widgets 只在 `screen-dark` 或显式 screen context 下读取大屏度量。

**Tech Stack:** Next.js 16、React 19、TypeScript、Ant Design、ECharts、Storybook。

---

## 文件结构

- Create: `web/src/app/ops-analysis/(pages)/view/screen/utils/metrics.ts`
  - 职责：集中计算画布适配、全局大屏密度、组件局部密度和 clamp 工具。
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`
  - 职责：使用 metrics 工具计算 `fitScale` 和 screen CSS variables；清理分散公式；让画布按宽高限制边最大化。
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame.tsx`
  - 职责：接收或计算组件级密度，发布 widget CSS variables。
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetRenderer.tsx`
  - 职责：向 shared widgets 传递 screen render context。
- Modify: `web/src/app/ops-analysis/components/widgetDataRenderer.tsx`
  - 职责：透传可选 screen render context，不改变普通 dashboard 行为。
- Modify: `web/src/app/ops-analysis/components/widgetRenderer.tsx`
  - 职责：把 screen render context 传给具体 widget 组件。
- Modify: `web/src/app/ops-analysis/types/dashBoard.ts`
  - 职责：补充 shared widgets 可选 screen render context 类型。
- Modify: `web/src/app/ops-analysis/components/widgets/comSingle.tsx`
  - 职责：单值指标在大屏模式下读取局部密度，优化字号 min/max。
- Modify: `web/src/app/ops-analysis/components/widgets/comLine.tsx`
  - 职责：折线图在大屏模式下缩放坐标轴、图例、grid、tooltip、线宽和 symbol。
- Modify: `web/src/app/ops-analysis/components/widgets/comBar.tsx`
  - 职责：柱状图在大屏模式下缩放坐标轴、图例、grid、tooltip 和柱形相关字号。
- Modify: `web/src/app/ops-analysis/components/widgets/comPie.tsx`
  - 职责：饼图在大屏模式下缩放图例、label、中心文字和 tooltip。
- Modify: `web/src/app/ops-analysis/components/widgets/comGauge.tsx`
  - 职责：仪表盘在大屏模式下缩放刻度、详情文字、进度宽度。
- Modify: `web/src/app/ops-analysis/components/widgets/comTopN.tsx`
  - 职责：TopN 在大屏模式下缩放行高、间距、标签和值文字。
- Modify: `web/src/app/ops-analysis/components/widgets/comTable.tsx`
  - 职责：表格在大屏模式下用 CSS variables 控制字号、行高和 padding。
- Modify: `web/src/app/ops-analysis/components/widgets/comTable.module.scss`
  - 职责：承接表格大屏 CSS variables。
- Modify or Create: `web/src/stories/ops-analysis-screen-responsive.stories.tsx`
  - 职责：提供大屏空画布、标题时钟、不同尺寸组件、编辑态/预览态等视觉跟随场景。

## 执行策略

- 不做阶段性提交。保持 spec、plan 和实现代码在工作区，最终由用户确认后一起提交。
- 小样式点不加单元测试；核心纯函数 `metrics.ts` 如实现简单，可用类型检查和 Storybook 视觉验证覆盖。
- 实现期间启动 Storybook：`cd web && pnpm storybook`。
- 每个任务完成后至少运行 `git diff --check`；最终运行 TypeScript 检查或说明无法运行的原因。

---

### Task 1: 新增 screen metrics 工具

**Files:**
- Create: `web/src/app/ops-analysis/(pages)/view/screen/utils/metrics.ts`

- [ ] **Step 1: 创建 metrics 工具**

实现以下函数：

```ts
export interface ScreenFitInput {
  contentWidth: number;
  contentHeight: number;
  designWidth: number;
  designHeight: number;
}

export interface ScreenFitMetrics {
  fitScale: number;
  renderedWidth: number;
  renderedHeight: number;
}

export interface ScreenVisualMetrics extends ScreenFitMetrics {
  screenDensity: number;
  screenUiScale: number;
}

export interface WidgetVisualMetrics {
  widgetDensity: number;
  widgetUiScale: number;
}

export const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

const safeNumber = (value: number, fallback: number) =>
  Number.isFinite(value) && value > 0 ? value : fallback;

export const calculateScreenFitMetrics = ({
  contentWidth,
  contentHeight,
  designWidth,
  designHeight,
}: ScreenFitInput): ScreenFitMetrics => {
  const safeDesignWidth = safeNumber(designWidth, 1920);
  const safeDesignHeight = safeNumber(designHeight, 1080);
  const safeContentWidth = Math.max(contentWidth, 0);
  const safeContentHeight = Math.max(contentHeight, 0);

  if (!safeContentWidth || !safeContentHeight) {
    return {
      fitScale: 1,
      renderedWidth: safeDesignWidth,
      renderedHeight: safeDesignHeight,
    };
  }

  const fitScale = Math.max(
    Math.min(
      safeContentWidth / safeDesignWidth,
      safeContentHeight / safeDesignHeight,
    ),
    0.0001,
  );

  return {
    fitScale,
    renderedWidth: Math.floor(safeDesignWidth * fitScale),
    renderedHeight: Math.floor(safeDesignHeight * fitScale),
  };
};

export const calculateScreenVisualMetrics = (
  input: ScreenFitInput,
): ScreenVisualMetrics => {
  const fit = calculateScreenFitMetrics(input);
  const densityBase = Math.min(fit.renderedWidth / 1440, fit.renderedHeight / 810);
  const screenDensity = clamp(densityBase, 0.72, 1.16);

  return {
    ...fit,
    screenDensity,
    screenUiScale: screenDensity / fit.fitScale,
  };
};

export const calculateWidgetVisualMetrics = ({
  renderedWidth,
  renderedHeight,
  fitScale,
  baseWidth = 420,
  baseHeight = 260,
}: {
  renderedWidth: number;
  renderedHeight: number;
  fitScale: number;
  baseWidth?: number;
  baseHeight?: number;
}): WidgetVisualMetrics => {
  const densityBase = Math.min(
    safeNumber(renderedWidth, baseWidth) / baseWidth,
    safeNumber(renderedHeight, baseHeight) / baseHeight,
  );
  const widgetDensity = clamp(densityBase, 0.76, 1.18);
  const safeFitScale = Math.max(fitScale, 0.0001);

  return {
    widgetDensity,
    widgetUiScale: widgetDensity / safeFitScale,
  };
};
```

- [ ] **Step 2: 运行格式检查**

Run: `git diff --check -- web/src/app/ops-analysis/\\(pages\\)/view/screen/utils/metrics.ts`

Expected: 无输出，退出码 0。

---

### Task 2: 接入画布适配和全局大屏 CSS 变量

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`

- [ ] **Step 1: 替换 canvasSize/scale 计算**

在 `screenCanvas.tsx` 中导入：

```ts
import {
  calculateScreenVisualMetrics,
} from "../utils/metrics";
```

用 `calculateScreenVisualMetrics` 计算：

```ts
const screenMetrics = useMemo(() => {
  const padding = fullscreen ? 32 : 32;
  return calculateScreenVisualMetrics({
    contentWidth: Math.max(containerSize.width - padding, 0),
    contentHeight: Math.max(containerSize.height - padding, 0),
    designWidth: width,
    designHeight: height,
  });
}, [containerSize.height, containerSize.width, fullscreen, height, width]);

const scale = screenMetrics.fitScale;
```

舞台尺寸使用：

```tsx
style={{
  width: screenMetrics.renderedWidth,
  height: screenMetrics.renderedHeight,
}}
```

画布根节点发布：

```tsx
style={{
  width,
  height,
  transform: `scale(${scale})`,
  "--screen-fit-scale": screenMetrics.fitScale,
  "--screen-density": screenMetrics.screenDensity,
  "--screen-ui-scale": screenMetrics.screenUiScale,
} as React.CSSProperties}
```

- [ ] **Step 2: 替换旧 `--screen-chrome-scale`**

把装饰层 CSS 中的 `var(--screen-chrome-scale)` 替换为 `var(--screen-ui-scale)`。

- [ ] **Step 3: 运行检查**

Run: `git diff --check -- web/src/app/ops-analysis/\\(pages\\)/view/screen/components/screenCanvas.tsx`

Expected: 无输出，退出码 0。

---

### Task 3: 组件外框接入局部密度

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetRenderer.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`

- [ ] **Step 1: 为 ScreenWidgetFrame 增加 metrics props**

增加 props：

```ts
interface ScreenWidgetFrameProps extends ScreenWidgetFrameOptions {
  item: ScreenWidgetItem;
  fitScale?: number;
  onConfigure?: () => void;
  onDelete?: () => void;
  children: React.ReactNode;
}
```

根据 `item.w/h` 和 `fitScale` 计算局部变量：

```ts
const renderedWidth = item.w * (fitScale || 1);
const renderedHeight = item.h * (fitScale || 1);
const widgetMetrics = calculateWidgetVisualMetrics({
  renderedWidth,
  renderedHeight,
  fitScale: fitScale || 1,
});
```

将变量设置到 section：

```tsx
style={{
  "--screen-widget-scale": widgetMetrics.widgetDensity,
  "--screen-widget-ui-scale": widgetMetrics.widgetUiScale,
} as React.CSSProperties}
```

- [ ] **Step 2: 透传 fitScale**

`ScreenCanvas` 调用 `ScreenWidgetRenderer` 时传入 `fitScale={scale}`；`ScreenWidgetRenderer` 再传给 `ScreenWidgetFrame`。

- [ ] **Step 3: 用变量替换 frame 固定尺寸**

优先替换 header 高度、标题字号、padding、按钮尺寸、resize handle 尺寸：

```css
height: calc(82px * var(--screen-widget-ui-scale));
padding: 0 calc(34px * var(--screen-widget-ui-scale));
font-size: calc(34px * var(--screen-widget-ui-scale));
```

- [ ] **Step 4: 运行检查**

Run: `git diff --check -- web/src/app/ops-analysis/\\(pages\\)/view/screen/components`

Expected: 无输出，退出码 0。

---

### Task 4: 透传 screen render context 到 shared widgets

**Files:**
- Modify: `web/src/app/ops-analysis/types/dashBoard.ts`
- Modify: `web/src/app/ops-analysis/components/widgetDataRenderer.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetRenderer.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetRenderer.tsx`

- [ ] **Step 1: 增加类型**

在 `ValueConfig` 附近增加可选类型，或在合适位置导出：

```ts
export interface ScreenRenderContext {
  enabled: boolean;
  fitScale: number;
  screenDensity: number;
  screenUiScale: number;
  widgetDensity: number;
  widgetUiScale: number;
}
```

Widget props 增加可选：

```ts
screenRenderContext?: ScreenRenderContext;
```

- [ ] **Step 2: WidgetWrapper 和 WidgetRenderer 透传**

`WidgetWrapperProps`、`WidgetRendererProps` 添加 `screenRenderContext?: ScreenRenderContext`，渲染具体组件时传入。

- [ ] **Step 3: ScreenWidgetRenderer 构建 context**

根据 `fitScale` 和 item 尺寸构建：

```ts
const widgetMetrics = calculateWidgetVisualMetrics({
  renderedWidth: item.w * fitScale,
  renderedHeight: item.h * fitScale,
  fitScale,
});

const screenRenderContext = {
  enabled: true,
  fitScale,
  screenDensity,
  screenUiScale,
  widgetDensity: widgetMetrics.widgetDensity,
  widgetUiScale: widgetMetrics.widgetUiScale,
};
```

- [ ] **Step 4: 运行类型相关检查**

Run: `git diff --check -- web/src/app/ops-analysis/types/dashBoard.ts web/src/app/ops-analysis/components/widgetDataRenderer.tsx web/src/app/ops-analysis/components/widgetRenderer.tsx`

Expected: 无输出，退出码 0。

---

### Task 5: 常用图表接入大屏度量

**Files:**
- Modify: `web/src/app/ops-analysis/components/widgets/comSingle.tsx`
- Modify: `web/src/app/ops-analysis/components/widgets/comLine.tsx`
- Modify: `web/src/app/ops-analysis/components/widgets/comBar.tsx`
- Modify: `web/src/app/ops-analysis/components/widgets/comPie.tsx`
- Modify: `web/src/app/ops-analysis/components/widgets/comGauge.tsx`
- Modify: `web/src/app/ops-analysis/components/widgets/comTopN.tsx`

- [ ] **Step 1: 为 widget props 增加 screenRenderContext**

每个组件 props 添加：

```ts
screenRenderContext?: ScreenRenderContext;
```

判断大屏模式：

```ts
const isScreenMode =
  config?.chartThemeMode === 'screen-dark' && screenRenderContext?.enabled;
const widgetScale = isScreenMode ? screenRenderContext.widgetDensity : 1;
```

- [ ] **Step 2: 抽取局部 scale helper**

在每个文件内先用轻量函数，避免过度抽象：

```ts
const scaleMetric = (value: number, scale = 1) =>
  Math.round(value * scale);
```

- [ ] **Step 3: ECharts option 使用 screen scale**

在 `comLine`、`comBar`、`comPie`、`comGauge` 中，把 screen 模式下的字号和间距改成：

```ts
fontSize: scaleMetric(12, widgetScale)
```

对 `grid`、`legend.itemWidth`、`legend.itemGap`、`tooltip.textStyle.fontSize`、`lineStyle.width` 等同样处理。

- [ ] **Step 4: DOM 型组件使用 screen scale**

`comSingle` 和 `comTopN` 中使用 `widgetScale` 调整 min/max 字号、行高和间距，保留已有内容自适应逻辑。

- [ ] **Step 5: 运行检查**

Run: `git diff --check -- web/src/app/ops-analysis/components/widgets/comSingle.tsx web/src/app/ops-analysis/components/widgets/comLine.tsx web/src/app/ops-analysis/components/widgets/comBar.tsx web/src/app/ops-analysis/components/widgets/comPie.tsx web/src/app/ops-analysis/components/widgets/comGauge.tsx web/src/app/ops-analysis/components/widgets/comTopN.tsx`

Expected: 无输出，退出码 0。

---

### Task 6: 表格和事件表大屏样式

**Files:**
- Modify: `web/src/app/ops-analysis/components/widgets/comTable.tsx`
- Modify: `web/src/app/ops-analysis/components/widgets/comTable.module.scss`
- Modify: `web/src/app/ops-analysis/components/widgets/eventTable/eventTable.tsx`

- [ ] **Step 1: comTable 注入 CSS variables**

在 screen dark style 中加入：

```ts
'--ops-screen-table-font-size': `${Math.round(20 * widgetScale)}px`,
'--ops-screen-table-header-font-size': `${Math.round(22 * widgetScale)}px`,
'--ops-screen-table-cell-padding-y': `${Math.round(10 * widgetScale)}px`,
'--ops-screen-table-cell-padding-x': `${Math.round(14 * widgetScale)}px`,
```

- [ ] **Step 2: SCSS 使用变量**

在 `.screenDarkTable` 中替换固定值：

```scss
font-size: var(--ops-screen-table-font-size, 14px);
padding: var(--ops-screen-table-cell-padding-y, 8px) var(--ops-screen-table-cell-padding-x, 10px);
```

- [ ] **Step 3: eventTable 同步 screen context**

事件表组件如果复用 AntD Table，同样接收 `screenRenderContext`，并只在 screen mode 下设置变量或 class。

- [ ] **Step 4: 运行检查**

Run: `git diff --check -- web/src/app/ops-analysis/components/widgets/comTable.tsx web/src/app/ops-analysis/components/widgets/comTable.module.scss web/src/app/ops-analysis/components/widgets/eventTable/eventTable.tsx`

Expected: 无输出，退出码 0。

---

### Task 7: Storybook 视觉跟随场景

**Files:**
- Create or Modify: `web/src/stories/ops-analysis-screen-responsive.stories.tsx`

- [ ] **Step 1: 创建 screen responsive story**

提供最少这些 stories：

```ts
export const Empty1920 = {};
export const Empty3840 = {};
export const TitleClock = {};
export const MixedWidgetsPreview = {};
export const EditSelected = {};
```

每个 story 使用固定容器尺寸包住 screen canvas，模拟宽度受限和高度受限。

- [ ] **Step 2: 启动 Storybook**

Run: `cd web && pnpm storybook`

Expected: Storybook 在 `http://localhost:6006` 可访问。

- [ ] **Step 3: 视觉检查**

检查：

- 标题居中且不同设计分辨率下视觉大小一致。
- 时钟位置和大小稳定。
- 小 KPI 不被 header/padding 挤爆。
- 大图表标签可读。
- 表格行高和字号在大屏模式下不显得过小。
- 编辑态手柄可用但不抢视觉。

---

### Task 8: 最终验证

**Files:**
- All touched files.

- [ ] **Step 1: 空白检查**

Run: `git diff --check`

Expected: 无输出，退出码 0。

- [ ] **Step 2: 类型检查**

Run: `cd web && pnpm type-check`

Expected: PASS。若仓库已有无关类型错误，记录首个无关错误并说明。

- [ ] **Step 3: Storybook 最终视觉确认**

Run: `cd web && pnpm storybook`

Expected: 视觉场景可访问，核心大屏展示无明显文字错位、重叠、过小、过大或拉伸。

- [ ] **Step 4: 不提交**

按用户要求，本轮不做单独提交。最终由用户确认后，将 spec、plan 和实现代码一起提交。
