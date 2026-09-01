import pytest

MONITOR_ADMIN_WRITE_PERMISSIONS = {
    "object-Add",
    "object-Edit",
    "object-Delete",
    "integration_metric-Add Group",
    "integration_metric-Edit Group",
    "integration_metric-Delete Group",
    "integration_metric-Add Metric",
    "integration_metric-Edit Metric",
    "integration_metric-Delete Metric",
    "strategy_list-Add",
    "strategy_list-Edit",
    "strategy_list-Delete",
}


@pytest.fixture(autouse=True)
def grant_monitor_admin_write_permissions(request):
    """让全局 api_client 的 admin 测试用户具备既有 Monitor 写权限。"""
    if "api_client" not in request.fixturenames:
        return
    user = request.getfixturevalue("authenticated_user")
    if "admin" in (getattr(user, "roles", None) or []):
        user.permission = {"monitor": set(MONITOR_ADMIN_WRITE_PERMISSIONS)}
