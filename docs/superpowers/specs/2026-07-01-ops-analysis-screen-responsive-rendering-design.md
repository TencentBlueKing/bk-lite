# 运营分析大屏响应式渲染设计

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
