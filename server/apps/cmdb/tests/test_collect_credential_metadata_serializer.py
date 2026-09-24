"""按采集目录覆盖凭据池规范化之后的新建、编辑校验。"""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_object_tree import get_collect_object_meta

ENTRIES = json.loads((Path(__file__).parent / "fixtures/collection_original_forms.json").read_text())
AUTH_ENTRIES = [entry for entry in ENTRIES if entry["binding"]]
TARGET_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


def _credential(entry, source):
    form = entry.get("effective_form", entry["original_form"])
    credential = {
        "ssh": {"username": "reader", "password": "test-secret", "port": 22},
        "sql": {"user": "reader", "password": "test-secret", "port": 3306},
        "platform_api": {"username": "reader", "password": "test-secret", "port": 443, "verify_tls": True},
        "cloud": {"accessKey": "test-key", "accessSecret": "test-secret"},
        "snmp": {"version": "v2c", "community": "test-community", "snmp_port": 161},
        "influxdb": {"token": "test-token", "scheme": "https", "port": 8086, "verify_tls": True},
        "winsphere": {"user": "reader", "password": "test-secret", "https_port": 443, "verify_tls": True},
        "vmware": {"username": "reader", "password": "test-secret", "port": 443, "ssl": True},
        "ipmi": {"username": "reader", "password": "test-secret", "port": 623, "privilege": "administrator"},
        "redfish": {"username": "reader", "password": "test-secret", "port": 443, "verify_tls": True},
        "winrm": {"username": "reader", "password": "test-secret", "port": 5986},
        "config_file": {"username": "reader", "password": "test-secret", "port": 22},
        "network_config_file": {"username": "reader", "password": "test-secret", "port": 22, "transport_protocol": "ssh"},
    }[form]
    if entry["model_id"] == "hwcloud":
        credential["project_id"] = "test-project"
    if entry["model_id"] == "azure":
        credential.update(tenant_id="test-tenant", subscription_id="test-subscription")
    credential["credential_source"] = source
    if source == "vault":
        credential.update(
            vault_credential_id="test-vault-id",
            vault_type_key=entry["binding"].split("/")[1],
            vault_actor_context={"username": "operator", "domain": "test", "current_team": 1},
        )
    return credential


@pytest.mark.parametrize("entry", AUTH_ENTRIES, ids=lambda entry: entry["id"])
@pytest.mark.parametrize("source", ["inline", "vault"])
def test_all_authenticated_entries_accept_pool_metadata_on_create_and_update(monkeypatch, entry, source):
    model_id = entry["model_id"]
    target_model = get_collect_object_meta(model_id).get("target_model_id") or model_id
    target = {
        "inst_uuid": TARGET_UUID,
        "model_id": "switch" if model_id in {"network", "network_config_file"} else target_model,
        "inst_name": "test-target",
        "ip_addr": "192.0.2.10",
        "management_address": "platform.example.com",
        "brand": "Cisco",
    }
    # 只隔离用户、目录和资产查询，保留真实凭据、目标与插件校验。
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *args, **kwargs: {})
    monkeypatch.setattr(CollectModelSerializer.Meta, "validators", [], raising=False)
    monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.InstanceManage.query_entity_by_uuids", lambda uuids: [target])
    monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.CmdbRulesFormatUtil.format_user_groups_permissions", lambda *a, **kw: {})
    monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.InstanceManage._has_topology_view_permission", lambda *a, **kw: True)
    monkeypatch.setattr("apps.cmdb.services.vmware_collection_scope.VmwareCollectionScope.peers", lambda task: [])
    if model_id == "winsphere":
        monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.get_collect_object_meta", lambda *a, **kw: entry)

    pool = CollectCredentialPoolService.normalize_pool(_credential(entry, source))
    pool = CollectCredentialPoolService.assign_versions([], pool)
    CollectCredentialPoolService.validate_pool_shape(pool)
    params = {}
    if model_id == "physcial_server" and entry["type"] == "protocol":
        params["collection_protocol"] = entry["credential_protocol"]
    if model_id == "pc":
        params["os_type"] = "windows"
    if model_id == "config_file":
        params["config_file_path"] = "/etc/hosts"
    if model_id == "network_config_file":
        params.update(config_name="running-config", commands="show version")
    payload = {
        "name": f"test-{entry['id']}",
        "model_id": model_id,
        "task_type": entry["task_type"],
        "driver_type": entry["type"],
        "credential": pool,
        "instances": [target],
        "access_point": [{"id": "test-node"}],
        "is_interval": True,
        "cycle_value_type": "cycle",
        "cycle_value": "30",
        "scan_cycle": "30",
        "timeout": 120,
        "team": [1],
        "params": params,
    }
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    serializer = CollectModelSerializer(data=payload, context={"request": request})
    assert serializer.is_valid(), serializer.errors
    saved = serializer.validated_data["credential"][0]
    assert saved["credential_id"] == pool[0]["credential_id"]
    assert saved["credential_version"] == 1
    assert saved["credential_source"] == source
    if source == "vault":
        assert saved["vault_credential_id"] == "test-vault-id"
        assert not (set(saved) & CollectCredentialPoolService.VAULT_CORE_FIELDS)

    instance = CollectModels(**serializer.validated_data)
    old_pool = copy.deepcopy(instance.credential)
    old_pool[0]["credential_version"] = 4
    instance.credential = old_pool
    update_pool = CollectCredentialPoolService.assign_versions(old_pool, old_pool)
    serializer = CollectModelSerializer(instance, data={"credential": update_pool}, partial=True, context={"request": request})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["credential"][0]["credential_version"] == 4
    assert serializer.validated_data["credential"][0]["credential_id"] == saved["credential_id"]
