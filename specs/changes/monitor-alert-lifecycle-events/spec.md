# 监控告警事件改为状态变更

Status: accepted

## Completion Evidence

- `MonitorEvent.action` 可空；新写入必须是 `triggered` / `escalated` / `recovered` / `closed`。同一 Alert 上 status 动作与按级别的 `escalated` 有部分唯一约束。
- 策略扫描只在新建 Alert、级别升高时落 Event；持续超阈和级别回落只更新快照/Alert。无数据打开只写一条 `triggered`。恢复与关闭入口写终态 Event，且不因重试重复写入。
- 有状态 Event 的扫描点类型为 `event`；无状态变化为 `info` / `no_data`。无数据告警不拷贝阈值窗口 raw_data，但仍关联生命周期 Event。
- 事件查询返回 `action`；详情事件 Tab 展示动作文案，不再按 Event 计数渲染热力图。
- 测试：`apps/monitor/tests/test_alert_lifecycle_events.py`、`test_policy_scan_event_alert_manager.py`、`test_policy_scan_alert_detector.py`、`test_policy_scan_scanner.py`、`test_snapshot_recorder_service.py`、`test_monitor_alert_view.py`、`test_monitor_policy_view_helpers.py`、`test_monitor_instance_removal_service.py`；前端 `web/src/app/monitor/hooks/__tests__/event.actionMap.test.tsx`、`web/src/app/monitor/(pages)/event/alert/__tests__/alertDetail.eventTimeline.test.tsx`。
- 验证（2026-09-07）：上述后端用例在 PostgreSQL `--reuse-db` 下通过；上述 vitest 通过。

## Problem Statement

监控告警详情的「事件」看起来像策略扫描流水，而不是事故叙事。阈值还在命中时，每个扫描周期都新建一条 Event；自动恢复和人工关闭却只改 Alert、写操作记录，事件列表里看不到收尾。运维无法一眼分辨「刚触发」「级别升高」「已经恢复」「被人关掉」，只能在一长串相似记录里自己猜。告警指标快照已经按扫描记下完整生命周期，Event 再抄一遍没有新信息。

## Solution

监控 Event 只记录会改变告警叙事的状态变化：触发、升级、恢复、关闭。持续超阈、未命中阈值、无数据仍在持续、级别回落都不建 Event。告警指标快照继续为活跃期内每次成功扫描追加一个点，承担趋势和密度。详情事件 Tab 变成带动作的状态时间线；扫描密度继续看快照图。日志告警不改。

## User Stories

1. As a 值班运维, I want 一条监控告警的事件列表只出现触发、升级、恢复和关闭, so that 我能立刻看懂这条事故发生了什么，而不是面对每次扫描的重复记录
2. As a 值班运维, I want 自动恢复和人工关闭也出现在事件列表里, so that 收尾动作与触发、升级一样可审计，而不只写在告警操作记录里
3. As a 值班运维, I want 告警详情的指标趋势仍然覆盖从触发到恢复的每次策略扫描, so that 我仍能看到持续超阈、回落和空窗，而不依赖 Event 条数
4. As a 值班运维, I want 事件时间线上能看出动作类型和级别, so that 升级不会被误认成又一次普通命中
5. As a 策略扫描与关闭路径, I want 同一告警的同一状态动作不会因重试、补偿扫描或重复关闭再写一条 Event, so that 事件列表保持一条叙事而不是并发回放

## Implementation Decisions

- 监控 Event 的领域含义与 APM 告警事件对齐：一次不可变状态变化。动作固定为 `triggered` / `escalated` / `recovered` / `closed`。Alert 级别仍只升不降；级别回落不是状态变更，不记 Event，也不改 Alert 当前级别。
- `MonitorEvent` 增加可空 `action` 字段。新写入必须带动作；存量扫描流水 Event 保持 `action` 为空，页面按历史记录展示，不做回填、不删除。
- 事件查询接口在现有字段上增加 `action`。权限、分页和按告警查询的路径不变。
- 策略扫描只在这些情况落 Event：新建活动 Alert（`triggered`）；已有活动 Alert 且本轮命中级别高于 Alert 当前级别（`escalated`）；活动 Alert 自动恢复（`recovered`）；活动 Alert 被关闭（`closed`）。其余命中、info、持续无数据只更新快照和 Alert 计数/状态机，不建 Event。
- 无数据 Alert 仍按「同一策略 + 同一监控实例」聚合成一条。打开时只写一条 `triggered` Event，不再为每个缺失维度各写一条 Event。维度级证据留在该次扫描的快照点中。部分维度恢复仍不恢复 Alert，也不写 Event；全部基准恢复才写一条 `recovered`。这取代「不同缺失维度分别保留 MonitorEvent」的旧契约。
- 告警指标快照的一对一模型和追加式生命周期不变。有状态 Event 的扫描点类型为 `event` 并关联该 Event；无状态变化的成功扫描点类型为 `info` 或 `no_data`。为此，持续超阈的原始数据必须在不建 Event 时仍进入快照记录，不能再依赖「先建 Event 再从 EventRawData 取数」。人工关闭、策略删除、实例移除不是策略扫描，不追加快照点。
- `recovered` Event 与 Alert 状态、结束时间、操作记录、告警中心投递在同一次状态转换里写下。`closed` Event 覆盖所有把活动告警置为关闭的入口：页面关闭、策略删除、实例移除。关闭原因和操作者写入 Event 内容，与现有 `operation_logs` 一致。已恢复或已关闭的 Alert 不再写第二条终态 Event。
- 通知和告警中心副本仍按 Alert 生命周期动作投递（created / upgraded / recovered / closed），不因 Event 变少而少发，也不因补了恢复/关闭 Event 而多发。Event 不是通知通道。
- 同一 Alert 上：`triggered` / `recovered` / `closed` 每种动作最多一条；`escalated` 按升到的级别各最多一条。重复或乱序扫描、关闭重试用已有行锁和状态条件更新保证，不得覆盖更早成立的终态。
- 详情事件 Tab 改为状态时间线：展示时间、动作、级别和内容。原按 Event 条数着色的热力图不再作为扫描密度图；密度与趋势只使用告警指标快照图。无 `action` 的历史 Event 仍出现在时间线中。
- 实现时同步更新术语表和监控相关 capability：补监控告警 / 监控告警事件 / 监控告警指标快照的定义，并改写无数据聚合与「每轮扫描都产生 Event」的旧表述。`monitor-alert-storm-protection` 中「业务要求永久保留每轮 Event」对本 change 之后的新写入不再适用；快照仍按扫描保留。

## Testing Decisions

- 只断言外部行为：给定扫描结果或关闭动作后，Alert 状态、Event 条数与动作、快照点类型/数量、通知动作是否变化。不断言内部函数是否被调用。
- 最高接缝是一次完整策略扫描（含补偿窗口）和各关闭入口。已有扫描、快照、关闭与事件查询测试作为先验，改为锁定新语义，而不是另起一套平行夹具。
- 必须覆盖：首次命中只建 `triggered`；后续同级命中不建 Event 但仍追加 `info` 快照；级别升高建 `escalated` 且通知仍是 upgraded；连续 info 达到恢复条件建一条 `recovered` 且快照含恢复当次扫描点；页面关闭、策略删除、实例移除各建一条 `closed` 且不加快照点；级别回落不建 Event、Alert 级别保持峰值；无数据多维度打开只有一条 `triggered`，部分恢复不写 Event，全部恢复写 `recovered`；同一窗口重试不重复 Event；关闭与恢复并发时终态与 Event 一致且只有一个终态动作；事件查询返回 `action` 且组织 fail-closed；存量无 `action` 的 Event 仍可列出。
- 通知断言保持「每个生命周期动作一次」，证明 Event 变薄没有改变投递。
- 页面侧锁定事件时间线展示动作文案，且热力图不再依赖 Event 计数作为扫描密度。

## Out of Scope

- 日志告警 Event、日志 AlertSnapshot、日志自动恢复。
- 把监控 Event 收成跨 App 统一表，或改告警中心入站契约。
- 降级动作、Alert 当前级别随扫描下调。
- 回填、改写或清理历史扫描流水 Event。
- 改变快照保留策略、截断上限或存储位置。
- 监控告警风暴保护中尚未启用的有界扫描切片。

## Further Notes

已确认：快照继续记全生命周期；Event 只记状态变更；不记降级。事件 Tab 热力图若仍按 Event 计数，收薄后会失真，因此密度归快照图。无数据聚合 Alert 打开时从「每维度一条 Event」改为「每 Alert 一条 triggered」，避免把维度证据重新塞回 Event。
