# 当前上游 Celery 任务清单

基线：TencentBlueKing/bk-lite master `7fc417be88`，2026-10-30。静态解析 182 个任务定义（含显式 name 与 queue）；不等同某台生产机器的实际注册集合。未实测的耗时/并发分类是基于执行职责的架构判断，不是性能数据。

保留 OpsPilot、报表渲染和 patch_maintenance 既有专用队列，默认 celery 拆为四个有界弹性 worker。专用 worker 并发同样计入总预算；本次不修改业务任务。

| 队列 | 定义数 |
|---|---:|
| background | 94 |
| critical | 12 |
| dashboard_report_render | 1 |
| notification | 22 |
| opspilot_channel | 12 |
| opspilot_chat_parse | 1 |
| opspilot_maintenance | 9 |
| opspilot_wiki | 9 |
| patch_maintenance | 2 |
| state | 20 |

## 准确注册名称与分类

| 任务 | 队列 | 判断依据 | 源码 |
|---|---|---|---|
| `apps.alerts.tasks.action_tasks.process_alert_actions` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/alerts/tasks/action_tasks.py:10](../server/apps/alerts/tasks/action_tasks.py#L10) |
| `apps.alerts.tasks.itsm_tasks.scan_itsm_tickets` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/alerts/tasks/itsm_tasks.py:11](../server/apps/alerts/tasks/itsm_tasks.py#L11) |
| `apps.alerts.tasks.tasks.async_auto_assignment_for_alerts` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/alerts/tasks/tasks.py:239](../server/apps/alerts/tasks/tasks.py#L239) |
| `apps.alerts.tasks.tasks.beat_close_alert` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/alerts/tasks/tasks.py:156](../server/apps/alerts/tasks/tasks.py#L156) |
| `apps.alerts.tasks.tasks.beat_retry_unassigned_assignment` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/alerts/tasks/tasks.py:313](../server/apps/alerts/tasks/tasks.py#L313) |
| `apps.alerts.tasks.tasks.build_instant_alerts` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/alerts/tasks/tasks.py:391](../server/apps/alerts/tasks/tasks.py#L391) |
| `apps.alerts.tasks.tasks.check_and_send_escalations` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/alerts/tasks/tasks.py:220](../server/apps/alerts/tasks/tasks.py#L220) |
| `apps.alerts.tasks.tasks.check_and_send_reminders` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/alerts/tasks/tasks.py:178](../server/apps/alerts/tasks/tasks.py#L178) |
| `apps.alerts.tasks.tasks.cleanup_reminder_tasks` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/alerts/tasks/tasks.py:200](../server/apps/alerts/tasks/tasks.py#L200) |
| `apps.alerts.tasks.tasks.deliver_alert_notification_channel` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/alerts/tasks/tasks.py:42](../server/apps/alerts/tasks/tasks.py#L42) |
| `apps.alerts.tasks.tasks.deliver_alert_outbox` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/alerts/tasks/tasks.py:35](../server/apps/alerts/tasks/tasks.py#L35) |
| `apps.alerts.tasks.tasks.dispatch_pending_alert_notification_deliveries` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/alerts/tasks/tasks.py:49](../server/apps/alerts/tasks/tasks.py#L49) |
| `apps.alerts.tasks.tasks.dispatch_pending_alert_outbox` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/alerts/tasks/tasks.py:75](../server/apps/alerts/tasks/tasks.py#L75) |
| `apps.alerts.tasks.tasks.event_aggregation_alert` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/alerts/tasks/tasks.py:106](../server/apps/alerts/tasks/tasks.py#L106) |
| `apps.alerts.tasks.tasks.sync_no_dispatch_alert_notice_task` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/alerts/tasks/tasks.py:503](../server/apps/alerts/tasks/tasks.py#L503) |
| `apps.alerts.tasks.tasks.sync_notify` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/alerts/tasks/tasks.py:422](../server/apps/alerts/tasks/tasks.py#L422) |
| `apps.alerts.tasks.tasks.sync_shield` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/alerts/tasks/tasks.py:486](../server/apps/alerts/tasks/tasks.py#L486) |
| `apps.apm.tasks.deliver_apm_alert_outbox` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/apm/tasks.py:124](../server/apps/apm/tasks.py#L124) |
| `apps.apm.tasks.dispatch_apm_policy_evaluations` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/apm/tasks.py:74](../server/apps/apm/tasks.py#L74) |
| `apps.apm.tasks.evaluate_apm_policy` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/apm/tasks.py:102](../server/apps/apm/tasks.py#L102) |
| `apps.apm.tasks.expire_apm_event_snapshot_payloads` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/apm/tasks.py:179](../server/apps/apm/tasks.py#L179) |
| `apps.apm.tasks.persist_apm_event_snapshot_payloads` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/apm/tasks.py:154](../server/apps/apm/tasks.py#L154) |
| `apps.apm.tasks.probe_apm_runtime_dependencies` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/apm/tasks.py:60](../server/apps/apm/tasks.py#L60) |
| `apps.apm.tasks.reconcile_telemetry_catalog` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/apm/tasks.py:31](../server/apps/apm/tasks.py#L31) |
| `apps.cmdb.tasks.celery_tasks.check_subscription_rules` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1255](../server/apps/cmdb/tasks/celery_tasks.py#L1255) |
| `apps.cmdb.tasks.celery_tasks.cleanup_config_file_orphan_temp_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1382](../server/apps/cmdb/tasks/celery_tasks.py#L1382) |
| `apps.cmdb.tasks.celery_tasks.collect_node_mgmt_hosts` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1340](../server/apps/cmdb/tasks/celery_tasks.py#L1340) |
| `apps.cmdb.tasks.celery_tasks.consume_change_record_mirror_outbox` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1411](../server/apps/cmdb/tasks/celery_tasks.py#L1411) |
| `apps.cmdb.tasks.celery_tasks.consume_cmdb_operation_outbox` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1404](../server/apps/cmdb/tasks/celery_tasks.py#L1404) |
| `apps.cmdb.tasks.celery_tasks.daily_data_cleanup_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1267](../server/apps/cmdb/tasks/celery_tasks.py#L1267) |
| `apps.cmdb.tasks.celery_tasks.enrich_scan_middleware_snapshots` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1448](../server/apps/cmdb/tasks/celery_tasks.py#L1448) |
| `apps.cmdb.tasks.celery_tasks.execute_collect_tool_debug_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1192](../server/apps/cmdb/tasks/celery_tasks.py#L1192) |
| `apps.cmdb.tasks.celery_tasks.execute_first_collection_run` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:448](../server/apps/cmdb/tasks/celery_tasks.py#L448) |
| `apps.cmdb.tasks.celery_tasks.execute_ipam_reconcile_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1363](../server/apps/cmdb/tasks/celery_tasks.py#L1363) |
| `apps.cmdb.tasks.celery_tasks.finalize_scan_execution` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/cmdb/tasks/celery_tasks.py:1434](../server/apps/cmdb/tasks/celery_tasks.py#L1434) |
| `apps.cmdb.tasks.celery_tasks.full_sync_auto_association_rule_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1316](../server/apps/cmdb/tasks/celery_tasks.py#L1316) |
| `apps.cmdb.tasks.celery_tasks.reconcile_auto_relation_pending_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1282](../server/apps/cmdb/tasks/celery_tasks.py#L1282) |
| `apps.cmdb.tasks.celery_tasks.reconcile_cmdb_operations_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1392](../server/apps/cmdb/tasks/celery_tasks.py#L1392) |
| `apps.cmdb.tasks.celery_tasks.reconcile_config_file_content_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1373](../server/apps/cmdb/tasks/celery_tasks.py#L1373) |
| `apps.cmdb.tasks.celery_tasks.reconcile_instance_auto_association_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1289](../server/apps/cmdb/tasks/celery_tasks.py#L1289) |
| `apps.cmdb.tasks.celery_tasks.reconcile_instances_auto_association_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1298](../server/apps/cmdb/tasks/celery_tasks.py#L1298) |
| `apps.cmdb.tasks.celery_tasks.reconcile_ipam_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1354](../server/apps/cmdb/tasks/celery_tasks.py#L1354) |
| `apps.cmdb.tasks.celery_tasks.recover_change_record_mirror_outbox_task` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/cmdb/tasks/celery_tasks.py:1418](../server/apps/cmdb/tasks/celery_tasks.py#L1418) |
| `apps.cmdb.tasks.celery_tasks.recover_due_scan_executions` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/cmdb/tasks/celery_tasks.py:1441](../server/apps/cmdb/tasks/celery_tasks.py#L1441) |
| `apps.cmdb.tasks.celery_tasks.recover_first_collection_runs` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/cmdb/tasks/celery_tasks.py:469](../server/apps/cmdb/tasks/celery_tasks.py#L469) |
| `apps.cmdb.tasks.celery_tasks.send_subscription_notifications` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/cmdb/tasks/celery_tasks.py:1260](../server/apps/cmdb/tasks/celery_tasks.py#L1260) |
| `apps.cmdb.tasks.celery_tasks.sync_cmdb_display_fields_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1111](../server/apps/cmdb/tasks/celery_tasks.py#L1111) |
| `apps.cmdb.tasks.celery_tasks.sync_collect_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:476](../server/apps/cmdb/tasks/celery_tasks.py#L476) |
| `apps.cmdb.tasks.celery_tasks.sync_collect_tasks_gate` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:835](../server/apps/cmdb/tasks/celery_tasks.py#L835) |
| `apps.cmdb.tasks.celery_tasks.sync_incoming_auto_association_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1307](../server/apps/cmdb/tasks/celery_tasks.py#L1307) |
| `apps.cmdb.tasks.celery_tasks.sync_node_mgmt_hosts` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1325](../server/apps/cmdb/tasks/celery_tasks.py#L1325) |
| `apps.cmdb.tasks.celery_tasks.sync_periodic_update_task_status` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/cmdb/tasks/celery_tasks.py:1086](../server/apps/cmdb/tasks/celery_tasks.py#L1086) |
| `apps.cmdb.tasks.celery_tasks.sync_public_enum_library_snapshots_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1215](../server/apps/cmdb/tasks/celery_tasks.py#L1215) |
| `apps.cmdb.tasks.celery_tasks.trigger_first_collection` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:458](../server/apps/cmdb/tasks/celery_tasks.py#L458) |
| `apps.cmdb.tasks.celery_tasks.trigger_scan_execution` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/celery_tasks.py:1427](../server/apps/cmdb/tasks/celery_tasks.py#L1427) |
| `apps.cmdb.tasks.display_field_backfill.backfill_cmdb_display_fields` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/display_field_backfill.py:83](../server/apps/cmdb/tasks/display_field_backfill.py#L83) |
| `apps.cmdb.tasks.node_mgmt_sync.recover_node_mgmt_sync` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/cmdb/tasks/node_mgmt_sync.py:69](../server/apps/cmdb/tasks/node_mgmt_sync.py#L69) |
| `apps.cmdb.tasks.node_mgmt_sync.watch_node_mgmt_sync_recovery` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/cmdb/tasks/node_mgmt_sync.py:107](../server/apps/cmdb/tasks/node_mgmt_sync.py#L107) |
| `apps.cmdb.tasks.transfer.cleanup_transfers` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/transfer.py:34](../server/apps/cmdb/tasks/transfer.py#L34) |
| `apps.cmdb.tasks.transfer.execute_transfer` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/transfer.py:24](../server/apps/cmdb/tasks/transfer.py#L24) |
| `apps.cmdb.tasks.transfer.maintain_transfers` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/cmdb/tasks/transfer.py:29](../server/apps/cmdb/tasks/transfer.py#L29) |
| `apps.cmdb.tasks.uuid_migration.migrate_cmdb_instance_uuid_runtime` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/cmdb/tasks/uuid_migration.py:72](../server/apps/cmdb/tasks/uuid_migration.py#L72) |
| `apps.core.tasks.auditlog_flush_task.clear_audit_logs` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/core/tasks/auditlog_flush_task.py:9](../server/apps/core/tasks/auditlog_flush_task.py#L9) |
| `apps.job_mgmt.tasks.cleanup_expired_distribution_files_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/job_mgmt/tasks.py:339](../server/apps/job_mgmt/tasks.py#L339) |
| `apps.job_mgmt.tasks.deliver_job_completion_outbox` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/job_mgmt/tasks.py:116](../server/apps/job_mgmt/tasks.py#L116) |
| `apps.job_mgmt.tasks.dispatch_pending_job_completion_outbox` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/job_mgmt/tasks.py:124](../server/apps/job_mgmt/tasks.py#L124) |
| `apps.job_mgmt.tasks.distribute_files_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/job_mgmt/tasks.py:46](../server/apps/job_mgmt/tasks.py#L46) |
| `apps.job_mgmt.tasks.do_callback_task` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/job_mgmt/tasks.py:450](../server/apps/job_mgmt/tasks.py#L450) |
| `apps.job_mgmt.tasks.do_nats_callback_task` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/job_mgmt/tasks.py:497](../server/apps/job_mgmt/tasks.py#L497) |
| `apps.job_mgmt.tasks.execute_playbook_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/job_mgmt/tasks.py:51](../server/apps/job_mgmt/tasks.py#L51) |
| `apps.job_mgmt.tasks.execute_scheduled_task` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/job_mgmt/tasks.py:179](../server/apps/job_mgmt/tasks.py#L179) |
| `apps.job_mgmt.tasks.execute_script_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/job_mgmt/tasks.py:41](../server/apps/job_mgmt/tasks.py#L41) |
| `apps.job_mgmt.tasks.finalize_cancelling_execution` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/job_mgmt/tasks.py:57](../server/apps/job_mgmt/tasks.py#L57) |
| `apps.log.tasks.extractor.publish_system_vector_config` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/log/tasks/extractor.py:13](../server/apps/log/tasks/extractor.py#L13) |
| `apps.log.tasks.policy.compensate_log_notice_task` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/log/tasks/policy.py:161](../server/apps/log/tasks/policy.py#L161) |
| `apps.log.tasks.policy.scan_log_policy_task` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/log/tasks/policy.py:57](../server/apps/log/tasks/policy.py#L57) |
| `apps.mlops.tasks.anomaly_detection.publish_dataset_release_async` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/anomaly_detection.py:96](../server/apps/mlops/tasks/anomaly_detection.py#L96) |
| `apps.mlops.tasks.classification.publish_dataset_release_async` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/classification.py:68](../server/apps/mlops/tasks/classification.py#L68) |
| `apps.mlops.tasks.external_resource_cleanup.cleanup_external_resource` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/external_resource_cleanup.py:21](../server/apps/mlops/tasks/external_resource_cleanup.py#L21) |
| `apps.mlops.tasks.external_resource_cleanup.dispatch_pending_external_resource_cleanup` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/external_resource_cleanup.py:88](../server/apps/mlops/tasks/external_resource_cleanup.py#L88) |
| `apps.mlops.tasks.file_cleanup.cleanup_train_data_file` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/file_cleanup.py:16](../server/apps/mlops/tasks/file_cleanup.py#L16) |
| `apps.mlops.tasks.image_classification.publish_dataset_release_async` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/image_classification.py:41](../server/apps/mlops/tasks/image_classification.py#L41) |
| `apps.mlops.tasks.log_clustering.publish_dataset_release_async` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/log_clustering.py:72](../server/apps/mlops/tasks/log_clustering.py#L72) |
| `apps.mlops.tasks.object_detection.publish_dataset_release_async` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/object_detection.py:195](../server/apps/mlops/tasks/object_detection.py#L195) |
| `apps.mlops.tasks.poll_train_job_status.poll_train_job_status` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/poll_train_job_status.py:23](../server/apps/mlops/tasks/poll_train_job_status.py#L23) |
| `apps.mlops.tasks.runtime_cleanup.bootstrap_timeseries_runtime_cleanup` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/runtime_cleanup.py:43](../server/apps/mlops/tasks/runtime_cleanup.py#L43) |
| `apps.mlops.tasks.runtime_cleanup.cleanup_orphan_timeseries_runtime` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/runtime_cleanup.py:20](../server/apps/mlops/tasks/runtime_cleanup.py#L20) |
| `apps.mlops.tasks.runtime_cleanup.dispatch_pending_timeseries_runtime_cleanup` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/runtime_cleanup.py:70](../server/apps/mlops/tasks/runtime_cleanup.py#L70) |
| `apps.mlops.tasks.timeseries.publish_dataset_release_async` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/mlops/tasks/timeseries.py:72](../server/apps/mlops/tasks/timeseries.py#L72) |
| `apps.module_link.tasks.recycle_expired_cmdb_monitor_tasks` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/module_link/tasks.py:12](../server/apps/module_link/tasks.py#L12) |
| `apps.monitor.tasks.collect_detect.purge_collect_detect_terminal_tasks` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/monitor/tasks/collect_detect.py:12](../server/apps/monitor/tasks/collect_detect.py#L12) |
| `apps.monitor.tasks.collect_detect.run_collect_detect_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/monitor/tasks/collect_detect.py:7](../server/apps/monitor/tasks/collect_detect.py#L7) |
| `apps.monitor.tasks.grouping_rule.discover_child_instances` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/monitor/tasks/grouping_rule.py:22](../server/apps/monitor/tasks/grouping_rule.py#L22) |
| `apps.monitor.tasks.grouping_rule.sync_instance_and_group` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/monitor/tasks/grouping_rule.py:9](../server/apps/monitor/tasks/grouping_rule.py#L9) |
| `apps.monitor.tasks.monitor_policy.deliver_alert_center_lifecycle_delivery` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/monitor/tasks/monitor_policy.py:242](../server/apps/monitor/tasks/monitor_policy.py#L242) |
| `apps.monitor.tasks.monitor_policy.retry_alert_center_lifecycle_notify_task` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/monitor/tasks/monitor_policy.py:142](../server/apps/monitor/tasks/monitor_policy.py#L142) |
| `apps.monitor.tasks.monitor_policy.scan_policy_task` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/monitor/tasks/monitor_policy.py:30](../server/apps/monitor/tasks/monitor_policy.py#L30) |
| `apps.monitor.tasks.snmp_ifmib_reconcile.reconcile_snmp_interface_filters` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/monitor/tasks/snmp_ifmib_reconcile.py:15](../server/apps/monitor/tasks/snmp_ifmib_reconcile.py#L15) |
| `apps.monitor.tasks.vault_credential.reconcile_vault_credentials_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/monitor/tasks/vault_credential.py:12](../server/apps/monitor/tasks/vault_credential.py#L12) |
| `apps.monitor.tasks.vault_credential.refresh_vault_credential_refs` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/monitor/tasks/vault_credential.py:7](../server/apps/monitor/tasks/vault_credential.py#L7) |
| `apps.node_mgmt.tasks.action_task.converge_collector_action_task_for_node` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/node_mgmt/tasks/action_task.py:271](../server/apps/node_mgmt/tasks/action_task.py#L271) |
| `apps.node_mgmt.tasks.action_task.timeout_collector_action_task` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/node_mgmt/tasks/action_task.py:279](../server/apps/node_mgmt/tasks/action_task.py#L279) |
| `apps.node_mgmt.tasks.cloudregion.check_all_region_services` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/node_mgmt/tasks/cloudregion.py:9](../server/apps/node_mgmt/tasks/cloudregion.py#L9) |
| `apps.node_mgmt.tasks.collector_auto_restart.restart_failed_collectors` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/node_mgmt/tasks/collector_auto_restart.py:170](../server/apps/node_mgmt/tasks/collector_auto_restart.py#L170) |
| `apps.node_mgmt.tasks.collector_default_backfill.backfill_collector_default_configs` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/node_mgmt/tasks/collector_default_backfill.py:190](../server/apps/node_mgmt/tasks/collector_default_backfill.py#L190) |
| `apps.node_mgmt.tasks.installer.converge_controller_install_connectivity_for_node` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/node_mgmt/tasks/installer.py:1196](../server/apps/node_mgmt/tasks/installer.py#L1196) |
| `apps.node_mgmt.tasks.installer.install_collector` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/node_mgmt/tasks/installer.py:1533](../server/apps/node_mgmt/tasks/installer.py#L1533) |
| `apps.node_mgmt.tasks.installer.install_controller` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/node_mgmt/tasks/installer.py:1053](../server/apps/node_mgmt/tasks/installer.py#L1053) |
| `apps.node_mgmt.tasks.installer.install_controller_for_node` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/node_mgmt/tasks/installer.py:1069](../server/apps/node_mgmt/tasks/installer.py#L1069) |
| `apps.node_mgmt.tasks.installer.retry_controller` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/node_mgmt/tasks/installer.py:1285](../server/apps/node_mgmt/tasks/installer.py#L1285) |
| `apps.node_mgmt.tasks.installer.timeout_controller_install_task` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/node_mgmt/tasks/installer.py:1205](../server/apps/node_mgmt/tasks/installer.py#L1205) |
| `apps.node_mgmt.tasks.installer.uninstall_collector` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/node_mgmt/tasks/installer.py:1715](../server/apps/node_mgmt/tasks/installer.py#L1715) |
| `apps.node_mgmt.tasks.installer.uninstall_controller` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/node_mgmt/tasks/installer.py:1404](../server/apps/node_mgmt/tasks/installer.py#L1404) |
| `apps.node_mgmt.tasks.sidecar_config.sync_node_properties_to_sidecar` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/node_mgmt/tasks/sidecar_config.py:8](../server/apps/node_mgmt/tasks/sidecar_config.py#L8) |
| `apps.node_mgmt.tasks.sidecar_config.sync_nodes_organizations_to_sidecar` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/node_mgmt/tasks/sidecar_config.py:35](../server/apps/node_mgmt/tasks/sidecar_config.py#L35) |
| `apps.node_mgmt.tasks.version_discovery.discover_node_versions` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/node_mgmt/tasks/version_discovery.py:18](../server/apps/node_mgmt/tasks/version_discovery.py#L18) |
| `apps.opspilot.tasks.chat_flow_celery_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/opspilot/tasks/chatflow.py:10](../server/apps/opspilot/tasks/chatflow.py#L10) |
| `apps.opspilot.tasks.chat_flow_test_execute_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/opspilot/tasks/chatflow.py:41](../server/apps/opspilot/tasks/chatflow.py#L41) |
| `apps.opspilot.tasks.cleanup_chat_attachments_task` | opspilot_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/chat_attachment.py:22](../server/apps/opspilot/tasks/chat_attachment.py#L22) |
| `apps.opspilot.tasks.cleanup_expired_workflow_attachments_task` | opspilot_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/memory.py:963](../server/apps/opspilot/tasks/memory.py#L963) |
| `apps.opspilot.tasks.flush_all_pending_memory_write_cache` | opspilot_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/memory.py:410](../server/apps/opspilot/tasks/memory.py#L410) |
| `apps.opspilot.tasks.flush_idle_skill_conversation_memory` | opspilot_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/memory.py:1089](../server/apps/opspilot/tasks/memory.py#L1089) |
| `apps.opspilot.tasks.flush_memory_write_cache_for_node` | opspilot_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/memory.py:377](../server/apps/opspilot/tasks/memory.py#L377) |
| `apps.opspilot.tasks.parse_chat_attachment` | opspilot_chat_parse | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/chat_attachment.py:14](../server/apps/opspilot/tasks/chat_attachment.py#L14) |
| `apps.opspilot.tasks.process_dingtalk_message` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:78](../server/apps/opspilot/tasks/channel.py#L78) |
| `apps.opspilot.tasks.process_enterprise_wechat_aibot_message` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:31](../server/apps/opspilot/tasks/channel.py#L31) |
| `apps.opspilot.tasks.process_enterprise_wechat_aibot_reply` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:64](../server/apps/opspilot/tasks/channel.py#L64) |
| `apps.opspilot.tasks.process_memory_write` | opspilot_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/memory.py:937](../server/apps/opspilot/tasks/memory.py#L937) |
| `apps.opspilot.tasks.process_memory_write_cache` | opspilot_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/memory.py:288](../server/apps/opspilot/tasks/memory.py#L288) |
| `apps.opspilot.tasks.process_skill_channel_aibot_message` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:173](../server/apps/opspilot/tasks/channel.py#L173) |
| `apps.opspilot.tasks.process_skill_channel_aibot_reply` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:253](../server/apps/opspilot/tasks/channel.py#L253) |
| `apps.opspilot.tasks.process_skill_channel_dingtalk_message` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:391](../server/apps/opspilot/tasks/channel.py#L391) |
| `apps.opspilot.tasks.process_skill_channel_feishu_message` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:446](../server/apps/opspilot/tasks/channel.py#L446) |
| `apps.opspilot.tasks.process_skill_channel_im_message` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:152](../server/apps/opspilot/tasks/channel.py#L152) |
| `apps.opspilot.tasks.process_skill_channel_wechat_message` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:279](../server/apps/opspilot/tasks/channel.py#L279) |
| `apps.opspilot.tasks.process_skill_channel_wechat_official_message` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:337](../server/apps/opspilot/tasks/channel.py#L337) |
| `apps.opspilot.tasks.process_wechat_message` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:8](../server/apps/opspilot/tasks/channel.py#L8) |
| `apps.opspilot.tasks.process_wechat_official_message` | opspilot_channel | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/channel.py:131](../server/apps/opspilot/tasks/channel.py#L131) |
| `apps.opspilot.tasks.wiki_batch_ingest_materials_task` | opspilot_wiki | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/wiki.py:747](../server/apps/opspilot/tasks/wiki.py#L747) |
| `apps.opspilot.tasks.wiki_build_material_task` | opspilot_wiki | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/wiki.py:315](../server/apps/opspilot/tasks/wiki.py#L315) |
| `apps.opspilot.tasks.wiki_enrich_markdown_import_search_task` | opspilot_wiki | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/wiki.py:1053](../server/apps/opspilot/tasks/wiki.py#L1053) |
| `apps.opspilot.tasks.wiki_execute_markdown_import_task` | opspilot_wiki | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/wiki.py:876](../server/apps/opspilot/tasks/wiki.py#L876) |
| `apps.opspilot.tasks.wiki_ingest_material_task` | opspilot_wiki | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/wiki.py:213](../server/apps/opspilot/tasks/wiki.py#L213) |
| `apps.opspilot.tasks.wiki_process_kb_material_builds_task` | opspilot_wiki | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/wiki.py:734](../server/apps/opspilot/tasks/wiki.py#L734) |
| `apps.opspilot.tasks.wiki_propose_update_task` | opspilot_wiki | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/wiki.py:579](../server/apps/opspilot/tasks/wiki.py#L579) |
| `apps.opspilot.tasks.wiki_rebuild_kb_task` | opspilot_wiki | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/wiki.py:625](../server/apps/opspilot/tasks/wiki.py#L625) |
| `apps.opspilot.tasks.wiki_refresh_web_materials_task` | opspilot_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/wiki.py:1066](../server/apps/opspilot/tasks/wiki.py#L1066) |
| `apps.opspilot.tasks.wiki_retry_markdown_import_task` | opspilot_wiki | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/wiki.py:780](../server/apps/opspilot/tasks/wiki.py#L780) |
| `apps.opspilot.tasks.write_skill_conversation_memory` | opspilot_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/opspilot/tasks/memory.py:1050](../server/apps/opspilot/tasks/memory.py#L1050) |
| `apps.patch_mgmt.tasks.check_patch_source_connectivity` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/patch_mgmt/tasks.py:30](../server/apps/patch_mgmt/tasks.py#L30) |
| `apps.patch_mgmt.tasks.execute_governance_host` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/patch_mgmt/tasks.py:480](../server/apps/patch_mgmt/tasks.py#L480) |
| `apps.patch_mgmt.tasks.execute_governance_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/patch_mgmt/tasks.py:367](../server/apps/patch_mgmt/tasks.py#L367) |
| `apps.patch_mgmt.tasks.ingest_patch_source` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/patch_mgmt/tasks.py:706](../server/apps/patch_mgmt/tasks.py#L706) |
| `apps.patch_mgmt.tasks.probe_target_connectivity` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/patch_mgmt/tasks.py:758](../server/apps/patch_mgmt/tasks.py#L758) |
| `apps.patch_mgmt.tasks.reconcile_assessment_notification_deliveries` | patch_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/patch_mgmt/tasks.py:304](../server/apps/patch_mgmt/tasks.py#L304) |
| `apps.patch_mgmt.tasks.reconcile_governance_host` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/patch_mgmt/tasks.py:565](../server/apps/patch_mgmt/tasks.py#L565) |
| `apps.patch_mgmt.tasks.run_periodic_compliance_scan` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/patch_mgmt/tasks.py:92](../server/apps/patch_mgmt/tasks.py#L92) |
| `apps.patch_mgmt.tasks.send_assessment_notification_delivery` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/patch_mgmt/tasks.py:163](../server/apps/patch_mgmt/tasks.py#L163) |
| `apps.patch_mgmt.tasks.verify_pending_reboot_hosts` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/patch_mgmt/tasks.py:832](../server/apps/patch_mgmt/tasks.py#L832) |
| `apps.patch_mgmt.tasks.watch_governance_timeouts` | patch_maintenance | 既有显式专用队列，保留原消费边界 | [server/apps/patch_mgmt/tasks.py:573](../server/apps/patch_mgmt/tasks.py#L573) |
| `apps.rum.tasks.deliver_rum_alert_outbox` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/rum/tasks.py:73](../server/apps/rum/tasks.py#L73) |
| `apps.rum.tasks.dispatch_rum_policy_evaluations` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/rum/tasks.py:38](../server/apps/rum/tasks.py#L38) |
| `apps.rum.tasks.evaluate_rum_alert_policy` | critical | 检测/告警生命周期，优先保证执行槽 | [server/apps/rum/tasks.py:61](../server/apps/rum/tasks.py#L61) |
| `apps.rum.tasks.publish_pending_rum_outbox` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/rum/tasks.py:84](../server/apps/rum/tasks.py#L84) |
| `apps.rum.tasks.reconcile_rum_projection` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/rum/tasks.py:114](../server/apps/rum/tasks.py#L114) |
| `apps.system_mgmt.tasks.check_password_expiry_and_notify` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/system_mgmt/tasks.py:279](../server/apps/system_mgmt/tasks.py#L279) |
| `apps.system_mgmt.tasks.execute_im_notification_sync_run_task` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/system_mgmt/tasks.py:364](../server/apps/system_mgmt/tasks.py#L364) |
| `apps.system_mgmt.tasks.execute_user_sync_source` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/system_mgmt/tasks.py:343](../server/apps/system_mgmt/tasks.py#L343) |
| `apps.system_mgmt.tasks.recover_stuck_initial_password_email_batches` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/system_mgmt/tasks.py:495](../server/apps/system_mgmt/tasks.py#L495) |
| `apps.system_mgmt.tasks.schedule_im_notification_sync` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/system_mgmt/tasks.py:350](../server/apps/system_mgmt/tasks.py#L350) |
| `apps.system_mgmt.tasks.send_initial_password_email` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/system_mgmt/tasks.py:382](../server/apps/system_mgmt/tasks.py#L382) |
| `apps.system_mgmt.tasks.send_initial_password_email_batch` | notification | 通知或 outbox 交付，外部 I/O 可能慢 | [server/apps/system_mgmt/tasks.py:441](../server/apps/system_mgmt/tasks.py#L441) |
| `apps.system_mgmt.tasks.sync_user_and_group_by_login_module` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/system_mgmt/tasks.py:50](../server/apps/system_mgmt/tasks.py#L50) |
| `apps.system_mgmt.tasks.write_error_log_async` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/system_mgmt/tasks.py:22](../server/apps/system_mgmt/tasks.py#L22) |
| `operation_analysis.cleanup_expired_dashboard_report_executions` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/operation_analysis/tasks/tasks.py:103](../server/apps/operation_analysis/tasks/tasks.py#L103) |
| `operation_analysis.cleanup_expired_dashboard_report_pdf_artifacts` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/operation_analysis/tasks/tasks.py:88](../server/apps/operation_analysis/tasks/tasks.py#L88) |
| `operation_analysis.converge_timed_out_dashboard_report_executions` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/operation_analysis/tasks/tasks.py:72](../server/apps/operation_analysis/tasks/tasks.py#L72) |
| `operation_analysis.materialize_excel_candidate` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/operation_analysis/tasks/tasks.py:118](../server/apps/operation_analysis/tasks/tasks.py#L118) |
| `operation_analysis.render_dashboard_report` | dashboard_report_render | 既有显式专用队列，保留原消费边界 | [server/apps/operation_analysis/tasks/tasks.py:32](../server/apps/operation_analysis/tasks/tasks.py#L32) |
| `operation_analysis.rescan_pending_excel_materializations` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/operation_analysis/tasks/tasks.py:220](../server/apps/operation_analysis/tasks/tasks.py#L220) |
| `operation_analysis.resubmit_excel_from_saved_source` | background | 导入导出、采集、批处理或低时效维护，隔离长任务 | [server/apps/operation_analysis/tasks/tasks.py:129](../server/apps/operation_analysis/tasks/tasks.py#L129) |
| `operation_analysis.scan_due_dashboard_report_subscriptions` | state | 状态收敛/补偿，可能集中高频触发 | [server/apps/operation_analysis/tasks/tasks.py:56](../server/apps/operation_analysis/tasks/tasks.py#L56) |
