# APM 策略与告警指标快照

Status: accepted

## 目标与范围

APM 自有策略执行、告警生命周期、事件、告警指标快照和通知。整体概念与 Monitor 对齐，但 APM 只读取自己的接口和 VictoriaTraces，不依赖 Monitor 的策略、对象、告警或快照表。

本变更不处理服务目录、拓扑、探索、接入和数据链路优化，也不兼容旧策略数据。

## 领域语言

- **Alert**：一次从触发到自动恢复或人工关闭的完整生命周期，状态为 `active / recovered / closed`。
- **Event**：生命周期中的一次状态变化，动作为 `triggered / escalated / recovered / closed`。
- **告警指标快照**：与 Alert 一对一的策略扫描结果集合。每个点是一次阈值对比，不是一个 Event，也不是查询窗口中的原始采样点。
- **事件原始证据**：按 Event 保存的细粒度指标与上下文，只用于诊断，不作为告警主趋势。

无数据是明确的评估状态。查询失败为 `unavailable`，不能当成无数据、触发或恢复。

## 策略模型与执行语义

策略只作用于一个 APM Service；`environment` 必填，`endpoints` 可为空或多选。指标固定为 `error_rate / p95 / p99 / throughput / no_traffic`。每条策略包含：

- `evaluation_interval`：1–60 分钟，决定相邻策略扫描点的理论间隔。
- `metric_window`：1–1440 分钟，决定一次扫描查询多长时间的数据。
- `aggregation`：`avg / max / min / last`，把窗口内原始数据聚合成一个阈值对比值。
- `thresholds`：1–3 条不同级别阈值。
- `trigger_after / recover_after`：连续满足或连续不满足的扫描次数。
- `no_data_after / no_data_severity`：可选的连续无数据条件。

评估在锁内重读策略、目标状态和活动 Alert。`policy + target identity + scheduled_at` 是评估游标，重复或乱序任务不能产生重复 Event 或快照点。告警触发前的连续命中不属于告警生命周期；触发扫描是首点，自动恢复扫描是末点。人工关闭只产生 `closed` Event，不伪造策略扫描点。

APM 只保留 `ApmPolicyTargetState` 作为每个评估目标的运行状态，不保留重复的策略级聚合状态。策略只接受当前的阈值、窗口和通知目标字段。

## 快照模型与接口

`ApmAlertMetricSnapshot` 与 Alert 一对一，结构与 Monitor 的告警指标快照一致：一个记录包含追加式 `snapshots` 集合。集合项类型为：

- `event`：本次扫描同时产生生命周期 Event；
- `info`：本次扫描完成但没有状态变化；
- `no_data`：本次扫描没有可用于阈值判断的数据。

每项只保存主图需要的扫描时间、评估值、当时阈值、数据状态和可选 Event 标识。以 `snapshot_time` 去重，更新时加行锁，避免并发追加丢失。接口一次返回 Alert 的完整集合，不额外设计评估记录列表、最近 100 条截断或游标分页。

- `/api/v1/apm/alerts/{id}/snapshots/`：返回告警指标快照。
- `/api/v1/apm/alerts/{id}/event-evidence/?event_id=...`：按需返回所选 Event 的原始证据。

两个接口都先按当前组织 fail-closed 校验 Alert 和 Event。不存在快照时，告警接口返回空 `snapshots`。

## 页面

详情 Drawer 的“告警”页展示告警指标快照图。横轴使用 `snapshot_time`，检测频率为 1 分钟时相邻扫描点应约为 1 分钟；同一分钟内仍显示秒，避免标签看似重叠。纵轴展示每次扫描用于阈值判断的聚合值和当时阈值。

“事件原始数据”页在用户选择 Event 后再加载细粒度数据。关闭告警按钮阻止表格行点击冒泡；成功关闭后刷新列表并关闭详情，不跳转到告警详情。

页面复用 Ant Design 和现有 APM 组件，不新增共享抽象。

## 数据库变更与发布

- 直接删除旧单阈值、旧周期、旧通知字段和 `ApmPolicyState`，不做回填或兼容读取。
- 新建 `ApmAlertMetricSnapshot`，不为旧 Alert 补造快照。
- 部署顺序为迁移 → Server/Worker/Beat → Web。迁移不访问 VictoriaTraces、对象存储或通知服务。

## 验收

- 策略：只接受当前字段；环境、指标、阈值、周期和无数据配置校验正确。
- 生命周期：触发、升级、恢复、人工关闭和重复调度语义正确。
- 快照：一个 Alert 一份集合；每次生命周期内成功扫描一个点；触发到恢复完整；无数据与恢复阈值正确；人工关闭不加点。
- 权限：Alert、Event、快照和原始证据不可跨组织枚举。
- 页面：主图按扫描频率绘点，事件原始数据按需加载，关闭操作不触发行跳转。
