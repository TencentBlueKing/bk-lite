"""operation_analysis 测试共享 fixtures。"""

import pytest


@pytest.fixture(autouse=True)
def _disable_license_guard(settings):
    """关闭 license 守卫，让 HTTP 层测试穿过中间件。

    运营分析接口受 LicenseAppGuardMiddleware 拦截：测试环境无 license 时
    get_licensed_names() 为空会直接 403。LICENSE_MGMT_ENABLED=False 时短路放行，
    专注验证视图自身的组织可见性与功能权限；许可逻辑由 license_mgmt 自测覆盖。
    """
    settings.LICENSE_MGMT_ENABLED = False
