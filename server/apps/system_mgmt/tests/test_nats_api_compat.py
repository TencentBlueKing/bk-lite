"""旧 apps.system_mgmt.nats_api 路径兼容层回归测试。"""
import ast
from pathlib import Path
import types

from apps.system_mgmt import nats_api


def test_nats_api_compat_syncs_sensitive_monkeypatch_helpers(monkeypatch):
    def fake_verify_token(token):
        return types.SimpleNamespace(username="alice", domain="domain.com")

    def fake_build_jwt_payload(user_id):
        return {"patched_user_id": user_id}

    def fake_collect_ancestor_group_ids(seed_ids):
        return set(seed_ids)

    monkeypatch.setattr(nats_api, "_verify_token", fake_verify_token)
    monkeypatch.setattr(nats_api, "_build_jwt_payload", fake_build_jwt_payload)
    monkeypatch.setattr(nats_api, "_collect_ancestor_group_ids", fake_collect_ancestor_group_ids)

    nats_api._sync_compat_globals()

    assert nats_api._auth._verify_token is fake_verify_token
    assert nats_api._auth._collect_ancestor_group_ids is fake_collect_ancestor_group_ids
    assert nats_api._login._verify_token is fake_verify_token
    assert nats_api._login._build_jwt_payload is fake_build_jwt_payload
    assert nats_api._otp._build_jwt_payload is fake_build_jwt_payload
    assert nats_api._settings._build_jwt_payload is fake_build_jwt_payload
    assert nats_api._wechat._build_jwt_payload is fake_build_jwt_payload


def test_reset_pwd_uses_legacy_nats_api_verify_token_patch(monkeypatch):
    monkeypatch.setattr(
        nats_api,
        "_verify_token",
        lambda token: types.SimpleNamespace(username="bob", domain="domain.com"),
    )

    result = nats_api.reset_pwd("alice", "domain.com", "ValidPass1!", caller_token="bob-token")

    assert result == {"result": False, "message": "Unauthorized: caller does not match target user"}


def test_get_user_login_token_uses_legacy_nats_api_jwt_payload_patch(monkeypatch):
    captured = {}

    def fake_build_jwt_payload(user_id):
        return {"patched_user_id": user_id}

    def fake_jwt_encode(**kwargs):
        captured.update(kwargs)
        return "patched-token"

    class EmptySystemSettings:
        class objects:
            @staticmethod
            def filter(key):
                return types.SimpleNamespace(first=lambda: None)

    user = types.SimpleNamespace(
        id=42,
        username="alice",
        display_name="Alice",
        domain="domain.com",
        locale="zh-Hans",
        timezone="Asia/Shanghai",
        temporary_pwd=False,
        disabled=False,
        otp_secret="",
        last_login=None,
        save=lambda: None,
    )
    monkeypatch.setattr(nats_api, "_build_jwt_payload", fake_build_jwt_payload)
    monkeypatch.setattr(nats_api._login, "SystemSettings", EmptySystemSettings)
    monkeypatch.setattr(nats_api.jwt, "encode", fake_jwt_encode)

    result = nats_api.get_user_login_token(user, "alice")

    assert result["result"] is True
    assert result["data"]["token"] == "patched-token"
    assert captured["payload"] == {"patched_user_id": 42}


def test_verify_token_uses_legacy_nats_api_collect_ancestor_patch(monkeypatch):
    captured = {}

    def fake_collect_ancestor_group_ids(seed_ids):
        captured["seed_ids"] = seed_ids
        return {1, 2}

    class FakeRoleList:
        def __iter__(self):
            return iter([types.SimpleNamespace(app="cmdb", name="viewer")])

        def values_list(self, *args, **kwargs):
            return [[10]]

    class FakeRoleObjects:
        @staticmethod
        def filter(**kwargs):
            return FakeRoleList()

    class FakeGroupQuerySet:
        def filter(self, **kwargs):
            captured["group_filter"] = kwargs
            return self

        def order_by(self, *args):
            return [types.SimpleNamespace(id=1, name="team-a", parent_id=None)]

    class FakeGroupObjects:
        @staticmethod
        def prefetch_related(*args):
            return FakeGroupQuerySet()

    class FakeMenuQuerySet:
        @staticmethod
        def values_list(*args):
            return [("cmdb", "host-view")]

    class FakeMenuObjects:
        @staticmethod
        def filter(**kwargs):
            return FakeMenuQuerySet()

    monkeypatch.setattr(
        nats_api,
        "_verify_token",
        lambda token: types.SimpleNamespace(
            id=7,
            username="alice",
            display_name="Alice",
            domain="domain.com",
            email="alice@example.com",
            group_list=[1],
            locale="zh-Hans",
            timezone="Asia/Shanghai",
        ),
    )
    monkeypatch.setattr(nats_api, "_collect_ancestor_group_ids", fake_collect_ancestor_group_ids)
    monkeypatch.setattr(nats_api, "get_user_all_roles", lambda user: [100])
    monkeypatch.setattr(nats_api._auth, "get_cached_token_info", lambda username, domain: None)
    monkeypatch.setattr(nats_api._auth, "set_cached_token_info", lambda username, domain, result: None)
    monkeypatch.setattr(nats_api._auth, "Role", types.SimpleNamespace(objects=FakeRoleObjects()))
    monkeypatch.setattr(nats_api._auth, "Group", types.SimpleNamespace(objects=FakeGroupObjects()))
    monkeypatch.setattr(nats_api._auth, "Menu", types.SimpleNamespace(objects=FakeMenuObjects()))
    monkeypatch.setattr(nats_api._auth.GroupUtils, "build_group_tree", lambda queryset, is_superuser, group_ids: [])
    monkeypatch.setattr(nats_api._auth.cache, "get", lambda key: None)
    monkeypatch.setattr(nats_api._auth.cache, "set", lambda key, value, timeout: None)

    result = nats_api.verify_token("token")

    assert result["result"] is True
    assert captured["seed_ids"] == [1]
    assert captured["group_filter"] == {"id__in": {1, 2}}


def test_nats_modules_explicitly_import_private_common_helpers():
    nats_dir = Path(nats_api.__file__).parent / "nats"
    common_tree = ast.parse((nats_dir / "common.py").read_text())
    common_private_names = {
        node.name
        for node in common_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name.startswith("_")
    }
    for node in common_tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_name = alias.asname or alias.name
                if imported_name.startswith("_"):
                    common_private_names.add(imported_name)

    for module_path in sorted(nats_dir.glob("*.py")):
        if module_path.name in {"__init__.py", "common.py"}:
            continue

        module_tree = ast.parse(module_path.read_text())
        defined_names = {
            node.name
            for node in ast.walk(module_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        explicit_private_imports = set()
        used_private_names = set()

        for node in ast.walk(module_tree):
            if isinstance(node, ast.ImportFrom) and node.module == "common":
                explicit_private_imports.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name != "*" and (alias.asname or alias.name).startswith("_")
                )
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id.startswith("_") and not node.id.startswith("__"):
                    used_private_names.add(node.id)

        missing = sorted((used_private_names & common_private_names) - defined_names - explicit_private_imports)
        assert missing == [], f"{module_path.name} must explicitly import private common helpers: {missing}"
