# 应用用户习惯表

## 目标

每个应用用自己的用户习惯表保存当前登录用户的工作台状态。刷新、重新登录、换设备后仍按账号生效。监控现有列表列配置迁入该表后删除旧表。

## 行为契约

- 习惯只属于当前用户，不按组织隔离，不写入 CMDB 或 system_mgmt。
- 通用读写：`GET/PUT /{app}/api/user_habits/{habit_key}/`（日志无中间 `api` 段：`/log/user_habits/{habit_key}/`）。
- GET 无记录返回 `data: null`，不 404。
- PUT 体就是 JSON 对象；键格式 `^[a-zA-Z0-9._-]{1,100}$`；值必须是对象且不超过 16KB。
- 读失败不得阻断页面；写失败不得回滚当前界面。
- 有结构约束的习惯（监控视图列）继续走原校验门面，存储改写本表。

## 键约定

| 应用 | key | value |
|---|---|---|
| monitor / log | `event.alert.chartExpanded` | `{ "expanded": true }` |
| log | `search.histogramExpanded` | `{ "expanded": true }` |
| monitor | `view.columnPreference.{object_id}` | `{ "field_keys": [...], "fixed_field_keys": [...] }` |

## 接缝

- 抽象模型 `apps.core.models.user_habit.UserHabitBase`
- 校验与 ViewSet：`apps.core.views.user_habit`
- 监控门面：`GET/PUT /monitor/api/monitor_object/{id}/view_column_preference/`
- 前端 `useHabitExpanded({ enabled, load, save })`

## 迁移

- 将 `MonitorViewColumnPreference` 行复制为 `view.columnPreference.{monitor_object_id}`。
- 复制完成后删除旧表。列接口契约保持不变。

## 验证

- 通用接口覆盖缺省、保存、非法键/值、用户隔离。
- 列配置旧接口在迁表后仍能保存、读取、校验和隔离。
- 告警分布图收起写入对应应用习惯表，不再把账号习惯写进 localStorage。
