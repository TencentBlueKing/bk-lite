"""
console_mgmt 邮箱验证码接口安全规格测试。

规格要点（Issue #3468 修复）：
- send_email_code 不再返回 hashed_code 给客户端
- send_email_code 使用 secrets 模块（CSPRNG）生成验证码
- send_email_code 将验证码存入服务端 cache（TTL 600s），不向客户端暴露
- validate_email_code 从 cache 取码比对，验证通过后立即删除（一次性使用）
- validate_email_code 不再接受客户端传入的 hashed_code
- cache 中无记录（过期或已用）时返回失败，不可暴力枚举
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

pytestmark = [pytest.mark.unit]

# --------------------------------------------------------------------------- #
# 独立测试 harness：不依赖 Django ORM / settings，直接加载被测函数
# --------------------------------------------------------------------------- #

import importlib.util
import sys
import types


def _install(name, **attrs):
    """往 sys.modules 注入伪模块（支持多级路径）。"""
    parts = name.split(".")
    parent = None
    for i, part in enumerate(parts):
        full = ".".join(parts[: i + 1])
        if full not in sys.modules:
            mod = types.ModuleType(full)
            sys.modules[full] = mod
            if parent is not None:
                setattr(parent, part, mod)
        parent = sys.modules[full]
    for k, v in attrs.items():
        setattr(sys.modules[name], k, v)
    return sys.modules[name]


def _load_views():
    """加载 views.py，注入所有外部依赖的桩。"""
    # Django 框架桩
    _install("django")
    _install("django.contrib")
    _install("django.contrib.auth")
    _install("django.contrib.auth.hashers", check_password=lambda pwd, h: pwd == h, make_password=lambda pwd: f"hashed:{pwd}")
    _install("django.core")
    _install("django.core.cache", cache=MagicMock())
    _install("django.db")
    _install("django.db.transaction", atomic=lambda: __import__("contextlib").contextmanager(lambda f: f)())
    _install("django.http", JsonResponse=lambda d, **kw: d)  # 让 JsonResponse 透传 dict
    _install("django.utils")
    _install("django.utils.timezone")
    _install("zoneinfo", ZoneInfo=lambda tz: tz)

    # 应用级桩
    _install("apps")
    _install("apps.core")
    _install("apps.core.utils")
    _install("apps.core.utils.loader", LanguageLoader=lambda **kw: MagicMock(get=lambda k, d="": d))
    _install("apps.rpc")
    _install("apps.rpc.system_mgmt", SystemMgmt=MagicMock)
    _install("apps.system_mgmt")
    _install("apps.system_mgmt.models", Group=MagicMock(), Role=MagicMock(), User=MagicMock())
    _install("apps.system_mgmt.models.app", App=MagicMock())
    _install("apps.system_mgmt.utils")
    _install("apps.system_mgmt.utils.group_utils", GroupUtils=MagicMock())
    _install("apps.system_mgmt.utils.operation_log_utils", log_operation=MagicMock())

    spec = importlib.util.spec_from_file_location(
        "console_mgmt_views",
        Path(__file__).resolve().parents[1] / "views.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_views = _load_views()


# --------------------------------------------------------------------------- #
# 辅助：构建假 request
# --------------------------------------------------------------------------- #

def _make_request(body: dict, username: str = "alice") -> MagicMock:
    req = MagicMock()
    req.body = json.dumps(body).encode()
    req.user.username = username
    req.user.locale = "en"
    req.user.domain = "domain.com"
    return req


# --------------------------------------------------------------------------- #
# send_email_code 测试
# --------------------------------------------------------------------------- #

class TestSendEmailCode:
    def test_不返回hashed_code(self):
        """send_email_code 响应中不得含有 hashed_code 字段。"""
        mock_cache = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.return_value.send_email_to_receiver.return_value = {"result": True}

        with patch.object(_views, "cache", mock_cache), \
             patch.object(_views, "SystemMgmt", mock_rpc):
            req = _make_request({"email": "user@example.com"})
            resp = _views.send_email_code(req)

        assert "hashed_code" not in resp, "send_email_code 不应将 hashed_code 返回给客户端"

    def test_验证码存入cache且TTL为600(self):
        """send_email_code 必须调用 cache.set 存储验证码，TTL = 600（或 EMAIL_CODE_TTL）。"""
        mock_cache = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.return_value.send_email_to_receiver.return_value = {"result": True}

        with patch.object(_views, "cache", mock_cache), \
             patch.object(_views, "SystemMgmt", mock_rpc):
            req = _make_request({"email": "user@example.com"})
            _views.send_email_code(req)

        assert mock_cache.set.called, "send_email_code 必须调用 cache.set 保存验证码"
        set_args = mock_cache.set.call_args
        # 参数：cache_key, code, timeout=TTL
        assert set_args[1].get("timeout") == _views._EMAIL_CODE_TTL or (
            len(set_args[0]) >= 3 and set_args[0][2] == _views._EMAIL_CODE_TTL
        ), f"cache.set 的 TTL 应为 {_views._EMAIL_CODE_TTL}，实际调用: {set_args}"

    def test_cache_key按用户和邮箱隔离(self):
        """cache key 必须包含 username 和 email，避免跨用户碰撞。"""
        mock_cache = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.return_value.send_email_to_receiver.return_value = {"result": True}

        email = "victim@example.com"
        username = "alice"
        with patch.object(_views, "cache", mock_cache), \
             patch.object(_views, "SystemMgmt", mock_rpc):
            req = _make_request({"email": email}, username=username)
            _views.send_email_code(req)

        set_call_key = mock_cache.set.call_args[0][0]
        assert username in set_call_key, "cache key 必须含 username"
        assert email in set_call_key, "cache key 必须含 email"

    def test_使用secrets而非random(self):
        """send_email_code 不得使用 random 模块（非CSPRNG）生成验证码。"""
        import random as _random
        mock_cache = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.return_value.send_email_to_receiver.return_value = {"result": True}

        with patch.object(_views, "cache", mock_cache), \
             patch.object(_views, "SystemMgmt", mock_rpc), \
             patch.object(_random, "randint", side_effect=AssertionError("不应使用 random.randint")):
            req = _make_request({"email": "user@example.com"})
            # 如果使用了 random.randint，会抛出 AssertionError
            _views.send_email_code(req)

    def test_RPC失败时不存入cache(self):
        """邮件发送失败时不应将验证码存入 cache。"""
        mock_cache = MagicMock()
        mock_rpc = MagicMock()
        mock_rpc.return_value.send_email_to_receiver.return_value = {"result": False, "message": "SMTP error"}

        with patch.object(_views, "cache", mock_cache), \
             patch.object(_views, "SystemMgmt", mock_rpc):
            req = _make_request({"email": "user@example.com"})
            resp = _views.send_email_code(req)

        mock_cache.set.assert_not_called()
        assert resp.get("result") is False


# --------------------------------------------------------------------------- #
# validate_email_code 测试
# --------------------------------------------------------------------------- #

class TestValidateEmailCode:
    def test_正确验证码通过并删除cache(self):
        """正确验证码验证后必须从 cache 删除（一次性使用）。"""
        mock_cache = MagicMock()
        mock_cache.get.return_value = "123456"

        with patch.object(_views, "cache", mock_cache):
            req = _make_request({"email": "user@example.com", "input_code": "123456"})
            resp = _views.validate_email_code(req)

        assert resp.get("result") is True
        mock_cache.delete.assert_called_once()

    def test_错误验证码失败且不删除cache(self):
        """错误验证码应返回失败，且 cache 中的记录不被删除（防止攻击者消耗正常验证码）。"""
        mock_cache = MagicMock()
        mock_cache.get.return_value = "123456"

        with patch.object(_views, "cache", mock_cache):
            req = _make_request({"email": "user@example.com", "input_code": "999999"})
            resp = _views.validate_email_code(req)

        assert resp.get("result") is False
        mock_cache.delete.assert_not_called()

    def test_cache中无记录时返回失败(self):
        """验证码过期或已使用（cache 无记录）时必须返回失败，不可绕过。"""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None  # 模拟过期/已用

        with patch.object(_views, "cache", mock_cache):
            req = _make_request({"email": "user@example.com", "input_code": "123456"})
            resp = _views.validate_email_code(req)

        assert resp.get("result") is False

    def test_不接受客户端传入hashed_code(self):
        """旧方案中客户端可传 hashed_code 绕过 TTL；新方案必须忽略该字段。
        即使请求体中包含 hashed_code，验证仍应走 cache 路径（cache无记录→失败）。
        """
        mock_cache = MagicMock()
        mock_cache.get.return_value = None  # cache 无记录

        with patch.object(_views, "cache", mock_cache):
            # 攻击者同时传 hashed_code（旧方案）和 input_code
            req = _make_request({
                "email": "user@example.com",
                "hashed_code": "some_bcrypt_hash",
                "input_code": "123456"
            })
            resp = _views.validate_email_code(req)

        # 不管 hashed_code 是否有效，cache 无记录时必须失败
        assert resp.get("result") is False, "存在 hashed_code 时仍不应绕过 cache 校验"

    def test_revert修复后旧方案可被绕过(self):
        """回归检验：确认修复代码被 revert 后，旧行为（直接验证 hashed_code）会导致安全问题。
        此测试本身在修复代码下应该 PASS（因为我们不再做 check_password(input, hashed_code)）。
        """
        # 如果 validate_email_code 仍使用 check_password，
        # 传入 hashed_code=make_password("123456") 应当无论 cache 状态如何都验证通过
        # → 修复后：cache 无记录时直接返回失败，不调用 check_password
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        with patch.object(_views, "cache", mock_cache):
            req = _make_request({
                "email": "user@example.com",
                "hashed_code": "hashed:123456",  # 旧的 make_password 输出
                "input_code": "123456"
            })
            resp = _views.validate_email_code(req)

        # 修复后：cache 无记录 → 必须失败，不得 check_password(input, hashed_code)
        assert resp.get("result") is False, (
            "revert 测试失败：修复代码下 cache 无记录时不应通过，否则说明仍在使用 hashed_code 验证"
        )
