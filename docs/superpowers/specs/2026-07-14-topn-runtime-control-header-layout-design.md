# TopN 组件内切换控件右上角布局设计

## 背景

当前 TopN 的运行时维度切换控件独占标题下方一行，占用排行榜内容区域。目标是将控件移动到 Widget 标题栏右上角，与标题处于同一行。

## 交互与布局

- 标题位于标题行左侧，运行时维度 Segmented 位于右侧。
- 标题容器使用 `min-width: 0`，空间不足时显示省略号。
- Segmented 不换行、不下沉到内容区，并保持右对齐。
- 控件区域设置最大可用宽度；极窄 Widget 中由控件容器提供横向滚动，避免撑破 Widget。
- 标题栏位于内容状态分支之外，因此加载、错误、空数据和正常排行时均保持可见。
- 没有合法 `runtimeParamControl` 的历史 TopN 只显示原有标题，不出现空白控件区域。

## 组件边界

- Dashboard 的 Widget 标题由外层画布渲染，运行时状态由 `WidgetWrapper` 管理；两者通过一个仅承载 DOM 目标的标题栏插槽连接。
- `WidgetWrapper` 使用 React Portal 把同一份受控 Segmented 渲染到标题栏，不提升或复制运行时状态。
- `ComTopN` 在存在标题栏插槽时不再渲染内容区控件；在没有该插槽的其他容器中保留现有内联降级。
- 仅 Dashboard Widget 卡片增加标题栏插槽，不改造其他 Widget 的标题语义。
- 不修改运行时参数配置协议、请求参数、缓存签名、实例状态或后端数据结构。
- Segmented 的 options、当前值和回调仍使用现有运行时参数能力。
- 排行榜字段、排序、数值、进度条和 `onReady` 语义保持不变。

## 验证

- 定向合约测试锁定 Dashboard 标题行包含 Portal 目标，`WidgetWrapper` 使用该目标，且 `ComTopN` 在目标存在时不重复渲染控件。
- 锁定标题具有截断能力，控件区域右对齐且可横向滚动。
- 锁定 loading、error、empty、rows 四种内容状态共用同一标题栏。
- Storybook 场景继续覆盖三项长文案和窄 Widget，供环境恢复后人工确认。
- 运行现有 TopN runtime parameter 定向测试和聚焦类型/静态检查。

## 非目标

- 不把 Segmented 改成下拉框。
- 不让控件换行到标题下方。
- 不调整其他 Widget 的通用标题栏。
- 不修改组件配置侧栏或数据源协议。
