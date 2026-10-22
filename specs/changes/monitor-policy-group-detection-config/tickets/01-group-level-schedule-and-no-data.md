# 01 — 组级检测频率与无数据告警（后端）

Status: ready

Blocked by: None

**What to build:** 在策略组服务上增加组级检测频率和无数据告警的读写。频率写入组内每条策略并重建其调度任务；无数据只写入每个插件的一条承载规则，开启时刷新基准，关闭时结束无数据告警并清空基准。列表接口返回组级值与一致性标记，规则返回承载标记。新增 `update_detection` 接口。

- [x] 承载规则派生为纯函数：按插件分组，优先 `group_by == ["instance_id"]` 且 id 最小，否则 id 最小
- [x] 开启无数据：承载策略 `enable_alerts` 含 `no_data` 并写入窗口、级别、名称、恢复窗，基准刷新；非承载策略不含 `no_data`
- [x] 关闭无数据：承载策略去掉 `no_data`，未恢复无数据告警以 `no_data_disabled` 结束，基准清空；阈值告警不动
- [x] 开关不变、只改窗口/级别/名称/恢复窗：不结束告警、不重建基准
- [x] 校验：检测窗不小于恢复窗；级别在 critical/error/warning；开启时名称必填
- [x] 组级频率：逐条策略写 `schedule`，用现有 PeriodicTask 重建入口重建；停用或无覆盖实例的策略任务保持关闭；不重置 `last_run_time`、不结束告警
- [x] 频率校验：类型 min/hour/day，数值正整数且不超过 59/23/1
- [x] 列表序列化：`schedule`、`schedule_uniform`、`no_data`、`no_data_uniform`；规则序列化 `no_data_carrier`。非承载规则含 `no_data` 视为不一致
- [x] `update_detection` 接口：`{group_id, schedule?, no_data?}`，至少一块；权限 `strategy_list-Edit`，组限当前组织，记审计日志
- [x] 新接口登记进全局写操作权限测试
- [x] 服务层测试覆盖上述每一条外部结果；复制组后承载规则对应同一插件且带走频率与无数据配置

## Notes

- 复用：`PolicyBaselineService.refresh/clear`、`MonitorPolicyViewSet.update_or_create_task`、`source_has_dispatch_targets`、`PolicyService._mark_new_alerts_closed` 与 `_publish_closed_alerts`、`period_to_seconds`。
- 不新增模型字段、不新增迁移。
- 测试命令沿用：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/monitor/tests/test_policy_group_service.py apps/monitor/tests/test_global_write_action_permissions_views.py --nomigrations --no-cov -o addopts=`

## Completion evidence

- 116 passed，0 failed（4.38s）：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/monitor/tests/test_policy_group_service.py apps/monitor/tests/test_global_write_action_permissions_views.py apps/monitor/tests/test_policy_multi_group.py --nomigrations --no-cov -o addopts=`
- 多跑了 `test_policy_multi_group.py`，因为 `update_rule` 改为只转发请求里出现的字段。
- 服务层覆盖：按插件选承载规则、开启无数据刷新基准、关闭只结束 `alert_type=no_data` 并清空基准、只改窗口不结束告警不重建基准、非法无数据与频率被拒绝、频率重建后停用或无覆盖实例的任务保持关闭且不改 `last_run_time`、请求至少含一块、列表一致性、复制组带走频率与无数据并保持同一插件的承载规则。
