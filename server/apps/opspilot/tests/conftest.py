"""opspilot 测试共享 fixtures。"""

import pytest


@pytest.fixture(autouse=True)
def _inject_required_apps(settings):
    """补齐 opspilot 测试所需的依赖 app。

    1. cmdb:被 metis/llm/tools/cmdb/* 间接 import,cmdb 模型未自带 app_label,
       必须注册到 INSTALLED_APPS 才能 import(否则 pytest 收集期就 13 条
       "Model class ... doesn't declare an explicit app_label" 报错,无法跑测试)。
       生产环境 INSTALLED_APPS 已含 cmdb,这里只在测试环境补一层。
    2. 关闭 license 守卫:让 ``_views`` 层 HTTP 测试穿过中间件。
       LicenseAppGuardMiddleware 在 ``LICENSE_MGMT_ENABLED`` 为假时短路放行;
       测试环境 DummyCache + 测试 DB 无 LicenseRecord,``get_licensed_names()``
       永远为空,必须短路。许可逻辑由 license_mgmt 自测覆盖。
    """
    apps = list(getattr(settings, "INSTALLED_APPS", ()))
    for name in ("apps.cmdb",):
        if name not in apps:
            apps.append(name)
    settings.INSTALLED_APPS = tuple(apps)
    settings.LICENSE_MGMT_ENABLED = False
