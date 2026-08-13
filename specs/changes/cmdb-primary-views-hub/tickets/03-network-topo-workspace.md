# 03 — 网络拓扑工作台

Status: done

Blocked by: 02 — 实例选择器、记忆与空态

**What to build:** 一级「网络拓扑」在工作台内复用现有网络拓扑能力（含编辑）；支持设为当前焦点；显式「查看详情」进基础信息。

- [x] 有合法实例时画布与详情入口同权（含既有编辑）
- [x] 可将仍支持网络主题的节点设为当前实例（更新 URL + 记忆）
- [x] 「查看详情」进入该实例基础信息，不落 relationships tab
- [x] NetworkTopo 所需关联上下文在工作台局部提供，不套详情整页 layout

## Completion evidence

- ViewCanvasHost embeds RelationshipsProvider + NetworkTopo with fillContainer
- Optional onRequestFocus / onViewDetail; hub: dblclick + context menu; detail unchanged
- Hub tests PASS
