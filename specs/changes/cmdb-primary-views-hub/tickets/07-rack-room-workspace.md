# 07 — 机房机柜工作台

Status: done

Blocked by: 02 — 实例选择器、记忆与空态

**What to build:** 「机房机柜」单入口；room/rack 模式切换；机房点机柜可留在工作台切到机柜模式；显式查看详情进基础信息；mode 与实例独立记忆。

- [x] 单导航项内可在机房 / 机柜模式切换，选择器随 mode 换模型
- [x] 机房平面图单击机柜：留在工作台，切 `mode=rack` 并聚焦该机柜
- [x] 显式「查看详情」进基础信息（不默认跳详情 tab）
- [x] mode + 实例记忆刷新后可恢复

## Completion evidence

- `ViewCanvasHost` rack-room：`RoomFloorPlan` + `onRackSelect` → `onFocusChange({ model_id: 'rack', mode: 'rack', … })`；rack 模式 `RackElevation`
- `resolveRackRoomMode` / 资格 room=`server_room`、rack=`rack`：`test:cmdb-views-hub-core` PASS
- mode+实例记忆：`viewMemory` 读写在 core 覆盖；hub wiring 断言 `onRackSelect` PASS
- Shell「查看详情」→ `buildBaseInfoPath`（不落详情 room/rack tab）
