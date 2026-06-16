"""job_mgmt 测试共享 fixtures。"""

import pytest


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
