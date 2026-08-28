# 运营分析画布数据组件复制

Status: implemented

## Problem Statement

仪表盘、大屏、报表编辑态只能新增或删除数据组件，不能把已配置好的组件就地复制一份。搭建者要做相近组件时只能重走选择器与配置抽屉。场景组件（networkStatusTopology 等）不应出现复制入口。

## Solution

在 Dashboard / Screen / Report 编辑态的数据组件 ⋯ 菜单中，于编辑与删除之间加入「复制」。复制当前打开 ⋯ 的那一个数据组件到同一画布：新 uuid、深拷贝 valueConfig、标题加「副本」、邻接放置。不克隆 DataSource，不改画布筛选定义，只拷贝该组件的 filterBindings，插入后走现有 filter sync。

## User Stories

1. 作为画布搭建者，我希望在编辑态把一个已配置的数据组件复制到同一画布，从而不必重新配置数据源与筛选绑定。
2. 作为画布搭建者，我希望场景组件的 ⋯ 菜单里根本没有「复制」，从而不会误操作网络状态拓扑等场景件。
3. 作为查看者或分享/内置画布使用者，我希望看不到复制入口，从而只读语义不被打开。

## Implementation Decisions

- 入口：现有 MoreActionsDropdown，紧挨编辑与删除。不新增右键菜单、Ctrl+C/V、多选或跨画布。
- 只复制打开 ⋯ 的那个组件。
- 仅数据组件。`isSceneWidgetType(sceneWidgetType || chartType)` 为真时菜单不出现「复制」（不是 disabled，也不是静默 no-op）。
- 仅编辑态。view / share / builtin 无复制入口。
- 新 uuid；深拷贝 valueConfig（含 dataSourceParams、filterBindings、tableConfig、appearance）。复用 dataSource id，不克隆 DataSource。不拷贝 runtime（rawData、loading、scheduler、live componentSwitch）。
- 不克隆画布筛选定义；只克隆该组件 bindings。插入后分别调用 `buildFiltersFromLayout` / `rebuildDraftFilters` / `syncReportFiltersFromSections`。
- 标题：有名 → `{原名} 副本`；空 → `副本`。
- Dashboard 分组：保留 groupId；优先同 y、x+1；放不下或仍重叠则走组内碰撞扫描（`insertDashboardWidgetIntoGroup`）。不把副本丢到未分组底部。
- Screen：+48,+48 px，zIndex = max+1，夹入 viewport，边缘允许与原件部分重叠；复制后 `selectedItemId` 为新组件。Dashboard / Report 不发明选中态。
- Report：新 section 插在源 section 正下方，id 唯一。
- DataSource 当前组织不可见时仍显示复制；克隆失败表现与原组件一致。不按 hasAuth 隐藏复制。
- 只脏本地草稿。无组件级撤销。复制不自动存草稿检查点。取消编辑回到上次成功保存。
- room3D、topologyMap、cardList、eventTimeline、radar 是数据组件，必须有复制。
- 拓扑 `handleNodeCopy` 只作语义参考（复制被操作的那一个）；不把 +200px / graph.select / toast 带进分析画布。

## Testing Decisions

公共接缝（vitest）：

1. Clone helper：新 id、深拷贝 valueConfig（改副本不改源）、同一 dataSource id、拷贝 filterBindings、画布 filter definitions 数量不变、标题 `{name} 副本` / 空 → `副本`。
2. Menu：编辑态数据组件 ⋯ 含「复制」；networkStatusTopology 场景菜单完全没有「复制」；view / share / builtin 没有「复制」。
3. Dashboard：分组复制保留 groupId；放置先试 x+1 同 y，再组内碰撞扫描。
4. Report：新 section 紧挨源下方；section id 唯一。
5. Screen：复制后 selectedItemId 为新组件；偏移 +48,+48；zIndex max+1。

## Non-goals

拓扑 / 架构 / networkTopology 画布；右键菜单；剪贴板；多选；跨画布；克隆 DataSource；改筛选定义；分享查询协议；组件级撤销；Dashboard/Report 选中态 chrome；widgetRegistry / DataSource / scene fetch 改写。
