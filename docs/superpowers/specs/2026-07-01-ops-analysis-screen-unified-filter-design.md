# 运营分析大屏统一筛选设计

## 背景

运营分析现在有三类画布视图：仪表盘、拓扑和大屏。仪表盘和拓扑已经支持页面级查询控制，包括统一筛选和命名空间选择。大屏是在后续拆分出来的视图，目前保留了组件级“筛选联动”的配置入口，但页面本身没有维护统一筛选定义、筛选值和命名空间上下文，也没有把这些上下文传给组件取数层。

这会形成一个不一致的状态：大屏组件配置抽屉里可以看到“筛选联动”，但运行时 `ScreenWidgetRenderer` 传给 `WidgetWrapper` 的始终是空筛选定义和空筛选值，所以大屏查看态和预览态实际上无法应用统一筛选。

## 目标

- 让大屏接入与仪表盘、拓扑一致的统一筛选模型。
- 复用现有统一筛选组件和数据转换逻辑。
- 将命名空间作为与统一筛选并列的页面级查询上下文处理。
- 全屏播放态保持纯展示，不显示筛选条和配置入口。
- 避免本轮对仪表盘、拓扑做大规模状态重构；只抽取稳定的公共查询工具，让大屏直接接入。
- 兼容没有筛选配置的旧大屏。

## 非目标

- 不创建大屏专属筛选模型，也不做大屏专属筛选条。
- 不持久化运行时筛选值和已选命名空间，除非后续产品明确要求记住用户上次筛选。
- 不在本次变更中重做仪表盘或拓扑的查询交互。
- 不在全屏播放态显示统一筛选。
- 不把组件位置调整、画布操作体验优化纳入本次筛选工作。

## 推荐方案

复用现有统一筛选模型，将大屏补齐为正式消费者。

大屏 `view_sets` 增加筛选定义：

```ts
interface ScreenViewSets {
  viewport: ScreenViewportConfig;
  items: ScreenItem[];
  decorations: ScreenDecorationsConfig;
  filters?: UnifiedFilterDefinition[];
}
```

运行时状态按页面查询上下文处理：

```ts
type OpsAnalysisQueryContext = {
  filterDefinitions: UnifiedFilterDefinition[];
  draftFilterValues: Record<string, FilterValue>;
  appliedFilterValues: Record<string, FilterValue>;
  namespaceDraftId?: number;
  appliedNamespaceId?: number;
  filterSearchVersion: number;
  namespaceSearchVersion: number;
};
```

`filters` 只保存筛选定义。草稿值、已应用值、已选命名空间都留在页面状态里，因为它们表示当前查询会话，不属于大屏设计本身。

## 公共逻辑

本次应抽一个小而稳定的公共查询层，而不是把仪表盘页面里的状态代码复制到大屏。

公共层包含这些与页面类型无关的能力：

- 规范化持久化的筛选定义，兼容当前数组结构和可能存在的旧结构。
- 根据筛选定义同步筛选值：
  - 移除已删除筛选项对应的值；
  - 给缺失的启用筛选项填充默认值；
  - 在查询时重新计算相对时间范围。
- 根据画布使用的数据源解析有效命名空间选项和兜底命名空间。
- 提供轻量 `useOpsAnalysisQueryState`：
  - 管理草稿筛选值；
  - 管理已应用筛选值；
  - 管理命名空间草稿值和已应用值；
  - 管理筛选、命名空间的搜索版本号；
  - 提供 apply/reset 类帮助函数。

仪表盘和拓扑本轮不做深度迁移。它们可以引用新的纯函数来替换明显重复的逻辑，但各自页面里的布局、分组、拓扑节点、局部刷新等编排逻辑保持不动。

## 大屏交互

普通查看态和编辑态满足以下任一条件时显示统一筛选条：

- 存在至少一个启用的统一筛选定义；
- 存在可展示的命名空间选择器；
- 当前处于编辑态，用户可以配置筛选。

筛选条复用 `UnifiedFilterBar`，命名空间选择器作为 prefix content 传入，保持和仪表盘、拓扑一致。

大屏编辑态需要提供统一筛选配置入口。配置弹窗复用 `UnifiedFilterConfigModal`，并扫描当前大屏组件使用的数据源参数来生成可绑定的筛选定义。

组件配置抽屉需要接收当前查询上下文：

- `filterDefinitions`
- `unifiedFilterValues`
- `builtinNamespaceId`

这样现有 `FilterBindingPanel` 在大屏组件里也能正确工作，不需要做大屏专属配置抽屉。

全屏播放态不渲染筛选条、命名空间选择器和筛选配置入口。进入全屏后使用普通页面中已经 applied 的筛选值和命名空间。

## 取数链路

大屏取数链路补齐为：

```txt
Screen 页面 query state
  -> ScreenCanvas
    -> ScreenWidgetRenderer
      -> WidgetWrapper
        -> widgetDataTransform/buildDataSourceParams
          -> 数据源请求参数
```

`ScreenCanvas` 只负责透传查询上下文，不解释筛选定义或命名空间规则。

`ScreenWidgetRenderer` 不再传空筛选定义和空筛选值，而是传入：

- `filterSearchVersion`
- `namespaceSearchVersion`
- `unifiedFilterValues={appliedFilterValues}`
- `filterDefinitions={filterDefinitions}`
- `builtinNamespaceId={appliedNamespaceId}`

手动刷新大屏时，使用当前已应用查询上下文刷新全部组件。

筛选搜索时，更新已应用筛选值，并递增 `filterSearchVersion`。

命名空间搜索时，更新已应用命名空间，并递增 `namespaceSearchVersion`。

如果筛选和命名空间同时变化，可以同时递增两个版本号，也可以由组合 helper 统一更新，但对 `WidgetWrapper` 暴露的 props 仍保持现有形态。

## 编辑、保存和取消

大屏继续保留当前已有的 saved、view、draft 三类状态。

进入编辑态时：

- 将当前 `viewSets` 复制到 `draftViewSets`；
- 记录进入编辑前的筛选定义；
- 记录取消时需要恢复的草稿筛选值、已应用筛选值和命名空间状态。

新增、编辑或删除大屏组件时：

- 更新 `draftViewSets.items`；
- 重新扫描组件数据源参数；
- 重建 `draftViewSets.filters`；
- 根据重建后的定义同步筛选值；
- 清理无效组件筛选绑定，例如筛选定义不存在、参数不存在或类型不匹配。

取消编辑时：

- 从上次保存状态恢复 `draftViewSets`；
- 恢复进入编辑前的筛选定义和筛选值；
- 清理已选中组件、正在配置组件等编辑态状态。

保存时：

- 持久化 `draftViewSets`，包含 `filters`；
- 将保存后的状态同步回运行态；
- 让运行态已应用筛选值按保存后的筛选定义重新同步；
- 命名空间仍作为运行态状态，不写入 `view_sets`。

## 命名空间规则

命名空间是页面级查询上下文，不是统一筛选定义。

大屏命名空间选项从当前大屏组件使用的数据源中推导，语义与仪表盘、拓扑保持一致。如果没有组件数据源声明 namespaces，则不展示命名空间选择器，也不向组件请求传命名空间参数。

如果存在命名空间选项且尚未应用命名空间，大屏默认使用第一个有效命名空间。如果组件编辑后当前命名空间失效，则回退到第一个可用命名空间；如果没有可用命名空间，则清空命名空间状态。

## 兼容性

旧大屏记录没有 `view_sets.filters` 时，统一规范化为空筛选定义列表。

仪表盘和拓扑现有数据不需要迁移。

内置 YAML 的大屏可以在本次之后包含 `filters`，但不是必须包含。YAML 不保存运行时筛选值，也不保存已选命名空间。

## 验证范围

实现后需要在 `/ops-analysis` 手动验证一个包含以下组件的大屏：

- 数据源包含时间筛选参数的组件；
- 数据源包含字符串筛选参数的组件；
- 数据源绑定了一个或多个命名空间的组件；
- 没有筛选绑定的组件。

预期行为：

- 普通大屏查看态在存在筛选或命名空间时显示筛选条；
- 全屏播放态隐藏筛选条；
- 筛选搜索刷新启用了筛选绑定的组件；
- 命名空间搜索刷新依赖命名空间的数据源组件；
- 手动刷新刷新全部组件；
- 组件配置抽屉能基于大屏筛选定义显示筛选联动选项；
- 取消编辑能恢复之前的筛选定义和组件绑定；
- 保存编辑能持久化 `view_sets.filters`；
- 没有筛选配置的旧大屏仍正常渲染。

小样式调整不需要额外加测试；如果实现触及共享纯函数，建议为筛选值同步、筛选定义规范化和命名空间兜底逻辑补轻量单测。

## 风险

存储结构本身风险较低，`filters` 是可选字段，旧大屏可以干净规范化。主要风险是状态同步：

- 筛选定义需要与组件数据源参数保持一致；
- 筛选定义变化时需要清理无效组件绑定；
- 草稿值和已应用值不能混用；
- 全屏态必须使用已应用查询值，但不能渲染控制条。

只抽取稳定公共查询工具，不深度重构仪表盘和拓扑状态结构时，本次风险维持在中等偏低。
