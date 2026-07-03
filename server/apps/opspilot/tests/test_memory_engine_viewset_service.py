"""MemoryEngineViewSet 三个 action 的真实行为测试。

MemoryEngineViewSet 是普通 DRF ViewSet，action 未叠加权限装饰器，
直接调用未鉴权原方法即可。只在「引擎注册表 / SDK 探测」这一真实边界处理：
- list_engines：真实注册表 + 真实 check_sdk_availability，并对 mem0/zep/custom/未知
  类型分支用 mock 返回不同 type 的引擎列表，断言 available 标记逻辑；
- get_schema：真实注册表取 local 的 schema；未知类型 -> 400；
- test_connection：local 走短路分支；未知类型 ValueError -> 400；
  注册一个临时引擎类，断言 TempEngine 构造 + test_connection 透传；
  引擎 test_connection 抛异常 -> 返回 success=False 而非 500。

断言 DRF Response 的 status_code 与 .data（未渲染即可读）。
"""
import pydantic.root_model  # noqa  预热避免 mcp 导入崩溃

from types import SimpleNamespace

import pytest

from apps.opspilot.memory.engines.base import BaseMemoryEngine
from apps.opspilot.memory.engines.registry import MemoryEngineRegistry
from apps.opspilot.viewsets.memory_engine_view import MemoryEngineViewSet

MOD = "apps.opspilot.viewsets.memory_engine_view"


def _req(data=None):
    return SimpleNamespace(data=data or {})


# ---------------------------------------------------------------------------
# list_engines
# ---------------------------------------------------------------------------
def test_list_engines_real_registry_marks_local_available():
    """真实注册表至少含 local，且 local 恒为 available=True。"""
    vs = MemoryEngineViewSet()
    resp = vs.list_engines(_req())

    assert resp.status_code == 200
    assert resp.data["result"] is True
    by_type = {e["type"]: e for e in resp.data["data"]}
    assert "local" in by_type
    assert by_type["local"]["available"] is True


def test_list_engines_availability_branches_by_sdk(mocker):
    """mem0/zep/custom/未知类型 各自按 SDK 探测结果打 available。"""
    mocker.patch(
        f"{MOD}.MemoryEngineRegistry.list_engines",
        return_value=[
            {"type": "local", "name": "L"},
            {"type": "mem0", "name": "M"},
            {"type": "zep", "name": "Z"},
            {"type": "custom", "name": "C"},
            {"type": "unknown_x", "name": "U"},
        ],
    )
    mocker.patch(
        f"{MOD}.check_sdk_availability",
        return_value={"mem0": True, "zep": False, "httpx": False},
    )

    vs = MemoryEngineViewSet()
    resp = vs.list_engines(_req())

    by_type = {e["type"]: e["available"] for e in resp.data["data"]}
    assert by_type["local"] is True  # local 分支恒 True
    assert by_type["mem0"] is True  # 跟随 sdk_availability["mem0"]
    assert by_type["zep"] is False  # 跟随 sdk_availability["zep"]
    assert by_type["custom"] is False  # 跟随 sdk_availability["httpx"]
    assert by_type["unknown_x"] is True  # else 分支默认 True


def test_list_engines_custom_defaults_httpx_true_when_absent(mocker):
    """custom 引擎在 sdk_availability 无 httpx 键时默认 True。"""
    mocker.patch(
        f"{MOD}.MemoryEngineRegistry.list_engines",
        return_value=[{"type": "custom", "name": "C"}],
    )
    mocker.patch(f"{MOD}.check_sdk_availability", return_value={})

    vs = MemoryEngineViewSet()
    resp = vs.list_engines(_req())
    assert resp.data["data"][0]["available"] is True


# ---------------------------------------------------------------------------
# get_schema
# ---------------------------------------------------------------------------
def test_get_schema_local_real_registry():
    vs = MemoryEngineViewSet()
    resp = vs.get_schema(_req(), engine_type="local")

    assert resp.status_code == 200
    assert resp.data["result"] is True
    data = resp.data["data"]
    assert data["type"] == "local"
    assert data["name"] == "本地存储"
    assert data["fields"] == []


def test_get_schema_unknown_type_returns_400():
    vs = MemoryEngineViewSet()
    resp = vs.get_schema(_req(), engine_type="nope_engine")

    assert resp.status_code == 400
    assert resp.data["result"] is False
    assert "nope_engine" in resp.data["message"]


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------
def test_test_connection_local_short_circuits():
    vs = MemoryEngineViewSet()
    resp = vs.test_connection(_req({"config": {}}), engine_type="local")

    assert resp.status_code == 200
    assert resp.data["result"] is True
    assert resp.data["data"]["success"] is True
    assert resp.data["data"]["message"] == "本地存储无需测试"


def test_test_connection_unknown_type_returns_400():
    vs = MemoryEngineViewSet()
    resp = vs.test_connection(_req({"config": {}}), engine_type="ghost_engine")

    assert resp.status_code == 400
    assert resp.data["result"] is False
    assert "ghost_engine" in resp.data["message"]


@pytest.fixture
def _temp_engine_registered():
    """注册一个临时非 local 引擎用于 test_connection 路径，结束后清理。"""
    created = {}

    class _FakeEngine(BaseMemoryEngine):
        def read(self, *a, **k):
            return None

        def write(self, *a, **k):
            return None

        def delete(self, *a, **k):
            return True

        def test_connection(self):
            # 断言 TempEngine.__init__ 真的把 config 注入了 _config
            created["config_seen"] = self._config
            created["space_id"] = self.memory_space_id
            return {"success": True, "message": "ok", "echo": self._config}

        @classmethod
        def get_engine_info(cls):
            return {"type": "fake", "name": "Fake"}

        @classmethod
        def get_config_schema(cls):
            return []

    MemoryEngineRegistry.register("fake", _FakeEngine)
    try:
        yield created
    finally:
        MemoryEngineRegistry._engines.pop("fake", None)


def test_test_connection_non_local_builds_temp_engine_and_passes_config(_temp_engine_registered):
    cfg = {"url": "http://h", "token": "t"}
    vs = MemoryEngineViewSet()
    resp = vs.test_connection(_req({"config": cfg}), engine_type="fake")

    assert resp.status_code == 200
    assert resp.data["result"] is True
    assert resp.data["data"]["success"] is True
    # 真实透传 config 到引擎实例
    assert resp.data["data"]["echo"] == cfg
    assert _temp_engine_registered["config_seen"] == cfg
    assert _temp_engine_registered["space_id"] == 0


@pytest.fixture
def _raising_engine_registered():
    class _BoomEngine(BaseMemoryEngine):
        def read(self, *a, **k):
            return None

        def write(self, *a, **k):
            return None

        def delete(self, *a, **k):
            return True

        def test_connection(self):
            raise RuntimeError("connection refused")

        @classmethod
        def get_engine_info(cls):
            return {"type": "boom", "name": "Boom"}

        @classmethod
        def get_config_schema(cls):
            return []

    MemoryEngineRegistry.register("boom", _BoomEngine)
    try:
        yield
    finally:
        MemoryEngineRegistry._engines.pop("boom", None)


def test_test_connection_engine_exception_returns_success_false_not_500(_raising_engine_registered):
    """引擎内部异常被吞为 data.success=False，HTTP 仍 200/result=True。"""
    vs = MemoryEngineViewSet()
    resp = vs.test_connection(_req({"config": {}}), engine_type="boom")

    assert resp.status_code == 200
    assert resp.data["result"] is True
    assert resp.data["data"]["success"] is False
    assert "connection refused" in resp.data["data"]["message"]
