# 采集无变化核实不再重复写日志

Status: implemented

日期：2026-11-06

## 缺陷原因

周期采集在业务字段没有变化时，仍会为每个实例写一条 CMDB `ChangeRecord`，概述是「自动采集核实实例，无字段变化」。带关联的采集（云平台、VMware）会把实例送进更新列表，落库时关联已从实例上摘掉，字段对比结果为空，于是每轮都变成一条核实记录。

这些核实记录又进入 `ChangeRecordMirrorOutbox`。每 100 条派发一个 `consume_change_record_mirror_outbox`，任务里再逐条调用 NATS `save_operation_log`。五分钟一次的 `recover_change_record_mirror_outbox_task` 不看队列里是否已经有同一事件，最多再派发 100 条仍处于 pending 的记录。结果是：

- CMDB 变更记录按实例、按周期不断新增，新鲜度时间被新行带走，但内容没有变化。
- 日志平台收到同一类核实日志的重复插入。
- background 队列被大量镜像任务占住。真正改了字段的日志只占其中很小一部分。

CMDB 自己的 `ChangeRecord` 和日志平台的 `OperationLog` 是两套存储。新鲜度只读 CMDB 记录的 `created_at`。日志平台只应由 NATS 写入。

## 修复方案

无变化核实仍留给 CMDB，用来刷新新鲜度；不进入镜像 outbox，也不推到日志平台。真正的新增、更新、删除和关系变更继续镜像。

同一实例的核实用稳定哈希标识，哈希只含实例、模型、变更类型和核实标记，不含采集时间或任务号。只和该实例最新一条 `ChangeRecord` 比较：哈希相同，或旧数据没有哈希但概述已是核实句时，原地更新 `created_at` 和内容，不新增行。最新一条已经是别的变更时，核实另起一行，避免改写中间的真实历史。

真实变更不再在事务提交后立刻 `delay`。沿用每 5 分钟的 `recover_change_record_mirror_outbox_task`，任务体改为单飞批量推送：锁键 `cmdb-change-record-mirror`，租约约 60 秒，每批成功后续约。上一轮还持有锁时本轮退出。进程退出后，下一轮在租约到期后从剩余 outbox 继续。

日志平台新增 `save_operation_logs`。每批最多 200 条或 768KB。每条在发送前写上幂等键 `{event_id}:{index}`，`OperationLog.idempotency_key` 唯一。重复推送计为成功，不插第二条。整包失败才整包重试。单条超过约 7MB 的负载不发送。已经堆在 outbox 里的核实日志在消费时标成成功，不再推送。

需要执行迁移：`cmdb.0067_changerecord_content_hash`、`system_mgmt.0055_operationlog_idempotency_key`。

采集守门的重复派发、采集任务单飞、自动关联预算和订阅通知不在本次范围。

## 测试结果

2026-11-06 在项目测试库执行，不使用内存 SQLite 全量迁移。内存 SQLite 会在既有 alerts 迁移删除 `SessionEventRelation.event` 时失败，与本次改动无关。

| 范围 | 结果 |
| --- | --- |
| 镜像 outbox、镜像服务、核实折叠、操作日志批量写入、管理类变更端到端 | 22 通过 |
| NATS 处理函数注册包含 `save_operation_logs` | 1 通过 |
| VM 周期拉取后的写日志路径 `test_vm_repeat_pull_does_not_duplicate_verify_or_platform_log` | 1 通过 |

VM 路径核对到的行为：

- 虚拟机带关联、CPU 和内存不变，仍进入更新；只产生 1 条核实记录，不进 outbox。
- 下一轮只改采集时间，还是这一条，`created_at` 被刷新。
- 只有采集时间变化、没有关联的实例走心跳，不写变更记录。
- CPU 从 2 改为 4 时另起一条「自动采集更新实例」，日志平台只增加 1 条。同一负载再推一次，按幂等键记为重复，平台日志仍是 1 条。
- 真实变更之后再两轮无变化，只再保留 1 条核实记录；平台日志保持 1 条。
