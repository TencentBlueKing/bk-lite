# -*- coding: utf-8 -*-
"""
Issue #3515: set_node_info 不应硬编码 skip_permission=True

验证 set_node_info() 构造 NATS 查询时：
1. 当 params 携带 organization_id 时，使用 organization_ids 限定范围，不发送 skip_permission=True
2. 当 params 不含 organization_id 时，才回退使用 skip_permission=True（向后兼容）
3. 两种情况下均传入 ip=connect_ip 缩小查询范围
4. 确保 revert 修复后测试失败（覆盖修复点）
"""

import asyncio
import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch, call

import pytest

# 允许 import stargazer 根目录模块
sys.path.insert(0, str(Path(__file__).parent.parent))


def _install_stub(name, **attrs):
    """向 sys.modules 注入伪模块，避免依赖真实环境"""
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_collection_service():
    """按路径加载 collection_service，注入最小伪依赖"""
    # 伪 logger
    logger_stub = types.SimpleNamespace(
        info=lambda *a, **kw: None,
        warning=lambda *a, **kw: None,
        error=lambda *a, **kw: None,
        debug=lambda *a, **kw: None,
    )
    sanic_log = _install_stub("sanic.log", logger=logger_stub)
    _install_stub("sanic", log=sanic_log)

    # 伪 nats_utils — nats_request 会被 patch 掉，只需占位
    _install_stub("core.nats_utils", nats_request=AsyncMock())
    _install_stub("core", nats_utils=sys.modules["core.nats_utils"])

    # 其余依赖占位
    _install_stub("core.yaml_reader", yaml_reader=object())
    _install_stub("core.plugin_executor", PluginExecutor=object)
    _install_stub("plugins.base_utils", convert_to_prometheus_format=lambda x: x)
    _install_stub("plugins", base_utils=sys.modules["plugins.base_utils"])

    path = Path(__file__).parent.parent / "service" / "collection_service.py"
    spec = importlib.util.spec_from_file_location("service.collection_service", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 加载一次，供所有测试用
_mod = _load_collection_service()
CollectionService = _mod.CollectionService


def _make_service(params: dict) -> CollectionService:
    svc = CollectionService.__new__(CollectionService)
    svc._node_info = None
    svc.namespace = "bklite"
    svc.params = params
    svc.host = params.get("host")
    svc.connect_ip = params.get("connect_ip") or svc.host
    return svc


# ── 测试 1：携带 organization_id 时不发 skip_permission ──────────────────────

@pytest.mark.asyncio
async def test_set_node_info_with_org_id_does_not_skip_permission():
    """当 params 含 organization_id 时，查询中不应出现 skip_permission=True"""
    svc = _make_service({
        "host": "10.0.0.1",
        "model_id": "host",
        "organization_id": "org-42",
    })

    captured_payloads = []

    async def fake_nats_request(subject, payload=None, timeout=10.0):
        captured_payloads.append(json.loads(payload))
        return {"success": False, "result": {"nodes": []}}

    with patch("core.nats_utils.nats_request", side_effect=fake_nats_request):
        # 重新绑定模块内的引用
        _mod.nats_request = fake_nats_request
        await svc.set_node_info()

    assert len(captured_payloads) == 1, "应调用一次 nats_request"
    query = captured_payloads[0]["args"][0]

    # 核心断言：organization_ids 存在，skip_permission 不存在
    assert "organization_ids" in query, "缺少 organization_ids"
    assert query["organization_ids"] == ["org-42"], "organization_ids 应等于 ['org-42']"
    assert "skip_permission" not in query, "携带 organization_id 时不应发送 skip_permission"
    assert query.get("ip") == "10.0.0.1", "应携带 ip 过滤参数"


# ── 测试 2：无 organization_id 时回退 skip_permission=True ───────────────────

@pytest.mark.asyncio
async def test_set_node_info_without_org_id_falls_back_to_skip_permission():
    """当 params 不含 organization_id 时，应回退到 skip_permission=True"""
    svc = _make_service({
        "host": "10.0.0.2",
        "model_id": "host",
        # 无 organization_id
    })

    captured_payloads = []

    async def fake_nats_request(subject, payload=None, timeout=10.0):
        captured_payloads.append(json.loads(payload))
        return {"success": False, "result": {"nodes": []}}

    _mod.nats_request = fake_nats_request
    await svc.set_node_info()

    assert len(captured_payloads) == 1
    query = captured_payloads[0]["args"][0]

    assert query.get("skip_permission") is True, "无组织上下文时应回退到 skip_permission=True"
    assert "organization_ids" not in query, "无 organization_id 时不应发送 organization_ids"
    assert query.get("ip") == "10.0.0.2", "应携带 ip 过滤参数"


# ── 测试 3：携带 organization_id 时找到节点并赋值 ────────────────────────────

@pytest.mark.asyncio
async def test_set_node_info_with_org_id_finds_node():
    """organization_id 模式下能正确解析 node_info"""
    svc = _make_service({
        "host": "10.0.0.3",
        "model_id": "host",
        "organization_id": "org-7",
    })

    async def fake_nats_request(subject, payload=None, timeout=10.0):
        return {
            "success": True,
            "result": {
                "nodes": [
                    {"ip": "10.0.0.3", "os": "Linux", "node_id": "n-123"},
                ]
            },
        }

    _mod.nats_request = fake_nats_request
    await svc.set_node_info()

    assert svc._node_info is not None, "应找到节点信息"
    assert svc._node_info["ip"] == "10.0.0.3"
    assert svc._node_info["node_id"] == "n-123"


# ── 测试 4：ip 过滤缩小范围，page_size=1 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_set_node_info_sends_ip_filter_and_page_size_one():
    """两种模式下都应携带 ip 和 page_size=1，避免全量拉取"""
    for org_id in ("org-1", None):
        params = {"host": "192.168.1.100", "model_id": "host"}
        if org_id:
            params["organization_id"] = org_id
        svc = _make_service(params)

        captured = []

        async def fake_nats_request(subject, payload=None, timeout=10.0):
            captured.append(json.loads(payload))
            return {"success": False, "result": {"nodes": []}}

        _mod.nats_request = fake_nats_request
        await svc.set_node_info()

        query = captured[0]["args"][0]
        assert query.get("ip") == "192.168.1.100", f"org_id={org_id}: 应携带 ip 过滤"
        assert query.get("page_size") == 1, f"org_id={org_id}: page_size 应为 1"
