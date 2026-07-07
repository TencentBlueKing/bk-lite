# IM 应用通知定时同步设计

> 说明：本文档保留设计阶段的过程记录。当前仓库实现已经在此基础上继续演进，凡与现状不一致之处，以当前代码实现为准。

## 背景

当前 IM 应用通知同步流程已经支持：

- 手动触发同步
- 请求入口创建 `IMNotificationSyncRun`
- Celery 异步执行同步任务
- 运行记录与正式映射分离

但当前能力仍只有“手动触发”这一种入口，不支持周期性自动同步。与之相比，`user_sync` 已经具备按资源粒度保存 `schedule_config` 并通过 `django_celery_beat` 创建周期任务的能力。

本次设计目标是在不重构现有 IM 同步主链路的前提下，为 IM 应用通知补充按 channel 粒度的定时同步能力。

## 目标

- 支持每个 `IMNotificationChannel` 单独配置定时同步
- 复用现有 IM 同步 run 执行链路，不引入第二套执行流程
- 复用仓库现有 `PeriodicTaskUtils + django_celery_beat` 模式
- 使手动同步与定时同步统一落到 `IMNotificationSyncRun`
- 为后续前端开放配置保留稳定后端接口与数据结构

## 非目标

- 本轮不引入全局统一的 IM 定时策略
- 本轮不支持复杂 cron 表达式、自定义周期规则或多时段配置
- 本轮不引入并发排队、抢占或强制重跑语义
- 本轮前端不强制一起开放配置入口，前端接入可作为下一阶段

## 实施约束

### 阶段 1 迁移策略

阶段 1 涉及模型字段变更时，迁移文件必须沿用当前 IM 重构阶段已明确的策略：

- 不新增新的迁移文件补丁
- 先回退到 `0035`
- 再重新生成并调整 `0036`

也就是说，本次 IM 定时同步相关模型字段变更应直接合入现有：

- `0036_imnotificationchannel_imnotificationusermapping`

而不是追加新的 `0037+` 迁移文件。

## 设计原则

### 1. 只增加触发源，不增加第二套同步语义

定时同步只是现有同步能力的另一个触发源，不应引入新的状态机、映射语义或执行分支。

### 2. 调度与执行解耦

周期任务只负责“是否发起同步”，不直接承担同步执行。真正的同步逻辑仍统一走：

1. 创建 run
2. 异步执行 run
3. 更新运行结果与 channel 状态

### 3. 与 `user_sync` 保持实现模式一致

优先复用现有 `PeriodicTaskUtils`、`schedule_config` 和 serializer 生命周期同步任务的方式，降低维护成本和认知成本。

### 4. 并发控制继续以 channel 为单位

同一 channel 任意时刻仍只允许一个 `running` run。定时任务不能突破这一约束。

## 现状

当前 IM 同步能力具备以下特点：

- `IMNotificationChannel` 没有 `schedule_config`
- 没有 `PeriodicTaskUtils`
- viewset 中只有手动入口 `POST sync_mappings`
- `tasks.py` 中只有 `execute_im_notification_sync_run_task(run_id)`
- service 中只有：
  - `create_im_notification_sync_run(channel_id)`
  - `execute_im_notification_sync_run(run_id)`

因此当前同步流程是“异步执行”，但不是“定时调度”。

## 方案选择

### 方案 A：按 channel 保存 `schedule_config` 并生成独立 periodic task

这是推荐方案。

特点：

- 每个 channel 自带调度配置
- 每个 channel 对应一个独立周期任务
- 周期任务只负责触发 channel 同步
- 同步执行仍完全复用现有 run 机制

优点：

- 和 `user_sync` 模式一致
- 实现边界清晰
- 问题排查简单
- 后续前端按 channel 配置更自然

### 方案 B：单独建 `IMNotificationSchedule` 表

不推荐作为本轮方案。

缺点：

- 结构更重
- 与当前资源模型割裂
- 当前收益不足以覆盖复杂度

### 方案 C：一个全局周期任务扫描全部 channel

不推荐作为本轮方案。

缺点：

- 调度逻辑集中在扫描任务内，边界模糊
- 与 `user_sync` 模式不一致
- 触发排查、局部停用和任务生命周期都更难处理

## 模型设计

### `IMNotificationChannel`

在现有模型基础上新增：

- `schedule_config`

推荐结构：

```json
{
  "enabled": true,
  "sync_time": "02:00"
}
```

同时让 `IMNotificationChannel` 复用 `PeriodicTaskUtils`，补充：

- `periodic_task_name()`
- `create_sync_periodic_task()`
- `delete_sync_periodic_task()`

周期任务名建议：

```text
im_notification_channel_<id>
```

### `IMNotificationSyncRun`

建议新增：

- `trigger_mode`

建议取值：

- `manual`
- `schedule`

原因：

- 能直接区分手动与定时触发
- 与 `user_sync` 现有 run 模式一致
- 便于记录展示、筛选和排查

不建议只放进 `payload`，因为那会削弱查询和展示的直接性。

语义边界需要明确：

- `trigger_mode` 只表示该 run 的创建来源
- 不表示 run 的执行结果
- 不表示 channel 当前是否配置了自动同步
- 不表示当前任务是否正在运行

## 状态语义

### `IMNotificationChannel.status`

保持不变：

- `pending_sync`
- `ready`
- `needs_resync`
- `disabled`

### `IMNotificationSyncRun.status`

保持不变：

- `running`
- `success`
- `partial`
- `failed`

### 结论

定时同步不新增新的状态值。

它只新增：

- 一个触发来源：`trigger_mode = schedule`

不引入：

- `scheduled`
- `queued`
- `auto_retry`

等新的运行状态。

## 调度生命周期

调度采用声明式同步：

- channel 保存后，系统自动根据 `enabled + schedule_config` 创建、更新或删除周期任务

### 创建 channel

当以下条件成立时创建 periodic task：

- `channel.enabled = true`
- `schedule_config.enabled = true`
- `schedule_config.sync_time` 非空

否则不创建。

### 更新 channel

每次更新后重新同步 periodic task：

- 需要启用时则创建或更新
- 不需要启用时则删除

### 删除 channel

删除 channel 时同步删除对应 periodic task，避免悬挂任务继续触发。

## 是否要求 `channel.status == ready`

不建议把 `ready` 作为创建 periodic task 的前置条件。

原因：

- 新建 channel 可能仍处于 `pending_sync`
- 但它完全可以先配置调度，并在到点时自动完成首次同步

因此建议：

- `periodic task` 可以存在于 `pending_sync / needs_resync / ready`
- 是否真正创建 run，由运行时服务层校验决定

## 任务设计

### 新增调度触发任务

建议新增一个很薄的 task，例如：

- `schedule_im_notification_sync(channel_id)`

职责：

1. 调用 `create_im_notification_sync_run(channel_id, trigger_mode="schedule")`
2. 若创建成功，调用 `execute_im_notification_sync_run_task.delay(run_id)`
3. 若未创建成功，则按规则记录日志并结束

### 现有执行任务保持不变

继续保留：

- `execute_im_notification_sync_run_task(run_id)`

它仍然只负责执行已创建好的 run。

### 设计结论

调度任务只触发，不执行。

同步任务只执行，不判断周期策略。

## Service 设计

### `create_im_notification_sync_run`

建议扩展为支持：

- `trigger_mode="manual"` 默认值

行为：

- 手动入口调用时传 `manual`
- 定时任务调用时传 `schedule`

创建 run 时写入：

- `trigger_mode`
- `locked_config_snapshot`

### 并发控制

同一 channel 任意时刻只允许一个 `running` run，规则不变。

定时任务命中已有 `running` run 时：

- 不排队
- 不抢占
- 不重试
- 直接跳过
- 记录日志

这是一个“正常跳过”而非“执行失败”。

### 定时触发返回口径

为保持与当前 `create_im_notification_sync_run` 返回风格一致，建议统一以下口径：

- 若成功创建 run：
  - 返回 `result=True`
  - 返回 `run_id`
- 若因“已有 running run”或其他不满足触发条件而未创建 run：
  - 返回 `result=False`
  - 返回可读 `message`
  - 不创建 `failed` run
  - 仅记录 skip 日志

也就是说：

- `result=False` 在定时触发路径下不等价于“同步执行失败”
- 它只表示“本次调度没有创建新的 run”

## Serializer / 生命周期设计

建议与 `user_sync` 保持一致：

- serializer `create()` 后调用 `_sync_periodic_task(instance)`
- serializer `update()` 后调用 `_sync_periodic_task(instance)`

内部规则：

- 如果 `channel.enabled && schedule_config.enabled && sync_time`，则 `create_sync_periodic_task()`
- 否则 `delete_sync_periodic_task()`

删除时：

- 在 viewset `destroy()` 流程中调用 `delete_sync_periodic_task()`

## 前端分阶段策略

### 阶段 1：先完成后端能力

本阶段只做：

- `schedule_config`
- `trigger_mode`
- periodic task 生命周期
- 调度触发任务
- run 记录打通

不强制开放前端配置入口。

### 阶段 2：前端接入当前 IM 页面

前端接入时，保持当前 IM 页面整体布局不变，只在编辑弹层中增加一个轻量区块。

交互形态调整为“同步选项”，而不是单独的“定时同步开关”：

- `同步选项`
  - `手动同步`
  - `自动同步`
- 当选择 `自动同步` 时，展示 `同步时间` 选择器
- 当选择 `手动同步` 时，不展示或禁用 `同步时间`

配置结构直接对应后端：

```json
{
  "enabled": true,
  "sync_time": "02:00"
}
```

首版建议：

- 仅支持“每天固定时间同步一次”
- 不支持复杂 cron
- 不新增额外调度管理页面

## 风险与边界

### 1. 定时任务不能绕开现有运行校验

不管是手动还是定时触发，都必须统一经过 `create_im_notification_sync_run` 校验。

### 2. 跳过并发 run 必须视为正常行为

如果已有 `running` run，定时任务应安静跳过，否则容易制造无意义告警和重试。

### 3. 调度配置不应承担运行状态职责

`schedule_config` 只表达“何时触发”，不表达“当前同步结果如何”。

### 4. 前端不应在后端未稳定前抢先暴露入口

因为定时调度本质上是后端能力，建议先把调度生命周期、run 记录和跳过语义做稳，再开放 UI。

## 测试与验证方向

后续实现至少应覆盖：

- channel 创建时启用定时任务的创建逻辑
- channel 更新时定时任务的更新/删除逻辑
- channel 删除时 periodic task 清理
- 定时任务触发后创建 `trigger_mode=schedule` 的 run
- 定时任务触发时命中 `running` run 的跳过逻辑
- 手动与定时触发都能进入同一执行链路
- `pending_sync` channel 可通过定时触发完成首次同步

## 决策结论

本次 IM 定时同步设计采用以下结论：

- 按 channel 粒度配置定时同步
- 复用 `schedule_config + PeriodicTaskUtils + django_celery_beat` 模式
- 定时触发只负责创建 run 并投递现有执行任务
- `IMNotificationSyncRun` 增加 `trigger_mode`
- 保持现有 channel/run 状态集合不变
- 同一 channel 不允许并发 run，定时命中运行中任务时直接跳过
- 分阶段落地：先后端，后前端
