import asyncio
import json
from copy import deepcopy
from unittest.mock import Mock

from django.conf import settings

from apps.cmdb.nats import nats as cmdb_nats
from apps.cmdb.nats.list_instances_auth import authorize_list_instances_params
from apps.rpc.cmdb import CMDB
from nats_client.handlers import nats_handler
from nats_client.utils import parse_arguments


def test_list_instances_rpc_upgrades_v2_to_signed_v3_without_mutating_input():
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

    result = CMDB().list_instances(
        protocol_version="2",
        model_id="host",
        organization_ids=[1],
        format=False,
    )

    assert result == {"count": 1, "items": [{"inst_uuid": "u1"}]}
    assert captured["params"] == [{"field": "organization", "type": "list[]", "value": [1]}]
