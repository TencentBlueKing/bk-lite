"""双租户测试覆盖登记表（安全红线 4 的机械化门禁）。

每个 @openapi_expose 暴露的端点必须在此登记其双租户 / 注入行为测试的
完整引用（"模块路径::测试函数名"）。test_governance.py 会校验：
1. 注册表中每个端点都有登记；
2. 每条登记的测试函数真实存在。

新暴露端点而未登记、或登记的测试被删除，pytest 即失败，合并被拒。
team_free 端点登记其「响应不含组织字段」断言测试。
"""

TENANT_ISOLATION_COVERAGE = {
    "workflow/trigger": [
        "apps.workflow.tests.test_trigger_entrypoints::test_openapi_trigger_uses_trusted_team_and_rejects_other_tenant",
    ],
    "workflow/webhook-test": [
        "apps.workflow.tests.test_trigger_entrypoints::test_webhook_test_session_captures_body_only_for_its_tenant",
    ],
    "patch-mgmt/module-data": [
        "apps.core.openapi.tests.test_gateway::test_tenant_can_read_own_org",
        "apps.core.openapi.tests.test_gateway::test_tenant_cannot_read_other_org",
        "apps.core.openapi.tests.test_gateway::test_forged_identity_headers_ignored",
    ],
    # cmdb 为锚点式注入：数据层隔离由函数自身现有权限逻辑承担（m1-notes.md），
    # 网关侧登记注入行为验证（锚点强制覆盖 / 透传 / 缺失拒绝）
    "cmdb/module-data": [
        "apps.core.openapi.tests.test_gateway::test_api_token_anchor_forced_to_bound_team",
        "apps.core.openapi.tests.test_gateway::test_jwt_anchor_passthrough",
        "apps.core.openapi.tests.test_gateway::test_jwt_missing_anchor_rejected",
    ],
    "cmdb/instances": [
        "apps.cmdb.tests.test_openapi_instance_list::test_api_tenant_can_list_own_org_instances",
        "apps.cmdb.tests.test_openapi_instance_list::test_api_tenant_cannot_list_other_org_instances",
        "apps.cmdb.tests.test_openapi_instance_list::test_forged_team_is_rejected",
        "apps.core.openapi.tests.test_system_token_tenant::test_system_tenant_can_list_own_org_instances",
        "apps.core.openapi.tests.test_system_token_tenant::test_system_tenant_cannot_list_other_org_instances",
        "apps.core.openapi.tests.test_system_token_tenant::test_system_tenant_forged_acting_team_is_rejected",
    ],
    "cmdb/classifications": [
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_api_tenant_can_list_own_classifications",
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_api_tenant_cannot_list_other_org_classifications",
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_classifications_forged_team_is_rejected",
    ],
    "cmdb/models": [
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_api_tenant_can_list_own_models",
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_api_tenant_cannot_list_other_org_models",
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_models_forged_team_is_rejected",
    ],
    "cmdb/model": [
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_api_tenant_can_read_own_model",
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_api_tenant_cannot_read_other_org_model",
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_model_forged_team_is_rejected",
    ],
    "cmdb/model-attributes": [
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_api_tenant_can_read_own_model_attributes",
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_api_tenant_cannot_read_other_org_model_attributes",
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_model_attributes_forged_team_is_rejected",
    ],
    "cmdb/model-associations": [
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_api_tenant_can_read_own_model_associations",
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_api_tenant_cannot_read_other_org_model_associations",
        "apps.cmdb.tests.test_openapi_cmdb_catalog::test_model_associations_forged_team_is_rejected",
    ],
    "cmdb/instance-create": [
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_can_create_instance_in_own_org",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_create_does_not_belong_to_other_org",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_instance_create_forged_team_is_rejected",
        "apps.core.openapi.tests.test_system_token_tenant::test_system_tenant_can_create_instance_in_own_org",
        "apps.core.openapi.tests.test_system_token_tenant::test_system_tenant_create_does_not_belong_to_other_org",
    ],
    "cmdb/instance": [
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_can_read_own_instance",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_cannot_read_other_org_instance",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_instance_forged_team_is_rejected",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_can_update_own_instance",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_cannot_update_other_org_instance",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_can_delete_own_instance",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_cannot_delete_other_org_instance",
    ],
    "cmdb/instance-batch-create": [
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_can_batch_create_in_own_org",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_batch_create_does_not_belong_to_other_org",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_batch_create_forged_team_is_rejected",
    ],
    "cmdb/instance-batch-update": [
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_can_batch_update_own_instances",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_cannot_batch_update_other_org_instances",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_batch_update_forged_team_is_rejected",
    ],
    "cmdb/instance-batch-delete": [
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_can_batch_delete_own_instances",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_cannot_batch_delete_other_org_instances",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_batch_delete_forged_team_is_rejected",
    ],
    "cmdb/instance-associations": [
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_can_list_own_instance_associations",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_cannot_list_other_org_instance_associations",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_instance_associations_forged_team_is_rejected",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_can_create_association_in_own_org",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_cannot_create_association_to_other_org_instance",
    ],
    "cmdb/instance-association": [
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_can_delete_own_association",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_api_tenant_cannot_delete_other_org_association",
        "apps.cmdb.tests.test_openapi_cmdb_mutations::test_association_delete_forged_team_is_rejected",
    ],
    "job-mgmt/file-distribute": [
        "apps.job_mgmt.tests.test_open_file_distribute_views::test_api_tenant_can_distribute_own_file",
        "apps.job_mgmt.tests.test_open_file_distribute_views::test_api_tenant_cannot_distribute_other_tenant_file",
        "apps.job_mgmt.tests.test_open_file_distribute_views::test_forged_team_is_rejected_without_side_effects",
    ],
    "job-mgmt/targets-v2": [
        "apps.job_mgmt.tests.test_open_file_distribute_views::test_target_list_v2_tenant_reads_only_own_targets",
        "apps.job_mgmt.tests.test_open_file_distribute_views::test_target_list_v2_other_tenant_cannot_read_first_tenant_targets",
        "apps.job_mgmt.tests.test_open_file_distribute_views::test_target_list_v2_rejects_forged_team",
    ],
    "job-mgmt/script-execute": [
        "apps.job_mgmt.tests.test_openapi_job_execute::test_api_tenant_can_execute_script_on_own_target",
        "apps.job_mgmt.tests.test_openapi_job_execute::test_api_tenant_cannot_execute_script_on_other_tenant_target",
        "apps.job_mgmt.tests.test_openapi_job_execute::test_script_execute_forged_team_is_rejected",
    ],
    "job-mgmt/job-status": [
        "apps.job_mgmt.tests.test_openapi_job_execute::test_api_tenant_can_read_own_job_status",
        "apps.job_mgmt.tests.test_openapi_job_execute::test_api_tenant_cannot_read_other_org_job_status",
        "apps.job_mgmt.tests.test_openapi_job_execute::test_job_status_forged_team_is_rejected",
    ],
    "job-mgmt/job-detail": [
        "apps.job_mgmt.tests.test_openapi_job_execute::test_api_tenant_can_read_own_job_detail",
        "apps.job_mgmt.tests.test_openapi_job_execute::test_api_tenant_cannot_read_other_org_job_detail",
        "apps.job_mgmt.tests.test_openapi_job_execute::test_job_detail_forged_team_is_rejected",
    ],
    "alerts/list": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_list_own_org_alerts",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_list_other_org_alerts",
        "apps.alerts.tests.test_openapi_gateway::test_list_forged_team_is_rejected",
    ],
    "alerts/detail": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_read_own_alert",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_read_other_org_alert",
        "apps.alerts.tests.test_openapi_gateway::test_detail_forged_team_is_rejected",
    ],
    "alerts/events": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_list_own_alert_events",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_list_other_org_alert_events",
        "apps.alerts.tests.test_openapi_gateway::test_events_forged_team_is_rejected",
    ],
    "alerts/assign": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_assign_own_alert",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_assign_other_org_alert",
        "apps.alerts.tests.test_openapi_gateway::test_assign_forged_team_is_rejected",
    ],
    "alerts/acknowledge": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_acknowledge_own_alert",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_acknowledge_other_org_alert",
        "apps.alerts.tests.test_openapi_gateway::test_acknowledge_forged_team_is_rejected",
    ],
    "alerts/reassign": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_reassign_own_alert",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_reassign_other_org_alert",
        "apps.alerts.tests.test_openapi_gateway::test_reassign_forged_team_is_rejected",
    ],
    "alerts/close": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_close_own_pending_alert_without_assignee",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_close_other_org_alert",
        "apps.alerts.tests.test_openapi_gateway::test_close_forged_team_is_rejected",
    ],
    "alerts/batch-action": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_batch_close_own_alerts",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_batch_close_other_org_alerts",
        "apps.alerts.tests.test_openapi_gateway::test_batch_action_forged_team_is_rejected",
    ],
    "alerts/shield-create": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_create_shield",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_create_shield_does_not_belong_to_other_org",
        "apps.alerts.tests.test_openapi_gateway::test_shield_create_forged_team_is_rejected",
    ],
    "alerts/shield-operate": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_operate_own_shield",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_operate_other_org_shield",
        "apps.alerts.tests.test_openapi_gateway::test_shield_operate_forged_team_is_rejected",
    ],
    "alerts/shield": [
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_update_own_shield",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_update_other_org_shield",
        "apps.alerts.tests.test_openapi_gateway::test_shield_update_forged_team_is_rejected",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_can_delete_own_shield",
        "apps.alerts.tests.test_openapi_gateway::test_api_tenant_cannot_delete_other_org_shield",
        "apps.alerts.tests.test_openapi_gateway::test_shield_delete_forged_team_is_rejected",
    ],
    "monitor/objects": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_list_visible_objects",
        "apps.monitor.tests.test_openapi_gateway::test_other_tenant_sees_the_same_visible_objects",
        "apps.monitor.tests.test_openapi_gateway::test_objects_forged_team_is_rejected",
    ],
    "monitor/instances": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_list_own_instances",
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_cannot_list_other_org_instances",
        "apps.monitor.tests.test_openapi_gateway::test_instances_forged_team_is_rejected",
    ],
    "monitor/policies": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_list_own_policies",
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_cannot_list_other_org_policies",
        "apps.monitor.tests.test_openapi_gateway::test_policies_forged_team_is_rejected",
    ],
    "monitor/metrics": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_list_metrics_without_query",
        "apps.monitor.tests.test_openapi_gateway::test_hidden_object_metrics_are_rejected",
    ],
    "monitor/metrics/instant": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_query_own_metric_instant",
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_cannot_query_other_org_metric",
        "apps.monitor.tests.test_openapi_gateway::test_metric_query_rejects_raw_query",
    ],
    "monitor/metrics/range": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_cannot_query_other_org_metric_range",
        "apps.monitor.tests.test_openapi_gateway::test_metric_range_rejects_window_over_six_hours",
    ],
    "monitor/plugins": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_list_plugins_and_form",
        "apps.monitor.tests.test_openapi_gateway::test_hidden_object_plugins_are_rejected",
    ],
    "monitor/plugins/form": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_list_plugins_and_form",
    ],
    "monitor/policy-groups": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_list_own_policy_groups",
        "apps.monitor.tests.test_openapi_gateway::test_policy_groups_forged_team_is_rejected",
    ],
    "monitor/integrations": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_save_integration_for_own_node",
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_cannot_save_integration_for_other_org_node",
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_delete_own_integration",
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_cannot_delete_other_org_integration",
        "apps.monitor.tests.test_openapi_gateway::test_delete_integration_forged_team_is_rejected",
    ],
    "monitor/cluster-collectors": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_can_create_kubernetes_collector",
    ],
    "monitor/cluster-collectors/install-command": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_cannot_generate_other_org_cluster_command",
        "apps.monitor.tests.test_openapi_gateway::test_cluster_command_rejects_k3s_tolerations",
    ],
    "monitor/cluster-collectors/status": [
        "apps.monitor.tests.test_openapi_gateway::test_api_tenant_cannot_read_other_org_cluster_status",
    ],
    "node/cloud-regions": [
        "apps.node_mgmt.tests.test_openapi_gateway::test_both_tenants_see_the_same_cloud_regions",
        "apps.node_mgmt.tests.test_openapi_gateway::test_cloud_regions_omit_proxy_address",
        "apps.node_mgmt.tests.test_openapi_gateway::test_cloud_regions_forged_team_is_rejected",
    ],
    "node/nodes": [
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_can_list_own_nodes",
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_cannot_list_other_org_nodes",
        "apps.node_mgmt.tests.test_openapi_gateway::test_nodes_forged_team_is_rejected",
    ],
    "node/packages": [
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_can_list_packages",
    ],
    "node/controllers/install": [
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_can_install_controller_for_own_node",
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_cannot_install_controller_on_other_org_node",
    ],
    "node/controllers/install-command": [
        "apps.node_mgmt.tests.test_openapi_gateway::test_install_command_forged_team_is_rejected",
    ],
    "node/install-tasks": [
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_cannot_read_other_org_install_task",
    ],
    "node/collectors/install": [
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_can_install_collector_on_own_node",
    ],
    "node/collectors/operate": [
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_cannot_operate_other_org_collector",
    ],
    "node/configurations/bind": [
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_can_bind_configuration_on_own_node",
    ],
    "node/nodes/detail": [
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_can_read_own_node_detail",
        "apps.node_mgmt.tests.test_openapi_gateway::test_api_tenant_cannot_read_other_org_node_detail",
        "apps.node_mgmt.tests.test_openapi_gateway::test_node_detail_forged_team_is_rejected",
    ],
    "log/groups": [
        "apps.log.tests.test_openapi_gateway::test_api_tenant_can_list_own_groups",
        "apps.log.tests.test_openapi_gateway::test_groups_forged_team_is_rejected",
    ],
    "log/collect-types": [
        "apps.log.tests.test_openapi_gateway::test_api_tenant_can_list_collect_types",
    ],
    "log/collect-instances": [
        "apps.log.tests.test_openapi_gateway::test_api_tenant_can_create_collect_instance_on_own_node",
        "apps.log.tests.test_openapi_gateway::test_api_tenant_cannot_create_collect_instance_on_other_org_node",
        "apps.log.tests.test_openapi_gateway::test_api_tenant_can_delete_own_collect_instance",
    ],
    "log/collect-instances/config": [
        "apps.log.tests.test_openapi_gateway::test_api_tenant_cannot_update_other_org_collect_config",
    ],
    "log/k8s-collectors": [
        "apps.log.tests.test_openapi_gateway::test_api_tenant_can_create_log_k8s_collector",
    ],
    "log/k8s-collectors/setting": [
        "apps.log.tests.test_openapi_gateway::test_api_tenant_cannot_save_other_org_k8s_setting",
    ],
    "log/k8s-collectors/install-command": [
        "apps.log.tests.test_openapi_gateway::test_k8s_command_forged_team_is_rejected",
    ],
    "log/k8s-collectors/status": [
        "apps.log.tests.test_openapi_gateway::test_api_tenant_cannot_read_other_org_k8s_status",
    ],
    "log/search": [
        "apps.log.tests.test_openapi_gateway::test_api_tenant_can_search_own_group",
        "apps.log.tests.test_openapi_gateway::test_api_tenant_cannot_search_other_org_group",
        "apps.log.tests.test_openapi_gateway::test_search_rejects_window_over_one_hour",
        "apps.log.tests.test_openapi_gateway::test_search_truncates_long_message",
    ],
    "apm/applications": [
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_can_list_own_applications",
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_cannot_list_other_org_applications",
        "apps.apm.tests.test_openapi_gateway::test_applications_forged_team_is_rejected",
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_creates_application_in_own_org",
        "apps.apm.tests.test_openapi_gateway::test_application_create_forged_team_is_rejected",
    ],
    "apm/services": [
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_can_list_own_services",
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_cannot_list_other_org_services",
        "apps.apm.tests.test_openapi_gateway::test_services_forged_team_is_rejected",
    ],
    "apm/instances": [
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_can_list_own_instances",
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_cannot_list_other_org_instances",
        "apps.apm.tests.test_openapi_gateway::test_instances_forged_team_is_rejected",
    ],
    "apm/services/metrics": [
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_can_query_own_service_metrics",
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_cannot_query_other_org_service_metrics",
        "apps.apm.tests.test_openapi_gateway::test_service_metrics_reject_window_over_seven_days",
    ],
    "apm/traces": [
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_can_list_own_traces",
        "apps.apm.tests.test_openapi_gateway::test_traces_reject_window_over_one_hour",
    ],
    "apm/integration-regions": [
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_can_list_integration_regions",
    ],
    "apm/integration-configs": [
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_cannot_render_other_org_integration_config",
    ],
    "apm/traces/detail": [
        "apps.apm.tests.test_openapi_gateway::test_api_tenant_cannot_read_other_org_trace",
    ],
    "system-mgmt/users": [
        "apps.system_mgmt.tests.test_openapi_directory::test_system_tenant_can_read_own_org_users",
        "apps.system_mgmt.tests.test_openapi_directory::test_system_tenant_cannot_read_other_org_users",
        "apps.system_mgmt.tests.test_openapi_directory::test_system_tenant_forged_acting_team_is_rejected",
        "apps.system_mgmt.tests.test_openapi_directory::test_group_id_out_of_scope_is_forbidden",
        "apps.system_mgmt.tests.test_openapi_directory::test_missing_group_id_is_business_rejected",
        "apps.system_mgmt.tests.test_openapi_directory::test_users_exact_query_does_not_leak_invisible_user",
        "apps.system_mgmt.tests.test_openapi_directory::test_users_batch_query_does_not_leak_invisible_users",
        "apps.system_mgmt.tests.test_openapi_directory::test_platform_superuser_reads_all_users_and_full_group_list",
        "apps.system_mgmt.tests.test_openapi_directory::test_app_admin_cannot_read_other_org_users",
    ],
    "system-mgmt/groups": [
        "apps.system_mgmt.tests.test_openapi_directory::test_system_tenant_can_read_own_org_groups",
        "apps.system_mgmt.tests.test_openapi_directory::test_system_tenant_cannot_read_other_org_groups",
        "apps.system_mgmt.tests.test_openapi_directory::test_system_tenant_groups_forged_acting_team_is_rejected",
        "apps.system_mgmt.tests.test_openapi_directory::test_archived_group_id_is_business_rejected",
        "apps.system_mgmt.tests.test_openapi_directory::test_scope_root_parent_id_null_and_preserved_across_pages",
        "apps.system_mgmt.tests.test_openapi_directory::test_include_children_does_not_expand_unauthorized_child",
        "apps.system_mgmt.tests.test_openapi_directory::test_superuser_reads_all_active_groups",
        "apps.system_mgmt.tests.test_openapi_directory::test_app_admin_cannot_read_other_org_groups",
    ],
    "system-mgmt/notification-channels": [
        "apps.system_mgmt.tests.test_openapi_notification_channels::test_system_tenant_lists_own_external_channels_only",
        "apps.system_mgmt.tests.test_openapi_notification_channels::test_other_org_channels_are_not_listed",
        "apps.system_mgmt.tests.test_openapi_notification_channels::test_forged_acting_team_is_rejected",
        "apps.system_mgmt.tests.test_openapi_notification_channels::test_list_without_channel_permission_is_denied",
    ],
    "system-mgmt/notification-channels/send": [
        "apps.system_mgmt.tests.test_openapi_notification_channels::test_system_tenant_sends_through_own_channel",
        "apps.system_mgmt.tests.test_openapi_notification_channels::test_send_other_org_channel_is_forbidden",
        "apps.system_mgmt.tests.test_openapi_notification_channels::test_send_internal_nats_channel_is_rejected",
        "apps.system_mgmt.tests.test_openapi_notification_channels::test_send_recipient_outside_org_is_rejected",
        "apps.system_mgmt.tests.test_openapi_notification_channels::test_send_without_edit_permission_is_denied",
        "apps.system_mgmt.tests.test_openapi_notification_channels::test_send_outside_token_scope_is_denied",
    ],
}
