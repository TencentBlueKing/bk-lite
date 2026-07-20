"""opspilot 测试共享 fixtures。"""

import sys
from unittest.mock import MagicMock

import pytest

# deepagents 第三方包升级后删了 `FILE_NOT_FOUND / FileData / _get_file_type / _glob_search_files`
# 等 API。`apps/opspilot/metis/llm/backends/minio_backend.py` 直接 import 这些,
# production 端在用 minio_backend 链路时也会失败。这里在 conftest 顶部
# 提前用 MagicMock 强制覆盖 `deepagents.backends.*` 子模块占位,让 minio_backend
# 可正常 import——测试只测 ToolsNodes 自身,不被 deepagents API 兼容性阻塞。
# 注意:必须用 `=` 而非 `setdefault`,因为 deepagents.backends.__init__ 会 eager import
# 子模块(`from .protocol import BackendProtocol` 等),`setdefault` 在 eager import
# 之后被真模块占用,不再生效。直接覆盖强制替换。
# 真实修复:重写 minio_backend.py 用新 deepagents API(独立 PR 跟进)。
_deepagents_backends_module = MagicMock(name="deepagents.backends")
_deepagents_backends_module.protocol = MagicMock()
_deepagents_backends_module.utils = MagicMock()
sys.modules["deepagents.backends"] = _deepagents_backends_module
sys.modules["deepagents.backends.protocol"] = _deepagents_backends_module.protocol
sys.modules["deepagents.backends.utils"] = _deepagents_backends_module.utils


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
