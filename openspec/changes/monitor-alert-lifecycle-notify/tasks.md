## 1. 数据模型与迁移

- [x] 1.1 MonitorAlert 模型新增 `notice_type_id`（IntegerField, default=0）和 `notice_users`（JSONField, default=list）字段
- [x] 1.2 生成并应用数据库迁移文件（不回填存量数据）

## 2. AlertLifecycleNotifier 重构

- [x] 2.1 重构 `AlertLifecycleNotifier`，改为从 alert 自身取 notice_type_id/notice_users（alert.notice_type_id == 0 时 fallback 到 policy）
- [x] 2.2 支持普通渠道通知（邮件/企微/飞书等），不再仅限 alert center NATS
- [x] 2.3 按 notice_type_id 分组批量发送，渠道不存在时 log warning 跳过
- [x] 2.4 支持四种动作的通知内容模板：created/upgraded/closed/recovered
- [x] 2.5 告警中心 NATS payload 的 action 映射：created→created, upgraded→updated, closed→closed, recovered→recovery

## 3. 告警创建时快照通知配置并触发通知

- [x] 3.1 `EventAlertManager._create_alerts_from_events` 中创建告警时写入 notice_type_id/notice_users（从 policy 快照）
- [x] 3.2 创建告警成功后调用 `AlertLifecycleNotifier.notify(new_alerts, action="created")`

## 4. 告警升级时触发通知

- [x] 4.1 `EventAlertManager._update_existing_alerts_from_events` 中 level 提升并 bulk_update 后调用 `AlertLifecycleNotifier.notify(alert_level_updates, action="upgraded")`

## 5. 移除事件级通知

- [x] 5.1 移除 `EventAlertManager.notify_events` 方法的实际通知逻辑（保留方法签名为空操作或直接删除）
- [x] 5.2 移除 `EventAlertManager.send_notice` 方法
- [x] 5.3 移除 `EventAlertManager._push_to_alert_center` 方法（created 推送已迁移到 lifecycle notifier）
- [x] 5.4 移除 `EventAlertManager._check_alert_center_channel` 及相关初始化逻辑
- [x] 5.5 清理 policy scan 主流程中对 `notify_events` 的调用

## 6. 验证

- [x] 6.1 确认现有 closed/recovered 通知路径不受破坏（AlertLifecycleNotifier 调用点在 alert_detector.py、monitor_policy.py、monitor_alert.py）
- [x] 6.2 确认 MonitorEvent 创建逻辑不受影响（事件仍正常记录，notice_result 字段保留但不写入）
- [ ] 6.3 执行 `cd server && make test` 确认测试通过（阻塞：当前环境无法连通 PostgreSQL；补充：`uv run pytest apps/monitor/tests/test_policy_scan_failure_handling.py -q` 中本次相关 monitor 用例已通过）
- [ ] 6.4 检查 lsp_diagnostics 确认无类型错误（阻塞：本地未安装 basedpyright-langserver；补充：变更文件已通过 `python3 -m py_compile` 语法校验）
