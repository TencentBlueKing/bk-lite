"""回放 credentialPagePayloads.test.tsx 从真实页面生成的请求（全程无设备连接）。"""

import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.cmdb.extensions import registry
from apps.cmdb.node_configs import _auto_register_from_package
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_object_tree import get_collect_object_meta
from apps.cmdb.services.collect_service import CollectModelService
from apps.system_mgmt.services.credential_service import seed_builtin_types

PAYLOAD_PATH = os.environ.get("CMDB_PAGE_PAYLOADS")
if not PAYLOAD_PATH:
    pytest.skip("先运行前端页面参数契约测试，并通过 CMDB_PAGE_PAYLOADS 指定生成的请求文件", allow_module_level=True)
CASES = json.loads(Path(PAYLOAD_PATH).read_text())
DISPATCH_AUDIT = []

AUTH_FIELDS = {
    "ssh": {"username": "vault-reader", "password": "vault-secret", "auth_method": "password"},
    "sql": {"username": "vault-reader", "password": "vault-secret"},
    "platform_api": {"username": "vault-reader", "password": "vault-secret"},
    "winrm": {"username": "vault-reader", "password": "vault-secret"},
    "ipmi": {"username": "vault-reader", "password": "vault-secret"},
    "redfish": {"username": "vault-reader", "password": "vault-secret"},
    "snmp": {
        "version": "v3",
        "username": "vault-reader",
        "security_level": "authPriv",
        "auth_protocol": "SHA",
        "auth_password": "vault-auth",
        "priv_protocol": "AES",
        "priv_password": "vault-priv",
    },
    "cloud": {"access_key": "vault-key", "secret_key": "vault-secret"},
    "token": {"token": "vault-token"},
    "oauth_client": {"client_id": "vault-client", "client_secret": "vault-secret", "tenant_id": "vault-tenant"},
    "openstack": {"username": "vault-reader", "password": "vault-secret", "user_domain_name": "Internal"},
}


@pytest.fixture(scope="module", autouse=True)
def enterprise_collect():
    from apps.cmdb_enterprise.collect.provider import get_collect_enterprise_extension

    snapshot = dict(registry._registry)
    extension = get_collect_enterprise_extension()
    registry.register("collect", extension)
    for package in extension.node_param_packages:
        _auto_register_from_package(package)
    yield
    if os.environ.get("CMDB_DISPATCH_AUDIT"):
        Path(os.environ["CMDB_DISPATCH_AUDIT"]).write_text(json.dumps(DISPATCH_AUDIT, ensure_ascii=False, indent=2))
    registry._registry.clear()
    registry._registry.update(snapshot)


@pytest.mark.django_db
@pytest.mark.parametrize("case", CASES, ids=lambda case: f"{case['id']}-{case['source']}")
def test_page_create_edit_storage_and_dispatch(case, monkeypatch):
    seed_builtin_types()
    payload = copy.deepcopy(case["create"])
    model_id = payload["model_id"]
    meta = get_collect_object_meta(model_id, payload["driver_type"])
    target = {**payload["instances"][0], "model_id": meta.get("target_model_id") or model_id}
    if model_id in {"network", "network_config_file"}:
        target["model_id"] = "switch"
    request = SimpleNamespace(user=SimpleNamespace(username="operator", domain="test", group_list=[]), COOKIES={"current_team": "1"})
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *a, **kw: {})
    monkeypatch.setattr(CollectModelSerializer.Meta, "validators", [], raising=False)
    monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.InstanceManage.query_entity_by_uuids", lambda uuids: [target])
    monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.CmdbRulesFormatUtil.format_user_groups_permissions", lambda *a, **kw: {})
    monkeypatch.setattr("apps.cmdb.serializers.collect_serializer.InstanceManage._has_topology_view_permission", lambda *a, **kw: True)
    monkeypatch.setattr("apps.cmdb.services.vmware_collection_scope.VmwareCollectionScope.peers", lambda task: [])
    type_key = case["binding"].split("/")[1]
    monkeypatch.setattr(
        "apps.cmdb.services.collect_vault_resolver.SystemMgmt.resolve_credential",
        lambda self, actor, credential_id: {"result": True, "data": {"type": type_key, "fields": AUTH_FIELDS[type_key]}},
    )
    attrs, _, _ = CollectModelService.format_params(payload)
    pool = CollectCredentialPoolService.normalize_pool(attrs["credential"])
    pool[0]["credential_id"] = "test-candidate"
    CollectModelService._bind_vault_credentials(request, pool)
    attrs["credential"] = CollectCredentialPoolService.assign_versions([], pool)
    CollectCredentialPoolService.validate_pool_shape(attrs["credential"])
    serializer = CollectModelSerializer(data=attrs, context={"request": request})
    assert serializer.is_valid(), serializer.errors
    task = serializer.save()
    task.refresh_from_db()
    original = task.decrypt_credentials
    # 参数页明确填写的连接值，必须经过保存和引用解析后仍存在。
    for key in (
        "port",
        "snmp_port",
        "https_port",
        "verify_tls",
        "ssl",
        "database",
        "namespace",
        "bucket",
        "source",
        "user_type",
        "project_id",
        "subscription_id",
        "privilege",
        "transport_protocol",
    ):
        if key in case["raw"]:
            assert original[0].get(key) == case["raw"][key], (case["id"], key)
    secrets = [value for key, value in case["raw"].items() if key in {"password", "token", "authkey", "privkey", "accessSecret", "enable_password"}]
    assert all(secret not in json.dumps(task.credential) for secret in secrets)

    node = NodeParamsFactory.get_node_params(task)
    configs = node.main("push")
    assert configs
    fields = (
        "port",
        "snmp_port",
        "https_port",
        "verify_tls",
        "ssl",
        "database",
        "namespace",
        "bucket",
        "source",
        "user_type",
        "project_id",
        "subscription_id",
        "privilege",
        "transport_protocol",
        "scheme",
        "transport",
        "certValidation",
    )
    DISPATCH_AUDIT.append(
        {
            "id": case["id"],
            "source": case["source"],
            "page": {key: case["raw"][key] for key in fields if key in case["raw"]},
            "dispatch": {key: value for key, value in node.set_credential().items() if key in fields},
        }
    )
    if model_id in {"openstack", "smartx", "manageone", "fusioncompute", "nutanixhci", "inspurincloudrail"}:
        for field in ("port", "scheme", "verify_tls", "source", "user_type", "region", "api_version"):
            if field in original[0]:
                assert node.set_credential()[field] == original[0][field], (model_id, field)

    expected_secret = "vault-token" if type_key == "token" else "vault-auth" if type_key == "snmp" else "vault-secret"
    if case["source"] == "inline":
        expected_secret = "page-token" if type_key == "token" else "page-auth" if type_key == "snmp" else "page-secret"
    assert any(expected_secret in (config.get("env_config") or {}).values() for config in configs)
    assert all(expected_secret not in config["content"] for config in configs)

    update_attrs, _, _ = CollectModelService.format_params(copy.deepcopy(case["edit"]))
    CollectModelService.format_update_credential(task, update_attrs)
    update_pool = CollectCredentialPoolService.normalize_pool(update_attrs["credential"])
    CollectModelService._bind_vault_credentials(request, update_pool, original)
    update_attrs["credential"] = CollectCredentialPoolService.assign_versions(original, update_pool)
    CollectCredentialPoolService.validate_pool_shape(update_attrs["credential"])
    update = CollectModelSerializer(task, data=update_attrs, partial=True, context={"request": request})
    assert update.is_valid(), update.errors
    task = update.save()
    task.refresh_from_db()
    assert task.decrypt_credentials == original
    assert NodeParamsFactory.get_node_params(task).credential == node.credential
