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
}
