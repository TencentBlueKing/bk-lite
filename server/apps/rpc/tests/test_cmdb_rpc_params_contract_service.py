"""CMDB RPC 参数 envelope 的端到端兼容契约服务测试。"""

import asyncio
import json

import pydantic.root_model  # noqa
import pytest
from django.conf import settings

from apps.cmdb.nats import nats as cmdb_nats
from apps.rpc.cmdb import CMDB
from nats_client.handlers import nats_handler
from nats_client.registry import default_registry
from nats_client.utils import parse_arguments

pytestmark = pytest.mark.unit


def _dispatch(method_name, **kwargs):
    key = f"{settings.NATS_NAMESPACE}.{method_name}"
    return asyncio.run(nats_handler(key, json.loads(parse_arguments((), kwargs))))


def test_prebuilt_envelope_merges_non_conflicting_flat_fields():
    client = CMDB()
    calls = []
    client.client.run = lambda method, **kwargs: calls.append((method, kwargs)) or {"result": True}

    client.search_models(params={"classification_id": "host_mgmt"}, include_hidden=False)

    assert calls == [("search_models", {"params": {"classification_id": "host_mgmt", "include_hidden": False}})]


def test_prebuilt_envelope_rejects_conflicting_flat_fields():
    with pytest.raises(ValueError, match="params conflict.*model_id"):
        CMDB().search_instances_batch(params={"model_id": "host"}, model_id="service")


def test_remote_facade_serializes_and_dispatches_to_real_handler(monkeypatch):
    monkeypatch.setattr(cmdb_nats.ModelManage, "search_model", lambda **kwargs: kwargs)

    async def request(namespace, method_name, *args, _timeout=None, _raw=False, **kwargs):
        assert namespace == settings.NATS_NAMESPACE
        assert _timeout == 5
        assert _raw is True
        return await nats_handler(f"{namespace}.{method_name}", json.loads(parse_arguments(args, kwargs)))

    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    monkeypatch.setattr("apps.rpc.base.nats_client.request", request)

    assert CMDB().search_models(classification_id="host_mgmt", _timeout=5, _raw=True) == {
        "classification_ids": ["host_mgmt"],
        "include_hidden": False,
    }


def test_facade_envelope_remains_callable_by_pre_migration_handler():
    calls = []

    def legacy_handler(params):
        calls.append(params)
        return params

    client = CMDB()
    client.client.run = lambda method, **kwargs: legacy_handler(**kwargs)

    assert client.search_models(classification_id="host_mgmt") == {"classification_id": "host_mgmt"}
    assert calls == [{"classification_id": "host_mgmt"}]


def test_local_appclient_calls_real_handler_without_transport_controls(monkeypatch):
    monkeypatch.setattr(cmdb_nats.ModelManage, "search_model", lambda **kwargs: kwargs)

    assert CMDB(is_local_client=True).search_models(classification_id="host_mgmt", _timeout=5, _raw=True) == {
        "classification_ids": ["host_mgmt"],
        "include_hidden": False,
    }


def test_dispatcher_accepts_legacy_top_level_kwargs(monkeypatch):
    monkeypatch.setattr(cmdb_nats.ModelManage, "search_model", lambda **kwargs: kwargs)

    assert _dispatch("search_models", classification_id="host_mgmt") == {
        "classification_ids": ["host_mgmt"],
        "include_hidden": False,
    }


@pytest.mark.parametrize(
    ("method_name", "legacy_kwargs"),
    [
        ("search_instances", {"protocol_version": "2", "model_id": "host", "organization_ids": [1]}),
        ("search_instances_batch", {"protocol_version": "2", "model_id": "host", "organization_ids": [1]}),
        ("list_instances", {"protocol_version": "2", "model_id": "host", "organization_ids": [1]}),
        ("search_model_attrs", {"model_id": "host"}),
        ("search_models", {}),
        ("search_classifications", {}),
        ("search_model_associations", {"model_id": "host"}),
        (
            "search_instance_associations",
            {"protocol_version": "2", "model_id": "host", "inst_uuid": "u1", "organization_ids": [1]},
        ),
        (
            "create_instance_association",
            {
                "protocol_version": "2",
                "src_inst_uuid": "u1",
                "dst_inst_uuid": "u2",
                "model_asst_id": "a1",
                "allowed_org_ids": [1],
            },
        ),
        (
            "delete_instance_association",
            {
                "protocol_version": "2",
                "src_inst_uuid": "u1",
                "dst_inst_uuid": "u2",
                "model_asst_id": "a1",
                "allowed_org_ids": [1],
            },
        ),
    ],
)
def test_all_ten_registered_handlers_bind_legacy_top_level_kwargs(method_name, legacy_kwargs):
    identity_wrapper = cmdb_nats._accept_legacy_rpc_kwargs(lambda params: params)
    registered = default_registry.registry[f"{settings.NATS_NAMESPACE}.{method_name}"]["func"]

    assert registered.__code__ == identity_wrapper.__code__
    assert identity_wrapper(**legacy_kwargs) == legacy_kwargs


def test_dispatcher_rejects_envelope_field_conflicts():
    with pytest.raises(ValueError, match="params conflict.*classification_id"):
        _dispatch("search_models", params={"classification_id": "a"}, classification_id="b")


def test_list_instances_preserves_business_params_field(monkeypatch):
    monkeypatch.setattr(cmdb_nats, "_format_asset_instances_response", lambda model_id, instances: instances)
    monkeypatch.setattr(cmdb_nats.InstanceManage, "instance_list", lambda **kwargs: ([kwargs], 1))
    query = [{"field": "ip", "type": "str=", "value": "10.0.0.1"}]

    result = CMDB(is_local_client=True).list_instances(
        protocol_version="2",
        model_id="host",
        organization_ids=[1],
        params=query,
        format=False,
    )

    assert result["items"][0]["params"] == [*query, {"field": "organization", "type": "list[]", "value": [1]}]


def test_dispatcher_accepts_legacy_list_instances_business_params(monkeypatch):
    monkeypatch.setattr(cmdb_nats.InstanceManage, "instance_list", lambda **kwargs: ([], 0))
    query = [{"field": "ip", "type": "str=", "value": "10.0.0.1"}]

    result = _dispatch(
        "list_instances",
        protocol_version="2",
        model_id="host",
        organization_ids=[1],
        params=query,
        format=False,
    )

    assert result == {"count": 0, "items": []}
