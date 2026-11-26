# ITSM 流程设计

Status: ready

## Problem Statement

流程设计器的顶栏占掉画布高度，节点属性曾经用覆盖抽屉，决策表又和流程列表挤在同一组切换里。设计人分不清这里是在画流程，还是在维护规则。

## Solution

流程管理只保留流程列表和流程设计。设计器顶栏固定，左中右三栏各自滚动，节点属性留在右栏。决策表改到规则与时效。

## User Stories

1. As a 流程设计人, I want the header to stay fixed and the canvas to use the remaining height, so that the drawing area is not pushed down by empty margin.
2. As a 流程设计人, I want the palette, canvas, and property column to scroll independently and collapse with the same round button, so that a long node list does not scroll the canvas away.
3. As a 流程设计人, I want node properties in the right column, so that opening a node does not cover the canvas with a drawer.
4. As a 流程设计人, I want 决策表 to live with 规则与时效, so that 流程管理 only keeps the flow list and the designer.

## Implementation Decisions

- 流程设计器是三栏：节点、画布、属性。属性不是覆盖抽屉。
- 顶栏包含返回、版本、预览、保存、发布，固定在内容区顶部。
- 左右收起按钮外观一致，只是箭头方向不同。
- 流程管理只剩流程设计这一项可见子菜单时，不再显示切换条。
- 旧的流程管理决策表地址转到规则与时效下的决策表。
- 流程图继续使用现有流程图组件，不引入另一套 BPMN 设计器。
- 通知、决策、知识发布、自动派单和子流程在画布上是独立节点；运行时如何走完见工单规格。

## Testing Decisions

- 流程编译用现有 BPMN 构建测试。节点别名和默认分支在发布前校验。
- 菜单只断言流程管理下不再把决策表当作可见子项，规则与时效下可以打开决策表。

## Out of Scope

- 表单画布的插入规则。
- 工单认领、退回和重开。
- 决策表的规则编辑器。决策表页面的列表见规则规格。

## Further Notes

- 流程设计页里的表单页签遵守表单设计规格，不在本规格重复。
