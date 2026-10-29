"""SSL 证书采集任务更新时，空凭据必须留在参数里。

format_params 会丢掉空列表。更新函数要接住缺失的 credential：
ssl_cer 写成 []，Host 和其他 protocol 仍拒绝，IP 仍沿用旧值。
"""

import types

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.services.collect_service import CollectModelService
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit

_EMPTY_CREDENTIAL_MESSAGE = "采集凭据不能为空！"


def _instance(**overrides):
    values = {
        "is_k8s": False,
        "driver_type": CollectDriverTypes.PROTOCOL,
        "decrypt_credentials": [{"token": "old-secret"}],
    }
    values.update(overrides)
    return types.SimpleNamespace(**values)


def _update_payload(**overrides):
    payload = {
        "name": "ssl-cer-renamed",
        "task_type": CollectPluginTypes.PROTOCOL,
        "driver_type": CollectDriverTypes.PROTOCOL,
        "model_id": "ssl_cer",
        "timeout": 600,
        "input_method": 0,
        "team": [1],
        "scan_cycle": {"value_type": "cycle", "value": "5"},
        "credential": [],
    }
    payload.update(overrides)
    return payload


def test_ssl_cer_empty_credential_update_keeps_name_cycle_and_empty_list():
    instance = _instance(
        model_id="ssl_cer",
        task_type=CollectPluginTypes.PROTOCOL,
        decrypt_credentials=[{"token": "must-not-backfill"}],
    )
    payload = _update_payload(name="ssl-cer-renamed", credential=[])

    params, is_interval, scan_cycle = CollectModelService.format_params(payload)

    assert "credential" not in params
    CollectModelService.format_update_credential(instance, params)

    assert params["credential"] == []
    assert params["name"] == "ssl-cer-renamed"
    assert params["cycle_value"] == "5"
    assert params["scan_cycle"] == "*/5 * * * *"
    assert is_interval is True
    assert scan_cycle == "*/5 * * * *"
    assert params["credential"] != instance.decrypt_credentials


def test_host_empty_credential_update_still_rejected():
    instance = _instance(model_id="host", task_type=CollectPluginTypes.HOST, driver_type="snmp")
    payload = _update_payload(
        name="host-renamed",
        model_id="host",
        task_type=CollectPluginTypes.HOST,
        driver_type="snmp",
        credential=[],
    )
    params, _, _ = CollectModelService.format_params(payload)

    with pytest.raises(BaseAppException, match=_EMPTY_CREDENTIAL_MESSAGE):
        CollectModelService.format_update_credential(instance, params)


def test_other_protocol_empty_credential_update_still_rejected():
    instance = _instance(model_id="nginx", task_type=CollectPluginTypes.PROTOCOL)
    payload = _update_payload(name="nginx-renamed", model_id="nginx", credential=[])
    params, _, _ = CollectModelService.format_params(payload)

    with pytest.raises(BaseAppException, match=_EMPTY_CREDENTIAL_MESSAGE):
        CollectModelService.format_update_credential(instance, params)


def test_ip_empty_credential_update_keeps_old_value():
    old_credential = {"community": "public-kept"}
    instance = _instance(
        model_id="ip_range",
        task_type=CollectPluginTypes.IP,
        decrypt_credentials=old_credential,
    )
    payload = _update_payload(
        name="ip-renamed",
        model_id="ip_range",
        task_type=CollectPluginTypes.IP,
        credential=[],
    )
    params, _, _ = CollectModelService.format_params(payload)

    assert "credential" not in params
    CollectModelService.format_update_credential(instance, params)

    assert params["credential"] == old_credential
    assert params["name"] == "ip-renamed"
    assert params["cycle_value"] == "5"
