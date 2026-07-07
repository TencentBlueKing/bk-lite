"""opspilot 测试共享 fixtures。"""

import pytest


@pytest.fixture(autouse=True)
def _disable_license_guard(settings):
    """关闭 license 守卫,让 ``_views`` 层 HTTP 测试穿过中间件。

    opspilot 的接口受 ``LicenseAppGuardMiddleware`` 拦截:未授权模块直接 403
    (测试环境 DummyCache + 测试 DB 无 LicenseRecord,``get_licensed_names()``
    永远为空)。该中间件在 ``LICENSE_MGMT_ENABLED`` 为假时短路放行,故测试内置否
    该开关即可绕过,专注验证视图自身的鉴权/序列化/业务逻辑。许可逻辑由
    license_mgmt 自测覆盖。
    """
    settings.LICENSE_MGMT_ENABLED = False
