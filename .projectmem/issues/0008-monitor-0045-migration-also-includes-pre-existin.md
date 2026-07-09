# #0008 monitor 0045 migration also includes pre-existing algorithm verbose_name drift (commit d38cada17 changed verbose_name 聚合算法→周期聚合算法 without migration)

- 2026-07-09T06:45:06Z `issue`: monitor 0045 migration also includes pre-existing algorithm verbose_name drift (commit d38cada17 changed verbose_name 聚合算法→周期聚合算法 without migration) [server/apps/monitor/migrations/0045_alter_monitorinstance_interval_and_more.py]
- 2026-07-09T06:45:07Z `attempt`: Task 2 实施:将 MonitorInstance.interval default 从 10 改为 60,自动生成 0045 migration(同时包含 pre-existing algorithm verbose_name drift)。新回归测试通过,目标 pre-existing test 通过,monitor tests 10236 passed / 19 failed(失败均为 pre-existing) [server/apps/monitor/models/monitor_object.py:55] (worked)
