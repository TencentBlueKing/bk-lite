# Task 4 报告：统一监控告警链策略权限根

> 状态：DONE

## 真实归属链与范围

- `MonitorAlert.policy_id -> MonitorPolicy`：告警列表、详情和 PATCH 全部从受限策略 queryset 派生。
- `MonitorEvent.policy_id -> MonitorPolicy`；若同时存在 `event.alert`，必须满足 `event.policy_id == event.alert.policy_id`。
- `MonitorEventRawData -> MonitorEvent -> MonitorPolicy`：先校验完整事件链，再读取 S3 字段。
- `MonitorAlertMetricSnapshot -> MonitorAlert + policy_id`：快照与告警策略不一致时隐藏，并在 S3 读取前返回 404。
- `PolicyInstanceBaseline.policy_id -> MonitorPolicy`：总览统计仅计算受限策略根下的基准。
- 监控模块没有 Incident/故障模型或对应 HTTP 接口；本任务没有虚构入口，也未进入日志模块。

## 实现结果

- `AlertPermissionMixin.get_accessible_policy_queryset()` 统一实现“策略对象权限 ∩ current_team 数据范围”；超级管理员只绕过动作授权，不绕过范围。
- 告警 list/retrieve/update、事件列表、原始数据、快照全部从该策略根派生；孤儿策略、越权策略和双标识不一致记录 fail closed。
- 普通用户更新告警要求策略 `Operate` 权限；越权 PATCH 在 serializer、事务和通知副作用前返回 404。
- 告警列表关联的策略 `organizations` 按 current_team 投影，共享策略仍可见但不泄露 sibling 组织。
- NATS `get_monitor_statistics`、`query_monitor_alert_segments`、`query_latest_active_alerts` 同时校验 actor、规范 current_team、对象权限和策略根；缺失/空/非法上下文直接失败，不再把超管或空范围解释为全量。
- NATS 的 current_team 范围以 Task 1 `SystemMgmt.get_authorized_groups_scoped` 返回值为唯一依据；`get_permissions_rules.team` 只属于旧对象权限响应，不再作为数据范围。两个告警查询在任何实例对象权限 RPC 前先认证 actor/current_team，伪造 sibling 组织时不再触发后续权限或数据查询。
- NATS 字符串 actor 使用显式 `domain`，避免跨域同名用户按默认域查询权限。
- 告警更新使用专用 serializer：仅 `status` 与视图辅助参数 `update_baseline` 可写；`policy_id`、`monitor_instance_id`、指标身份、内容和生命周期簿记字段均明确返回 400，拒绝发生在写库、基线事务和通知之前。
- 监控到节点管理的 HTTP 用户路径在 Task 3 已统一携带 `CurrentTeamDataScope.data_team_ids`；本任务回归确认，无需重复改动。

## TDD 证据

首批 RED 共 8 项，全部按预期失败：

- 超管在组织 A 可见组织 B 告警；
- 共享策略响应泄露 sibling organizations；
- 超管跨组织 PATCH 真正关闭告警并产生副作用；
- 快照策略不一致仍读取 S3；
- Event 策略与 Alert 策略不一致仍返回；
- RawData 非法链仍读取 S3；
- NATS 超管统计返回全量；
- NATS 缺 actor/current_team 仍成功。

第二批 RED：同一授权实例下，两个 NATS 告警查询均返回 sibling 策略告警（count=2）；修复后只返回当前策略根（2 passed）。actor 显式 domain 专项也先复现默认 `domain.com` 错误，再转绿。

审查修复 RED：

- 普通用户仅授权组织 A，却在 NATS actor_context 伪造 sibling B；旧实现未调用 Task 1 scoped RPC，statistics 仍返回 B 的 policy/instance/alert 数据。
- 两个告警查询虽最终 fail closed，但在 scoped RPC 拒绝前已调用实例对象权限 RPC；顺序测试稳定复现各 1 次调用。
- Alert PATCH 同时提交 sibling `policy_id` 与 `status=closed` 返回 200，并可进入通知链；预期为 400、DB 不变、通知 0 次。

修复后，伪造 B 的 statistics/segments/latest 全部 fail closed，且两个告警查询不会调用实例对象权限 RPC；合法普通用户 A、超级管理员 A 与“无授权实例返回空”均保持可用。

## GREEN 与扩大回归

- Task 4 审查后聚焦集合：`91 passed`（包含 coverage 的最终复跑）。
- 告警 `status/update_baseline` 事务与回滚专项：`6 passed`。
- 覆盖率集合：`91 passed`；`diff-cover` 统计 52 个差异可执行行、6 行未覆盖，差异覆盖率 **88%**，高于 75% 门禁。
- 并入 Task 3 监控直接对象权限和业务流的扩大集合：`330 passed in 116.17s`。

## 静态与迁移门禁

- `python -m py_compile`：通过。
- isort 5.10.1（6 个触及文件）：通过。
- flake8 7.1.1（忽略仓库既有 C901/W503/E203 口径）：通过，0 告警。
- Black 23.1：本轮新增 serializer 与继承权限测试通过；生产大文件和既有测试保留仓库基线格式，本任务未做整文件机械格式化。
- `makemigrations --check --dry-run`：通过，`No changes detected`。
- `git diff --check`：通过。
- 原生 SQL 扫描：未发现 `RawSQL`、`.raw()`、`cursor.execute`。

## 已知风险

- `monitor/nats/monitor.py` 是历史大模块；本任务以差异覆盖率 88%、91 项聚焦测试和 330 项权限业务回归约束新增路径。
- 本轮按已确认边界不重构后台自发任务身份，也不处理当前完全未接数据权限的平台公共目录。
