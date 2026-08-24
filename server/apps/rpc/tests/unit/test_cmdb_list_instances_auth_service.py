import asyncio
import json
from copy import deepcopy
from unittest.mock import Mock

import pytest
from django.conf import settings

from apps.cmdb.nats import nats as cmdb_nats
from apps.cmdb.nats.list_instances_auth import authorize_list_instances_params
from apps.rpc.cmdb import CMDB
from nats_client.handlers import nats_handler
from nats_client.utils import parse_arguments

pytestmark = pytest.mark.unit


def test_list_instances_rpc_upgrades_v2_to_signed_v3_without_mutating_input(monkeypatch):
    monkeypatch.setenv("CMDB_NATS_LIST_INSTANCES_SIGN_V3", "true")
    rpc = CMDB(is_local_client=True)
    rpc.client = Mock()
    rpc.client.run.return_value = {"count": 0, "items": []}
    params = {
        "protocol_version": "2",
        "model_id": "host",
        "organization_ids": [1],
        "params": [{"field": "ip_addr", "type": "str=", "value": "10.0.0.1"}],
        "page": 1,
    }
    before = deepcopy(params)

    result = rpc.list_instances(params=params)

    assert result == {"count": 0, "items": []}
    assert params == before
    prepared = rpc.client.run.call_args.kwargs["params"]
    assert prepared["protocol_version"] == "3"
    authorize_list_instances_params(prepared)


def test_list_instances_rpc_preserves_v2_by_default_for_mixed_version_deploy(monkeypatch):
    monkeypatch.delenv("CMDB_NATS_LIST_INSTANCES_SIGN_V3", raising=False)
    rpc = CMDB(is_local_client=True)
    rpc.client = Mock()

    rpc.list_instances(protocol_version="2", model_id="host", organization_ids=[1])

    assert rpc.client.run.call_args.kwargs["params"]["protocol_version"] == "2"
    assert "_auth" not in rpc.client.run.call_args.kwargs["params"]


def test_new_rpc_default_remains_callable_by_pre_v3_handler(monkeypatch):
    monkeypatch.delenv("CMDB_NATS_LIST_INSTANCES_SIGN_V3", raising=False)
    rpc = CMDB(is_local_client=True)

    def pre_v3_handler(method_name, *, params):
        assert method_name == "list_instances"
        if params.get("protocol_version") != "2":
            raise ValueError("unsupported CMDB protocol version")
        return {"count": 0, "items": []}

    rpc.client = Mock()
    rpc.client.run.side_effect = pre_v3_handler

    result = rpc.list_instances(protocol_version="2", model_id="host", organization_ids=[1])

    assert result == {"count": 0, "items": []}


def test_list_instances_rpc_can_roll_back_from_v3_to_v2(monkeypatch):
    rpc = CMDB(is_local_client=True)
    rpc.client = Mock()
    kwargs = {"protocol_version": "2", "model_id": "host", "organization_ids": [1]}
    monkeypatch.setenv("CMDB_NATS_LIST_INSTANCES_SIGN_V3", "true")
    rpc.list_instances(**kwargs)
    monkeypatch.setenv("CMDB_NATS_LIST_INSTANCES_SIGN_V3", "false")
    rpc.list_instances(**kwargs)

    assert rpc.client.run.call_args_list[0].kwargs["params"]["protocol_version"] == "3"
    assert rpc.client.run.call_args_list[1].kwargs["params"] == kwargs


def test_list_instances_rpc_preserves_non_v2_failure_contract():
    rpc = CMDB(is_local_client=True)
    rpc.client = Mock()

    rpc.list_instances(model_id="host", organization_ids=[1])

    rpc.client.run.assert_called_once_with(
        "list_instances",
        params={"model_id": "host", "organization_ids": [1]},
    )


def test_remote_rpc_v2_upgrade_reaches_real_dispatcher_as_valid_v3(monkeypatch):
    captured = {}

    def instance_list(**kwargs):
        captured.update(kwargs)
        return ([{"inst_uuid": "u1"}], 1)

    async def request(namespace, method_name, *args, _timeout=None, _raw=False, **kwargs):
        assert namespace == settings.NATS_NAMESPACE
        return await nats_handler(f"{namespace}.{method_name}", json.loads(parse_arguments(args, kwargs)))

    monkeypatch.setattr(cmdb_nats.InstanceManage, "instance_list", instance_list)
    monkeypatch.setattr("apps.rpc.base.nats_client.request", request)
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    monkeypatch.setenv("CMDB_NATS_LIST_INSTANCES_SIGN_V3", "true")

    result = CMDB().list_instances(
        protocol_version="2",
        model_id="host",
        organization_ids=[1],
        format=False,
    )

    assert result == {"count": 1, "items": [{"inst_uuid": "u1"}]}
    assert captured["params"] == [{"field": "organization", "type": "list[]", "value": [1]}]
