"""
Issue #3492: get_is_superuser 路径解析健壮性修复单元测试

测试覆盖：
- 正常 /api/v1/<app>/ 路径正确提取应用名（回归保护）
- 不含 api/v1/ 的路径（健康检查等）返回 False，不报错
- 多段 api/v1/ 路径（代理重写）锚定起点，不取末段（核心修复验证）
- 前缀带 /proxy/ 等非标路径不误识别为 api 应用
- resolver_match.route 优先于 request.path（主路径验证）
- 应用名映射正确（system_mgmt→system-manager 等）
- revert 验证：把旧 split 逻辑还原后，多段 api/v1/ 测试必须失败
"""

import re
import sys
import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Django-free 独立加载 harness
# 无需 Django settings；直接按路径加载 backends.py 被测模块，
# 仅注入必要的伪依赖（django.db.models.F 等不需要 settings 也能 import）。
# ---------------------------------------------------------------------------

def _install(name: str, **attrs) -> ModuleType:
    """往 sys.modules 注入一个最小伪模块（递归注册所有前缀）。"""
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        key = ".".join(parts[:i])
        if key not in sys.modules:
            mod = ModuleType(key)
            sys.modules[key] = mod
    mod = sys.modules[name]
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def _load_backends():
    """加载 backends.py 并注入所有依赖伪模块。返回 AuthBackend 类。"""

    # --- 基础伪依赖 ---
    # pytz
    pytz_mod = _install("pytz")
    setattr(pytz_mod, "timezone", lambda tz: tz)

    # django.contrib.auth.backends
    class _ModelBackend:
        pass

    _install("django")
    _install("django.contrib")
    _install("django.contrib.auth")
    _install("django.contrib.auth.backends", ModelBackend=_ModelBackend)
    _install("django.core")
    _install("django.core.cache", cache=MagicMock())
    _install("django.core.exceptions", MultipleObjectsReturned=Exception, ObjectDoesNotExist=Exception)
    _install("django.db", IntegrityError=Exception)
    _install("django.utils")
    _install("django.utils.timezone")
    _install("django.utils.translation")

    # app-level stubs
    _install("apps")
    _install("apps.base")
    _install("apps.base.models", User=MagicMock(), UserAPISecret=MagicMock())
    _install("apps.core")
    _install("apps.core.constants",
             VERIFY_TOKEN_USER_NOT_FOUND_CODE="",
             VERIFY_TOKEN_USER_NOT_FOUND_MESSAGE="")
    _install("apps.core.logger", logger=MagicMock())
    _install("apps.core.utils")
    _install("apps.core.utils.custom_error", DoesNotExist=Exception)
    _install("apps.rpc")
    _install("apps.rpc.system_mgmt", SystemMgmt=MagicMock())
    _install("apps.system_mgmt")
    _install("apps.system_mgmt.models", Group=MagicMock(), Menu=MagicMock(),
             Role=MagicMock(), User=MagicMock())

    backends_path = (
        Path(__file__).parent.parent  # server/apps/core/
        / "backends.py"
    )
    spec = importlib.util.spec_from_file_location("apps.core.backends", backends_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["apps.core.backends"] = mod
    spec.loader.exec_module(mod)
    return mod.AuthBackend


AuthBackend = _load_backends()


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------

def _make_request(path: str, route: str = None) -> MagicMock:
    """构造最小 request mock，可选地携带 resolver_match。"""
    req = MagicMock()
    req.path = path
    if route is not None:
        rm = MagicMock()
        rm.route = route
        req.resolver_match = rm
    else:
        req.resolver_match = None
    return req


def _user_info(roles=None, is_superuser=False):
    return {
        "is_superuser": is_superuser,
        "roles": roles or [],
    }


# ---------------------------------------------------------------------------
# 核心测试：_extract_app_name_from_request
# ---------------------------------------------------------------------------

class TestExtractAppName:
    """验证应用名提取逻辑正确性。"""

    def test_normal_api_path_extracts_app_name(self):
        """正常 /api/v1/<app>/ 路径正确提取。"""
        req = _make_request("/api/v1/system_mgmt/users/")
        assert AuthBackend._extract_app_name_from_request(req) == "system_mgmt"

    def test_node_mgmt_path(self):
        req = _make_request("/api/v1/node_mgmt/nodes/")
        assert AuthBackend._extract_app_name_from_request(req) == "node_mgmt"

    def test_health_check_path_returns_empty(self):
        """不含 /api/v1/ 的健康检查路径返回空串。"""
        req = _make_request("/health/")
        assert AuthBackend._extract_app_name_from_request(req) == ""

    def test_multi_segment_api_v1_anchors_at_start(self):
        """代理重写产生多段 api/v1/ 时，锚定起始段，不取末段。
        这是 Issue #3492 的核心修复点：旧 split("api/v1/")[-1] 会取到错误末段。
        """
        # /api/v1/system_mgmt/api/v1/custom_app/endpoint
        # 旧逻辑：split("api/v1/") = ['/', 'system_mgmt/', 'custom_app/endpoint']
        #         [-1] = 'custom_app/endpoint' → split("/",1)[0] = 'custom_app'（错误）
        # 新逻辑：锚定 ^/api/v1/ → 取第一段 'system_mgmt'（正确）
        req = _make_request("/api/v1/system_mgmt/api/v1/custom_app/endpoint")
        assert AuthBackend._extract_app_name_from_request(req) == "system_mgmt"

    def test_proxy_prefix_path_returns_empty(self):
        """/proxy/... 路径不以 /api/v1/ 开头，应返回空串（不误识别）。"""
        req = _make_request("/proxy/api/v1/system_mgmt/api/v1/custom_app/endpoint")
        assert AuthBackend._extract_app_name_from_request(req) == ""

    def test_resolver_match_route_takes_priority(self):
        """当 resolver_match.route 可用时，优先使用路由信息，忽略 request.path。"""
        # path 是混淆路径，route 是 Django 已解析的正确路由
        req = _make_request(
            path="/proxy/api/v1/system_mgmt/api/v1/custom_app/endpoint",
            route="api/v1/system_mgmt/",
        )
        assert AuthBackend._extract_app_name_from_request(req) == "system_mgmt"

    def test_resolver_match_route_empty_falls_back_to_path(self):
        """resolver_match.route 为空串时，降级到 request.path 匹配。"""
        req = _make_request(
            path="/api/v1/node_mgmt/nodes/",
            route="",
        )
        assert AuthBackend._extract_app_name_from_request(req) == "node_mgmt"


# ---------------------------------------------------------------------------
# 核心测试：get_is_superuser
# ---------------------------------------------------------------------------

class TestGetIsSuperuser:
    """验证超级用户判断结果的正确性。"""

    def test_is_superuser_flag_takes_precedence(self):
        """user_info.is_superuser=True 时直接返回 True，跳过路径解析。"""
        req = _make_request("/health/")
        result = AuthBackend.get_is_superuser(req, _user_info(is_superuser=True))
        assert result is True

    def test_system_mgmt_admin_role_grants_superuser(self):
        """system_mgmt 管理员角色正确映射为 system-manager--admin。"""
        req = _make_request("/api/v1/system_mgmt/users/")
        result = AuthBackend.get_is_superuser(
            req, _user_info(roles=["system-manager--admin"])
        )
        assert result is True

    def test_wrong_app_role_does_not_grant_superuser(self):
        """其他应用的管理员角色不授予当前应用的超级用户权限。"""
        req = _make_request("/api/v1/system_mgmt/users/")
        result = AuthBackend.get_is_superuser(
            req, _user_info(roles=["node--admin"])
        )
        assert result is False

    def test_health_check_path_does_not_grant_superuser(self):
        """健康检查路径无法提取应用名，不会授予超级用户权限（--admin 不在 roles）。"""
        req = _make_request("/health/")
        # '--admin' 不在 roles，且空 app_name 时直接 False
        result = AuthBackend.get_is_superuser(req, _user_info(roles=["--admin"]))
        assert result is False

    def test_multi_segment_api_v1_no_privilege_escalation(self):
        """多段 api/v1/ 的混淆路径不产生权限错位（核心修复：不把 custom_app 当作应用名）。"""
        # 如果旧逻辑：custom_app → 'custom_app--admin' in roles → 可能误判
        req = _make_request("/api/v1/system_mgmt/api/v1/custom_app/endpoint")
        # 应只检查 system_mgmt 对应的 system-manager--admin，不检查 custom_app--admin
        result = AuthBackend.get_is_superuser(
            req, _user_info(roles=["custom_app--admin"])
        )
        assert result is False  # 旧逻辑下这里会误判为 True

    def test_node_mgmt_mapping(self):
        """node_mgmt 正确映射为 node--admin。"""
        req = _make_request("/api/v1/node_mgmt/nodes/")
        result = AuthBackend.get_is_superuser(req, _user_info(roles=["node--admin"]))
        assert result is True

    def test_unmapped_app_uses_raw_name(self):
        """未在映射表中的应用名原样使用（如 mlops → mlops--admin）。"""
        req = _make_request("/api/v1/mlops/models/")
        result = AuthBackend.get_is_superuser(req, _user_info(roles=["mlops--admin"]))
        assert result is True


# ---------------------------------------------------------------------------
# Revert 哨兵：验证测试本身的有效性
# ---------------------------------------------------------------------------

class TestRevertSentinel:
    """如果把修复 revert 回旧的 split 逻辑，关键测试必须失败。
    此 class 通过直接模拟旧逻辑来验证哨兵测试的有效性。"""

    def _old_extract(self, path: str) -> str:
        """旧逻辑（被修复前）。"""
        return path.split("api/v1/")[-1].split("/", 1)[0]

    def test_old_logic_fails_on_multi_segment(self):
        """旧逻辑在多段 api/v1/ 路径下会取错误末段（反向证明修复必要性）。"""
        path = "/api/v1/system_mgmt/api/v1/custom_app/endpoint"
        old_result = self._old_extract(path)
        # 旧逻辑取最后一段 'custom_app'，而非正确的 'system_mgmt'
        assert old_result == "custom_app", f"旧逻辑应取末段 'custom_app'，实际: {old_result!r}"

    def test_new_logic_fixes_multi_segment(self):
        """新逻辑锚定起点，正确取 'system_mgmt'。"""
        req = _make_request("/api/v1/system_mgmt/api/v1/custom_app/endpoint")
        result = AuthBackend._extract_app_name_from_request(req)
        assert result == "system_mgmt", f"新逻辑应取 'system_mgmt'，实际: {result!r}"


# ---------------------------------------------------------------------------
# 直接运行入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    test_classes = [
        TestExtractAppName,
        TestGetIsSuperuser,
        TestRevertSentinel,
    ]

    passed = 0
    failed = 0
    for cls in test_classes:
        instance = cls()
        for name in [m for m in dir(cls) if m.startswith("test_")]:
            method = getattr(instance, name)
            try:
                method()
                print(f"  PASS  {cls.__name__}.{name}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {cls.__name__}.{name}")
                traceback.print_exc()
                failed += 1

    print(f"\n{'='*60}")
    print(f"结果: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
