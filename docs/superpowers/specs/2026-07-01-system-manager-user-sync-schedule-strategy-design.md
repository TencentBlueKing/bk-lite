# 系统管理用户同步策略设计

## Summary

重构系统管理用户同步的“同步策略”弹窗与后端调度模型，解决当前 `启用状态` 与 `定时同步` 双开关语义重叠的问题，并把自动同步从“仅支持每天 HH:mm”升级为受约束的多模式调度：关闭、每天、每周、每 N 小时。

本次设计保持用户同步的现有执行链路不变：手动同步和自动同步仍统一落到 `UserSyncRun`，只调整策略表达、调度生成和兼容迁移。

## Goals

- 明确区分“同步源是否运行”和“自动同步如何运行”。
- 保留 `UserSyncSource.enabled` 作为同步源总开关：停用后，立即同步与自动同步都不可用。
- 将 `schedule_config` 从旧结构 `{ enabled, sync_time }` 升级为 mode-based 结构。
- 自动同步支持以下模式：
  - 关闭
  - 每天
  - 每周
  - 每 N 小时
- 每周支持多选星期，共用一个执行时间。
- 每 N 小时按 `00:00` 对齐执行，仅允许 `1 / 2 / 3 / 4 / 6 / 8 / 12`。
- 在不引入 cron 编辑器的前提下，提供可预测、可解释、可迁移的调度能力。

## Non-Goals

- 本轮不支持自定义 cron 表达式。
- 本轮不支持每月、工作日、节假日跳过、多时间段组合。
- 本轮不支持任意 N 小时；不接受 `5`、`7`、`10` 等无法稳定映射到日内固定时刻的间隔。
- 本轮不开放时区编辑，只展示“按系统时区执行”的说明。
- 本轮不同时升级其他复用 `schedule_config` 旧结构的模块，例如 IM 通知。

## Current State

### 前端现状

用户同步策略弹窗当前位于：

- `web/src/app/system-manager/components/user/user-sync/UserSyncStrategyModal.tsx`

现有表单字段只有：

- `enabled`
- `schedule_enabled`
- `sync_time`

交互上表现为两个平级开关加一个时间选择器：

- `启用状态`
- `定时同步`
- `同步时间`

这会造成两个问题：

1. `启用状态` 与 `定时同步` 都像“是否开启同步”，用户难以分辨谁控制源状态、谁控制自动调度。
2. 调度只暴露 `HH:mm`，无法表达每周或日内固定间隔。

列表页当前只把 `schedule_config.sync_time` 或 `手动同步` 作为摘要，缺少对策略语义的完整表达。相关代码位于：

- `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
- `web/src/app/system-manager/utils/userSyncPageUtils.ts`

### 后端现状

用户同步源模型位于：

- `server/apps/system_mgmt/models/user_sync_source.py`

当前 `schedule_config` 是 JSONField，结构默认按下述旧格式处理：

```json
{
  "enabled": true,
  "sync_time": "02:00"
}
```

周期任务创建逻辑位于：

- `server/apps/core/mixinx.py`

当前 helper 只支持“每天某时某分”的 crontab：

- `minute = sync_time.minute`
- `hour = sync_time.hour`
- `day_of_week = *`
- `day_of_month = *`
- `month_of_year = *`

因此现有实现本质上只支持 daily schedule。

### 共享校验约束

`validate_user_sync_contract()` 当前复用共享的 `validate_schedule_config()`，而该校验器也被 IM 通知模块使用：

- `server/apps/system_mgmt/services/capability_contract_service.py`

这意味着用户同步若直接改写共享校验规则，会顺带破坏 IM 通知现有的 daily-only 结构。该兼容边界必须显式处理。

## Product Decision

### 1. 把策略拆成两层，而不是继续堆叠布尔值

推荐结构：

1. **同步源状态**
   - 来源：`UserSyncSource.enabled`
   - 语义：这个同步源是否允许运行
2. **自动同步**
   - 来源：`UserSyncSource.schedule_config`
   - 语义：当同步源处于启用状态时，系统如何自动触发同步

结论：

- `enabled = false`：整个同步源停用；手动与自动同步都停止。
- `enabled = true + mode = disabled`：同步源启用，但只有手动同步。
- `enabled = true + mode in (daily, weekly, interval_hours)`：同步源启用，并按策略自动同步。

### 2. 自动同步采用 mode-based 模型

本次 `schedule_config` 统一为：

```json
{
  "mode": "disabled | daily | weekly | interval_hours",
  "time": "HH:mm",
  "weekdays": [1, 3, 5],
  "interval_hours": 6,
  "timezone": "Asia/Shanghai"
}
```

字段说明：

- `mode`
  - `disabled`：关闭自动同步
  - `daily`：每天在 `time` 执行
  - `weekly`：每周在 `weekdays + time` 执行
  - `interval_hours`：按 `00:00` 对齐，按 `interval_hours` 小时步长循环执行
- `time`
  - daily：每日执行时间
  - weekly：每周执行时间
- `weekdays`
  - 仅 weekly 使用，编码为 `1..7 = 周一..周日`
- `interval_hours`
  - 仅 interval_hours 使用，允许值：`1 / 2 / 3 / 4 / 6 / 8 / 12`
- `timezone`
  - 先写入系统默认时区，不在本轮开放编辑

### 3. 不引入 version 字段

本轮不为 `schedule_config` 增加 `version`。

原因：

- 旧结构和新结构差异足够明显，可以通过是否存在 `mode` 来区分。
- 新增 `version` 只会增加前后端维护负担，而不会显著提升业务可读性。
- 迁移目标是让数据快速收敛到一种结构，而不是长期维护多代协议。

## UI Design

### 弹窗结构

#### 区块 1：同步源状态

- 字段：`enabled`
- 展示名称：`同步源状态`
- 文案说明：`停用后，立即同步与自动同步都会停止`

#### 区块 2：自动同步

- 字段：`schedule_mode`
- 展示名称：`自动同步`
- 值：
  - `关闭`
  - `每天`
  - `每周`
  - `每 N 小时`

#### 条件字段

- `mode = daily`
  - `执行时间`
- `mode = weekly`
  - `执行日`
  - `执行时间`
- `mode = interval_hours`
  - `间隔小时`

### 字段规则

#### 同步源状态

- 永远显示
- 保存到 `UserSyncSource.enabled`
- 只控制源是否运行，不承载调度语义

#### 自动同步

- 永远显示
- 保存到 `schedule_config.mode`
- 决定下方条件字段与任务生成方式

#### 执行时间

- `daily / weekly` 时必填
- 格式必须是 `HH:mm`
- 展示说明：`按系统时区执行`

#### 执行日

- 仅 `weekly` 时显示
- 至少选 1 天
- 可多选，共用同一时间
- 编码固定为 `1..7 = 周一..周日`

#### 间隔小时

- 仅 `interval_hours` 时显示
- 仅允许：`1 / 2 / 3 / 4 / 6 / 8 / 12`
- 不再要求单独配置起始时间
- 展示说明：`按 00:00 对齐执行，例如每 6 小时表示 00:00、06:00、12:00、18:00`

### 列表页摘要

列表不再只显示 `sync_time`，而是显示完整策略摘要：

- `enabled = false` → `已停用`
- `mode = disabled` → `手动`
- `mode = daily + 02:00` → `每天 02:00`
- `mode = weekly + [1,3] + 02:00` → `每周一、周三 02:00`
- `mode = interval_hours + 6` → `每 6 小时（00:00 对齐）`

## Scheduling Design

### 调度生成规则

#### disabled

- 不创建 periodic task

#### daily

生成 daily crontab：

- `minute = time.minute`
- `hour = time.hour`
- `day_of_week = *`

#### weekly

生成 weekly crontab：

- `minute = time.minute`
- `hour = time.hour`
- `day_of_week = weekdays`

例如：

- `[1,3,5] + 02:00` → `day_of_week = 1,3,5`

#### interval_hours

本轮仍映射到 crontab，但只支持 24 的因子，并统一按 `00:00` 对齐，不提供“起始时间”配置。

例如：

- `interval_hours = 6`

生成：

- `hour = */6`
- `minute = 0`

再例如：

- `interval_hours = 3`

生成：

- `hour = */3`
- `minute = 0`

### 为什么不支持任意 N 小时

如果允许 `5`、`7` 等无法整除 24 的间隔，crontab 无法稳定表达“严格每 N 小时”的循环语义，会产生跨天漂移。当前仓库的调度实现基于 crontab，而不是真正的 interval schedule，因此本轮必须限制为 24 的因子。

## Backend Design

### Serializer

用户同步 serializer 需要从“旧 daily-only 校验”升级为“mode-based 校验”：

- `mode = disabled`
  - 不要求 `time`
- `mode = daily`
  - 要求合法 `time`
- `mode = weekly`
  - 要求合法 `time`
  - 要求非空 `weekdays`
- `mode = interval_hours`
  - 不要求 `time`
  - 要求 `interval_hours` 属于允许值集

### 模型文件修改说明

本次若进入实现，需要明确修改模型相关文件，但**不做数据库字段新增**，`schedule_config` 仍保持为现有 JSONField。

涉及的模型/调度文件与修改边界：

- `server/apps/system_mgmt/models/user_sync_source.py`
  - 保留 `schedule_config` 字段本身不变
  - 重写 `create_sync_periodic_task()`，不再只读取 `sync_time`
  - 新增或内聚 `schedule_config -> schedule_spec` 的解析逻辑
  - 保持 `periodic_task_name()` / `delete_sync_periodic_task()` 的职责不变
- `server/apps/core/mixinx.py`
  - **不依赖也不改写**现有 `create_periodic_task(sync_time, ...)`
  - 在 `PeriodicTaskUtils` 中新增一个**静态方法**，例如 `create_periodic_task_from_spec(...)`
  - 该静态方法只接收通用 `schedule_spec`，不直接理解 user_sync 的 `schedule_config`
  - 现有 daily-only helper 继续保留给旧调用方使用，避免牵连 IM 通知等模块

结论：

- **修改模型文件是需要的**，但修改点在“调度生成逻辑”，不是“模型字段结构”。
- **不要求新增 migration**，因为 `schedule_config` 仍是同一个 JSONField。

### 共享校验器拆分

不建议直接改写共享的 `validate_schedule_config()` 去只支持新模型。

推荐：

- 为用户同步新增专用 schedule validator
- 保留共享 daily-only validator 供 IM 通知等旧模块继续使用

原因：

- 用户同步这次已经超出“单一 daily schedule”范围
- 继续强行共用旧 validator，只会让模块耦合和条件分支继续膨胀

### 调度 helper

当前 `PeriodicTaskUtils.create_periodic_task(sync_time, ...)` 只能接收 daily 时间字符串。

本次不建议继续复用或扩展这个方法，而是**在 `PeriodicTaskUtils` 中新增一个专用静态方法**。

推荐结构：

1. `schedule_config -> schedule_spec`
2. `PeriodicTaskUtils.create_periodic_task_from_spec(schedule_spec, ...)`

`schedule_spec` 可以统一描述为：

```json
{
  "kind": "crontab",
  "minute": "0",
  "hour": "*/6",
  "day_of_week": "*",
  "day_of_month": "*",
  "month_of_year": "*"
}
```

这样 daily、weekly、interval_hours 都能走一套新的任务创建逻辑，同时不影响现有基于 `sync_time` 的旧 helper。

## Frontend Implementation Boundaries

### 需要修改的主要文件

- `web/src/app/system-manager/types/user-sync.ts`
- `web/src/app/system-manager/components/user/user-sync/UserSyncStrategyModal.tsx`
- `web/src/app/system-manager/utils/userSyncUtils.ts`
- `web/src/app/system-manager/utils/userSyncPageUtils.ts`
- `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
- `web/src/app/system-manager/locales/zh.json`
- `web/src/app/system-manager/locales/en.json`
- `web/src/stories/system-manager-user-sync-source-list.stories.tsx`

### 需要新增/重写的前端 helper

- `toStrategyFormValues(source)`
- `buildSchedulePayload(values)`
- `getScheduleSummary(scheduleConfig, enabled, t)`
## Cutover Strategy

本次采用**直接切换到新语义**，不做旧结构兼容，不做旧数据回填。

约束如下：

- 用户同步后端接口自本次改造起只接受新结构 `schedule_config`
- 用户同步后端接口自本次改造起只返回新结构 `schedule_config`
- 现有存量数据不做 `{ enabled, sync_time } -> { mode, ... }` 映射
- 不提供管理命令、不做 dry-run、不做批量回填

这意味着本次是一次**清晰 cutover**，而不是过渡兼容方案。实现时应同步调整：

1. 前端策略弹窗提交新结构
2. 后端 serializer 仅校验新结构
3. 后端 periodic task 生成逻辑仅依据新结构工作
4. 若测试、样例、fixture、Storybook 中仍存在旧结构，必须直接改成新结构

设计影响：

- 文档、接口、测试、前端 helper 都不再保留旧结构分支
- 用户同步模块内不允许同时维护两套 schedule 语义
- 若线上已有旧数据，需要在实施前由业务方明确接受“旧策略不保留 / 需人工重配”的切换成本

## Acceptance Criteria

### UI

- 策略弹窗中，用户能明确区分“同步源状态”和“自动同步”。
- `daily / weekly / interval_hours` 三种模式的条件字段显隐正确。
- 列表摘要不再只显示时间，而是显示完整策略语义。

### Backend

- `enabled = false` 时，无论 `schedule_config.mode` 是什么，都删除 periodic task。
- `mode = disabled` 时，不创建 periodic task。
- `daily / weekly / interval_hours` 能生成正确 crontab。
- `interval_hours` 只接受允许值集。

### Cutover

- 用户同步接口只接受新结构 `schedule_config`。
- 用户同步接口只返回新结构 `schedule_config`。
- 不实现旧结构兼容读取。
- 不实现旧数据回填或批量迁移命令。

### Verification

最小验证包括：

- `cd web && pnpm lint && pnpm type-check`
- `cd server && make test` 中至少覆盖：
  - schedule serializer mode-based 校验
  - daily / weekly / interval_hours 调度生成
  - `enabled=false` / `mode=disabled` 删除任务
  - 旧结构输入被拒绝

## Risks

- 若直接修改共享 `validate_schedule_config()`，可能破坏 IM 通知等仍使用旧结构的模块。
- 若 interval_hours 放开到任意整数，会让调度语义与实际 crontab 行为不一致。
- 若列表摘要仍只展示 `time`，即便弹窗改清楚，用户对策略的整体认知仍不完整。
- 本次不做旧数据映射与回填，意味着现有旧策略不能被自动继承；若线上已有旧配置，需要接受人工重配或一次性清库式切换。

## Recommendation

本次实现应按以下顺序推进：

1. 先确认是否接受“直接切新结构，不保留旧策略自动迁移”的业务成本。
2. 后端先新增用户同步专用的 schedule helper 与新结构校验逻辑，不改写旧的 daily-only helper。
3. 前端切到 mode-based 弹窗和列表摘要。
4. 同步更新测试、样例和 fixture，移除用户同步模块内的旧结构用法。
