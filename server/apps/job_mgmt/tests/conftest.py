"""job_mgmt 测试共享 fixtures。"""

import pytest


@pytest.fixture(autouse=True)
def _disable_license_guard(settings):
    """关闭 license 守卫，让 ``_views`` 层 HTTP 测试穿过中间件。

    job_mgmt 的接口受 ``LicenseAppGuardMiddleware`` 拦截：未授权模块直接 403
    （测试环境无 license → ``get_licensed_names()`` 为空）。该中间件在
    ``LICENSE_MGMT_ENABLED`` 为假时短路放行，故测试内置否该开关即可绕过，
    专注验证视图自身的鉴权/序列化/业务逻辑。许可逻辑由 license_mgmt 自测覆盖。
    """
    settings.LICENSE_MGMT_ENABLED = False


@pytest.fixture
def su_client(api_client, authenticated_user):
    """超管 + current_team=1 cookie 的 APIClient。

    用于 ``_views`` 层测试穿过 ``@HasPermission`` 鉴权与 ``AuthViewSet`` 的团队过滤
    （超管在 create/retrieve/update/destroy 路径上跳过团队/实例级校验）。
    设为实例属性即可被请求内的 ``request.user`` 读取，无需落库。
    """
    authenticated_user.is_superuser = True
    api_client.cookies["current_team"] = "1"
    return api_client
