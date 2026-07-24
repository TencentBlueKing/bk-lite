"""patch_mgmt 测试共享 fixtures。

当前状态（Todo 3 / MVP 阶段）：
  - Todo 2 完成了 schema 测试；schema 测试无需 license/auth fixtures。
  - Todo 4-8 将引入 views / services；届时 view 层测试需要
    ``_disable_license_guard``（参照 job_mgmt/tests/conftest.py）。

为何当前保持极简并预置 _disable_license_guard：
  1. 全局 conftest.py 已提供 ``api_client``、``authenticated_user``、
     ``request_factory``，schema/harness 测试直接使用。
  2. 全局 conftest.py 的 ``disable_auth_middleware``（autouse）已去除
     AuthMiddleware / APISecretMiddleware。
  3. LicenseAppGuardMiddleware 在企业版 footprint 存在时才加载；
     测试环境通常无 footprint，但无法保证所有 CI 环境一致。
     预置 _disable_license_guard（autouse=True）遵循 job_mgmt 惯例，
     使所有 patch_mgmt 测试（含未来 view 测试）统一短路该守卫，
     专注于业务逻辑验证，许可逻辑由 license_mgmt 自测覆盖。
  4. 当前无 view 层，fixture 为零成本预置（仅覆写一个 settings 值）。

未来 Todo 4-8 添加 view 测试时：
  - 如需超管 + team cookie：参照 job_mgmt 添加 ``su_client`` fixture。
  - 如需特定 patch_mgmt 权限角色：在此扩展，无需改动全局 conftest.py。
"""

import pytest


@pytest.fixture(autouse=True)
def _disable_license_guard(settings):
    """关闭 license 守卫，让 view 层 HTTP 测试穿过中间件。

    与 job_mgmt/tests/conftest.py 保持一致的 autouse 惯例：
    当前 schema/harness 测试不受影响（仅写入一个 settings 值）；
    未来 view 测试自动获得该绕过，无需各测试类单独声明。
    """
    settings.LICENSE_MGMT_ENABLED = False


@pytest.fixture(autouse=True)
def _use_executor_for_windows(settings):
    """测试默认经由生产执行器下发 Windows 命令。

    本地 ``.env`` 可显式启用 ``direct_winrm`` 跑真实闭环，但不应让
    开发者的私有配置改变测试路由或触发真实 WinRM 连接。
    """
    settings.PATCH_MGMT_WINDOWS_EXECUTION_MODE = 'executor'


@pytest.fixture
def su_client(api_client, authenticated_user, monkeypatch):
    """超管 + current_team=1 cookie 的 APIClient。

    用于 view 层测试穿过 @HasPermission 鉴权与 AuthViewSet 的团队过滤
    （数据权限 RPC 外部边界固定返回团队 1 规则）。
    设为实例属性即可被请求内的 request.user 读取，无需落库。
    """
    authenticated_user.is_superuser = True
    api_client.cookies["current_team"] = "1"
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *_args, **_kwargs: {"team": [1], "instance": []},
    )
    return api_client
