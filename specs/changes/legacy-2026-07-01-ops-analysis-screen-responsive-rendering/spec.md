# Historical Superpowers change: 2026-07-01-ops-analysis-screen-responsive-rendering

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-01-ops-analysis-screen-responsive-rendering.md

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

## specs: 2026-07-01-ops-analysis-screen-responsive-rendering-design.md

## 背景

运营分析大屏目前使用固定设计画布，并通过绝对坐标渲染组件。这个基础是正确的：大屏编辑器需要稳定的设计坐标系，用户摆放好的组件不能因为浏览器窗口变化就发生布局漂移。

当前问题不在于固定坐标系本身，而在于视觉尺寸分散在画布、标题/时钟装饰层、组件外框、Ant Design 表格覆盖样式以及各类图表组件里。很多值是固定 `px`，导致标题大小、时钟位置、面板 padding、表格行高、图表标签、加载态和空态在不同设计分辨率、浏览器窗口、预览态和全屏态下表现不一致。

本设计保留固定设计坐标系，同时为大屏 `screen` 模式增加一套明确的响应式渲染契约。

## 目标

- 保持大屏布局坐标稳定。现有组件的 `x/y/w/h` 继续以设计画布单位存储。
- 大屏画布按当前内容区域等比最大化展示。
- 分离“画布适配”和“视觉密度”，避免字体和装饰层被设计分辨率意外影响。
- 响应式体系只作用于 `screen` 大屏渲染。共享 widget 如需调整，必须由明确的大屏模式信号触发。
- 让大屏预览、全屏预览和编辑态的视觉层级保持一致。
- 开发时必须启动 Storybook 做视觉跟随，覆盖不同画布比例、组件尺寸和组件状态。

## 非目标

- 不把大屏布局改成流式网页布局。
- 不改变普通仪表盘 `dashboard` 或拓扑 `topology` 的默认展示。
- 不迁移已存储的大屏坐标或组件布局数据。
- 本次不实现编辑态手动缩放功能，但设计为后续扩展预留空间。
- 本次不引入新的大屏模板系统。

## 推荐方案

采用三层渲染模型：

1. **画布适配**：保留设计坐标系，计算设计画布如何放进当前内容区域。
2. **大屏视觉密度**：为标题、时钟、背景装饰、空态、选中态、表格默认样式和面板基础样式计算全局 token。
3. **组件局部密度**：根据每个组件自身的实际显示尺寸计算局部 token，让小 KPI 卡片和大图表面板拥有合适的内部层级。

这个方案比逐个补 CSS 更稳，因为它为大屏模式建立了统一的视觉尺寸来源。

## 画布适配

画布必须按照限制边等比适配：

```ts
fitScale = Math.min(
  contentWidth / designWidth,
  contentHeight / designHeight,
);
```

实际渲染尺寸为：

```ts
renderedWidth = designWidth * fitScale;
renderedHeight = designHeight * fitScale;
```

舞台在工作区中居中显示。多余空间保留为深色工作区背景。画布不能被拉伸、裁切，也不能只按宽度单边硬算。

现有组件绝对坐标继续使用设计单位。画布根节点保持 `width: designWidth`、`height: designHeight`，并通过 `transform: scale(fitScale)` 展示。

## 大屏视觉密度

`fitScale` 不等于视觉密度。`fitScale` 回答的是“设计画布如何放进容器”；视觉密度回答的是“最终肉眼看到的标题、时钟、面板和文字应该多大”。

画布需要计算并暴露这些 CSS 变量：

```css
--screen-fit-scale
--screen-density
--screen-ui-scale
```

`--screen-density` 基于实际渲染出来的画布尺寸计算，并限制在可读范围内。它应该响应真实显示尺寸，而不是只看配置里的设计宽度。

`--screen-ui-scale` 用来抵消外层画布 transform：

```ts
screenUiScale = screenDensity / fitScale;
```

大屏装饰层使用类似写法：

```css
font-size: calc(32px * var(--screen-ui-scale));
```

画布整体再经过 `fitScale` 缩放后，最终肉眼看到的字号由 `screenDensity` 控制，而不是被设计分辨率和 transform 重复影响。

具体 clamp 数值应保持保守。目标是在很小的预览窗口里不让文字过小，在超大屏里不让文字失控，同时允许更大的实际画布拥有更舒展的视觉表现。

## 组件局部密度

每个大屏组件外框需要根据自身实际显示尺寸暴露局部 token：

```css
--screen-widget-scale
--screen-widget-title-size
--screen-widget-body-size
--screen-widget-padding
--screen-widget-control-size
```

组件密度同时考虑宽度和高度：

```ts
widgetDensity = clamp(
  Math.min(renderedWidgetWidth / baseWidgetWidth, renderedWidgetHeight / baseWidgetHeight),
  minWidgetDensity,
  maxWidgetDensity,
);
```

写入未缩放画布内部的值同样需要抵消 `fitScale`：

```ts
widgetUiScale = widgetDensity / fitScale;
```

这样小 KPI 卡片会保持紧凑，大图表面板会更舒展，但不会改变用户摆放好的坐标和尺寸。

## 组件职责

### Screen Canvas

- 使用 `ResizeObserver` 测量可用工作区尺寸。
- 同时基于宽度和高度计算 `fitScale`。
- 居中显示实际渲染舞台。
- 在大屏画布根节点发布全局 CSS 变量。
- 保持设计尺寸和组件坐标不变。
- 背景、标题、时钟、空态、分辨率标识和编辑态轮廓都从大屏 token 取值。

### Screen Widget Frame

- 测量自身实际渲染区域，或从画布层接收布局度量。
- 发布组件级 CSS 变量。
- header 高度、标题字号、padding、信号线、角标、操作按钮和 resize handle 都从变量取值。
- 编辑控件需要保持可读，但视觉上应弱于展示内容。

### Shared Widgets

共享 widget 只能在明确的大屏模式下调整。有效信号包括 `chartThemeMode: "screen-dark"`，以及后续如果引入的显式 screen render context。

大屏模式下需要适配：

- 单值指标：保留现有内容自适应逻辑，但 min/max 字号应来自大屏组件密度。
- 折线图和柱状图：缩放坐标轴标签、图例、grid 间距、tooltip 文字、线宽和 symbol 大小。
- 饼图：缩放标签文字、图例间距、中心文字和 tooltip。
- 仪表盘：缩放刻度标签、详情文字、进度宽度和分割线尺寸。
- TopN：缩放标签文字、条形高度、行间距和值文字。
- 表格和事件表：缩放表头/正文字号、行高、单元格 padding、分页文字、空态和加载态。
- 网络状态拓扑：保留图形 fitView 行为，但在大屏模式下缩放覆盖层、节点标签、图例和类工具条信息。

普通 dashboard 渲染继续使用现有 dashboard 主题行为。

## 数据流

1. Screen 加载 `viewSets.viewport`、`viewSets.items` 和 `viewSets.decorations`。
2. Screen canvas 测量工作区内容区域。
3. Canvas 计算 `fitScale`、实际渲染尺寸、`screenDensity` 和 `screenUiScale`。
4. Canvas 渲染设计尺寸的大屏根节点，并设置 `transform: scale(fitScale)`。
5. 大屏根节点暴露装饰层所需的 CSS 变量。
6. 每个 widget frame 计算或接收组件密度，并暴露组件级 CSS 变量。
7. CSS 无法覆盖的场景，由 `ScreenWidgetRenderer` 将大屏模式上下文传给 `WidgetWrapper` 和共享 widget。
8. ECharts 类 widget 在大屏模式下根据 screen/widget 度量生成 option。

## 错误处理与降级

- 如果工作区暂时无法测量尺寸，按设计比例渲染一个占位舞台。
- 如果 viewport 宽高非法，继续使用 normalize 后的默认 viewport。
- 如果 `fitScale` 为 `0` 或非有限数字，计算时回退为 `1`，避免生成非法 CSS。
- 如果组件测量不可用，组件密度回退为 `1`。
- 如果组件过小导致内容空间不足，优先采用截断、降低 padding 和紧凑密度，避免内容溢出。

## Storybook 视觉跟随

实现期间需要启动 Storybook，并验证大屏模式场景。最低覆盖：

- `1920x1080`、`1366x768`、`3840x2160` 的空画布。
- 标题 + 时钟。
- 预览态和编辑态。
- 小尺寸和大尺寸 KPI 卡片。
- 折线图、柱状图、饼图、仪表盘、TopN、表格、事件表和网络拓扑组件。
- loading、empty、error、selected、resizing 状态。
- 触发宽度受限和高度受限的容器尺寸。

视觉验收标准是：不同场景下标题、时钟、面板层级、表格可读性、图表标签和编辑态手柄都保持比例合理。

## 实现备注

- 引入一个小型 screen metrics 工具，避免把公式散落在 JSX 里。
- DOM 装饰和面板样式优先使用 CSS 变量。
- ECharts option 里使用显式数值，因为 ECharts option 不能稳定读取 CSS 变量。
- 所有大屏样式改动都必须通过 screen-mode class 或 screen-mode config 触发。
- 如果 `screenCanvas.tsx` 内联样式块继续膨胀，应将大屏样式拆出，降低文件复杂度。

## 验收标准

- 画布适配同时使用可用宽度和高度，并保持配置比例。
- 标题、时钟、分辨率标识、空态和背景装饰使用大屏级响应式 token。
- 组件外框的 header、标题、padding、操作按钮、角标和 resize handle 使用组件级响应式 token。
- 大屏模式下的图表和表格从 screen/widget 度量缩放文字和间距。
- 普通 dashboard 和 topology 默认视图不发生视觉变化。
- 开发过程中使用 Storybook 检查要求覆盖的大屏场景。
- 不需要迁移已存储的大屏布局数据。
