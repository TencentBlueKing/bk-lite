"""双租户测试覆盖登记表（安全红线 4 的机械化门禁）。

每个 @openapi_expose 暴露的端点必须在此登记其双租户 / 注入行为测试的
完整引用（"模块路径::测试函数名"）。test_governance.py 会校验：
1. 注册表中每个端点都有登记；
2. 每条登记的测试函数真实存在。

新暴露端点而未登记、或登记的测试被删除，pytest 即失败，合并被拒。
team_free 端点登记其「响应不含组织字段」断言测试。
"""

TENANT_ISOLATION_COVERAGE = {
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
}
