# 03 — 重置布局

Status: done

Blocked by: 02 — 画布编辑态节点/折线草稿写回

**What to build:** 组件右上角工具栏提供「重置布局」，一键清空**当前布局模式**的手工几何并按该模式算法重算；结果进入草稿，由页面「保存」落库。

- [x] 工具栏提供「重置布局」，文案/交互符合现有工具栏风格
- [x] 点击后仅清空当前 `layoutMode` 对应桶中的 `nodePositions` 与 `linkVertices`，留在当前 mode，其它 mode 桶不动
- [x] 重置后立即按当前模式算法重算并渲染
- [x] 重置只写草稿；需页面「保存」才落库，未保存离开则与其他草稿改动一致可丢失

## Completion evidence

- 工具栏重置按钮 + 确认弹窗（文案说明仅清当前模式）
- `resetNetworkStatusTopologyLayout(config, mode)` 纯函数与单测
