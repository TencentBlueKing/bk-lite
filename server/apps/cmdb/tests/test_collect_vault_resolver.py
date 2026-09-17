from types import SimpleNamespace

import pytest

from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_vault_binding import COLLECT_VAULT_BINDINGS, actual_builtin_type_keys, binding_for_collect_object
from apps.cmdb.services.collect_vault_resolver import resolve_task_credential_pool
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES

ACTOR = {"username": "operator", "domain": "example.com", "current_team": 3}

AUTH_BY_BINDING = {
    "network/sql": ({"username": "ops", "password": "vault-secret"}, "username", "ops"),
    "host/sql": ({"username": "ops", "password": "vault-secret"}, "username", "ops"),
    "storage/cloud": ({"access_key": "ak", "secret_key": "vault-secret"}, "accessKey", "ak"),
    "storage/snmp": ({"version": "v2c", "community": "vault-secret"}, "version", "v2"),
    "host/ssh": ({"username": "ops", "password": "vault-secret", "auth_method": "password"}, "username", "ops"),
    "host/winrm": ({"username": "ops", "password": "vault-secret"}, "username", "ops"),
    "host/ipmi": ({"username": "ops", "password": "vault-secret"}, "username", "ops"),
    "host/redfish": ({"username": "ops", "password": "vault-secret"}, "username", "ops"),
    "network/snmp": ({"version": "v2c", "community": "vault-secret"}, "version", "v2"),
    "network/platform_api": ({"username": "ops", "password": "vault-secret"}, "username", "ops"),
    "database/sql": ({"username": "db", "password": "vault-secret"}, "user", "db"),
    "database/token": ({"token": "vault-secret"}, "token", "vault-secret"),
    "middleware/sql": ({"username": "db", "password": "vault-secret"}, "user", "db"),
    "cloud/cloud": ({"access_key": "ak", "secret_key": "vault-secret"}, "accessKey", "ak"),
    "cloud/openstack": ({"username": "ops", "password": "vault-secret", "user_domain_name": "Domain"}, "user_domain_name", "Domain"),
    "cloud/oauth_client": ({"client_id": "client", "client_secret": "vault-secret", "tenant_id": "tenant"}, "username", "client"),
    "cloud/platform_api": ({"username": "ops", "password": "vault-secret"}, "username", "ops"),
    "storage/platform_api": ({"username": "ops", "password": "vault-secret"}, "username", "ops"),
}
for category in ("network", "database", "middleware"):
    AUTH_BY_BINDING[category + "/ssh"] = ({"username": "ops", "password": "vault-secret", "auth_method": "password"}, "username", "ops")


def test_snmp_vault_task_keeps_port_but_not_page_auth_version():
    pool = CollectCredentialPoolService.normalize_pool(
        [
            {
                "credential_source": "vault",
                "vault_type_key": "snmp",
                "vault_credential_id": "crd-snmp-1",
                "snmp_port": 1161,
                "version": "v2",
                "community": "stale-page-secret",
            }
        ]
    )
    assert pool[0]["snmp_port"] == 1161
    assert pool[0]["vault_credential_id"] == "crd-snmp-1"
    assert "version" not in pool[0]
    assert "community" not in pool[0]


def test_old_snmp_vault_task_uses_credential_version_at_dispatch(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda binding: ["snmp"])
    task = SimpleNamespace(
        model_id="network",
        driver_type="protocol",
        params={},
        decrypt_credentials=[
            {
                "credential_source": "vault",
                "vault_credential_id": "crd-snmp-1",
                "vault_actor_context": ACTOR,
                "snmp_port": 1161,
                "version": "v2",
                "community": "stale-page-secret",
            }
        ],
    )
    result = resolve_task_credential_pool(
        task,
        resolver=lambda actor, credential_id: {
            "result": True,
            "data": {
                "type": "snmp",
                "fields": {
                    "version": "v3",
                    "security_level": "authPriv",
                    "username": "snmp",
                    "auth_protocol": "SHA",
                    "auth_password": "vault-auth",
                    "priv_protocol": "AES",
                    "priv_password": "vault-priv",
                },
            },
        },
    )[0]
    assert result["version"] == "v3"
    assert result["snmp_port"] == 1161
    assert result["authkey"] == "vault-auth"
    assert "stale-page-secret" not in result.values()


@pytest.mark.parametrize("binding,object_id", [(binding, object_id) for binding, ids in COLLECT_VAULT_BINDINGS.items() for object_id in ids])
def test_every_bound_plugin_has_an_explicit_category_and_type(binding, object_id):
    assert binding_for_collect_object(object_id) == binding


@pytest.mark.parametrize("binding,object_id", [(binding, object_id) for binding, ids in COLLECT_VAULT_BINDINGS.items() for object_id in ids])
def test_every_plugin_converts_selected_vault_auth_before_dispatch(monkeypatch, binding, object_id):
    fields, converted_key, expected_value = AUTH_BY_BINDING[binding]
    type_key = binding.split("/")[1]
    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda candidate: [type_key])
    task = SimpleNamespace(
        model_id=object_id,
        driver_type="protocol",
        params={},
        decrypt_credentials=[
            {
                "credential_source": "vault",
                "vault_credential_id": "crd-1",
                "vault_actor_context": ACTOR,
                "port": 1234,
                "password": "stale-task-secret",
            }
        ],
    )
    result = resolve_task_credential_pool(
        task,
        resolver=lambda actor, credential_id: {"result": True, "data": {"type": type_key, "fields": fields}},
    )[0]
    assert result[converted_key] == expected_value
    assert result["port"] == 1234
    assert "vault_credential_id" not in result
    assert "stale-task-secret" not in result.values()


@pytest.mark.parametrize("binding,object_id", [(binding, object_id) for binding, ids in COLLECT_VAULT_BINDINGS.items() for object_id in ids])
def test_every_plugin_binding_matches_builtin_credential_directory(binding, object_id):
    category, key = binding.split("/")
    definition = BUILTIN_TYPES[key]
    row = SimpleNamespace(key=key, is_builtin=True, categories=definition["categories"], fields=definition["fields"])
    assert actual_builtin_type_keys(binding, [row]) == [key], object_id


def test_mapping_covers_all_116_authenticating_tree_entries():
    assert sum(len(ids) for ids in COLLECT_VAULT_BINDINGS.values()) == 116
    assert len({object_id for ids in COLLECT_VAULT_BINDINGS.values() for object_id in ids}) == 116


@pytest.mark.parametrize(
    "model_id,driver_type,expected",
    [
        ("oracle", "protocol", "database/sql"),
        ("network_topo", "protocol", "network/snmp"),
        ("aliyun", "protocol", "cloud/cloud"),
        ("keepalived", "job", "middleware/ssh"),
        ("postgresql", "job", "database/sql"),
        ("mysql", "job", "database/sql"),
    ],
)
def test_directory_external_and_alternate_driver_bindings(model_id, driver_type, expected):
    assert binding_for_collect_object(model_id, model_id=model_id, driver_type=driver_type) == expected


def test_region_lookup_uses_selected_vault_id_and_current_actor(monkeypatch):
    from apps.cmdb.views.collect import CollectModelViewSet

    class RegionParams:
        @staticmethod
        def build_region_credential(raw):
            first = raw[0]
            return {"secret_id": first["accessKey"], "secret_key": first["accessSecret"]}

    monkeypatch.setattr("apps.cmdb.views.collect.NodeParamsFactory.get_params_class", lambda model, driver: RegionParams)
    monkeypatch.setattr("apps.cmdb.views.collect.get_current_team_from_request", lambda request: 7)
    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda binding: ["cloud"])
    seen = []

    def resolve(actor, credential_id):
        seen.append((actor, credential_id))
        return {"result": True, "data": {"type": "cloud", "fields": {"access_key": "ak", "secret_key": "sk"}}}

    monkeypatch.setattr(
        "apps.cmdb.services.collect_vault_resolver.SystemMgmt.resolve_credential", lambda self, actor, credential_id: resolve(actor, credential_id)
    )
    request = SimpleNamespace(user=SimpleNamespace(username="now", domain="tenant"))
    result = CollectModelViewSet()._build_region_query_credential(
        request, {"model_id": "qcloud", "vault_credential_id": "crd-1", "access_key": "page-ak", "access_secret": "page-sk"}
    )
    assert result["secret_id"] == "ak"
    assert result["secret_key"] == "sk"
    assert "vault_credential_id" not in result
    assert seen == [({"username": "now", "domain": "tenant", "current_team": 7}, "crd-1")]


@pytest.mark.parametrize(
    "protocol,type_key,fields,expected",
    [
        ("snmp", "snmp", {"version": "v2c", "community": "vault-community"}, {"version": "v2", "community": "vault-community"}),
        ("snmp", "snmp", {"version": "v2", "community": "vault-community"}, {"version": "v2", "community": "vault-community"}),
        ("ipmi", "ipmi", {"username": "admin", "password": "vault-password"}, {"username": "admin", "password": "vault-password"}),
    ],
)
def test_collect_tool_debug_resolves_vault_reference_for_protocol(monkeypatch, protocol, type_key, fields, expected):
    from apps.cmdb.services.collect_tool_service import CollectToolService

    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda binding: [type_key])
    monkeypatch.setattr(
        "apps.cmdb.services.collect_vault_resolver.SystemMgmt.resolve_credential",
        lambda self, actor, credential_id: {"result": True, "data": {"type": type_key, "fields": fields}},
    )
    payload = {"protocol": protocol, "credential": {"credential_source": "vault", "vault_credential_id": "crd-1", "password": "stale"}}
    resolved = CollectToolService.inject_credentials(payload, None, actor_context=ACTOR)["credential"]
    assert all(resolved[key] == value for key, value in expected.items())
    assert "vault_credential_id" not in resolved
    assert "stale" not in resolved.values()


def test_collect_tool_debug_resolves_vault_only_inside_worker(monkeypatch):
    from apps.cmdb.services.collect_tool_service import CollectToolService

    seen = []
    monkeypatch.setattr(CollectToolService, "save_debug_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        CollectToolService,
        "inject_credentials",
        lambda payload, instance, actor_context: (
            seen.append((payload["credential"]["vault_credential_id"], actor_context))
            or {**payload, "credential": {"community": "worker-secret", "version": "v2"}}
        ),
    )
    monkeypatch.setattr(CollectToolService, "execute_debug", lambda payload, **kwargs: (seen.append(payload["credential"]) or {"success": True}))
    queued = {
        "protocol": "snmp",
        "action": "test_connection",
        "target": "10.0.0.1",
        "port": 161,
        "credential": {"credential_source": "vault", "vault_credential_id": "crd-1"},
        "vault_actor_context": ACTOR,
    }
    result = CollectToolService.run_debug_task("debug-1", queued, "default_stargazer", 10)
    assert result["success"] is True
    assert seen == [("crd-1", ACTOR), {"community": "worker-secret", "version": "v2"}]
    assert "vault_actor_context" not in queued


def test_collect_tool_debug_vault_resolution_failure_returns_safe_result(monkeypatch):
    from apps.cmdb.services.collect_tool_service import CollectToolService

    states = []
    monkeypatch.setattr(CollectToolService, "save_debug_state", lambda *args, **kwargs: states.append(args))
    monkeypatch.setattr(CollectToolService, "inject_credentials", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("secret-sentinel")))
    payload = {
        "protocol": "snmp",
        "action": "test_connection",
        "target": "10.0.0.1",
        "port": 161,
        "credential": {"credential_source": "vault", "vault_credential_id": "crd-1"},
        "vault_actor_context": ACTOR,
    }
    result = CollectToolService.run_debug_task("debug-1", payload, "default_stargazer", 10)
    assert result["stage"] == "param"
    assert "secret-sentinel" not in str(result)
    assert states[-1][1] == "error"


def test_saved_vault_task_region_lookup_uses_current_actor_instead_of_old_binding(monkeypatch):
    from apps.cmdb.views.collect import CollectModelViewSet

    class RegionParams:
        @staticmethod
        def build_region_credential(raw):
            return {"secret_id": raw[0]["accessKey"], "secret_key": raw[0]["accessSecret"]}

    old_actor = {"username": "old", "domain": "tenant", "current_team": 2}
    task = SimpleNamespace(
        model_id="qcloud",
        driver_type="protocol",
        params={},
        decrypt_credentials=[{"credential_source": "vault", "vault_credential_id": "crd-1", "vault_actor_context": old_actor}],
    )
    view = CollectModelViewSet()
    monkeypatch.setattr(view, "_get_authorized_task", lambda request, task_id: task)
    monkeypatch.setattr("apps.cmdb.views.collect.NodeParamsFactory.get_params_class", lambda model, driver: RegionParams)
    monkeypatch.setattr("apps.cmdb.views.collect.get_current_team_from_request", lambda request: 7)
    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda binding: ["cloud"])
    seen = []

    def resolve(self, actor, credential_id):
        seen.append(actor)
        return {"result": True, "data": {"type": "cloud", "fields": {"access_key": "ak", "secret_key": "sk"}}}

    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.SystemMgmt.resolve_credential", resolve)
    result = view._build_region_query_credential(
        SimpleNamespace(user=SimpleNamespace(username="now", domain="tenant")),
        {"model_id": "qcloud"},
        task_id=42,
    )
    assert result["secret_id"] == "ak"
    assert seen == [{"username": "now", "domain": "tenant", "current_team": 7}]


def test_type_directory_chooses_actual_builtin_fallback_keys():
    rows = [
        SimpleNamespace(key="redfish", is_builtin=False, categories=["host"]),
        SimpleNamespace(key="redfish_bmc", is_builtin=True, categories=["host"]),
        SimpleNamespace(key="openstack", is_builtin=False, categories=["cloud"]),
        SimpleNamespace(key="openstack_account", is_builtin=True, categories=["cloud"]),
    ]
    assert actual_builtin_type_keys("host/redfish", rows) == ["redfish_bmc"]
    assert actual_builtin_type_keys("cloud/openstack", rows) == ["openstack_account"]


def test_type_directory_rejects_builtin_row_without_required_auth_fields():
    row = SimpleNamespace(
        key="openstack",
        is_builtin=True,
        categories=["cloud"],
        fields=[{"id": "username", "kind": "string"}, {"id": "password", "kind": "secret"}],
    )
    assert actual_builtin_type_keys("cloud/openstack", [row]) == []


@pytest.mark.parametrize(
    "binding,fields,expected",
    [
        ("host/ssh", {"auth_method": "password", "username": "ops", "password": "vault-secret"}, {"username": "ops", "password": "vault-secret"}),
        ("database/sql", {"username": "db", "password": "vault-secret"}, {"user": "db", "password": "vault-secret"}),
        ("cloud/cloud", {"access_key": "ak", "secret_key": "vault-secret"}, {"accessKey": "ak", "accessSecret": "vault-secret"}),
        (
            "cloud/oauth_client",
            {"client_id": "client", "client_secret": "vault-secret", "tenant_id": "tenant"},
            {"username": "client", "password": "vault-secret", "tenant_id": "tenant"},
        ),
        (
            "network/snmp",
            {
                "version": "v3",
                "security_level": "authPriv",
                "username": "snmp",
                "auth_protocol": "SHA",
                "auth_password": "vault-secret",
                "priv_protocol": "AES",
                "priv_password": "priv-secret",
            },
            {"version": "v3", "level": "authpriv", "integrity": "sha", "authkey": "vault-secret", "privacy": "aes", "privkey": "priv-secret"},
        ),
        ("database/token", {"token": "vault-secret"}, {"token": "vault-secret"}),
    ],
)
def test_dispatch_resolves_key_conversion_and_preserves_dynamic_fields(monkeypatch, binding, fields, expected):
    object_id = "pc" if binding == "host/ssh" else COLLECT_VAULT_BINDINGS[binding][0]
    key = binding.split("/")[1]
    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda candidate: [key])
    calls = []

    def resolve(actor, credential_id):
        calls.append((actor, credential_id))
        return {"result": True, "data": {"type": key, "fields": fields}}

    task = SimpleNamespace(
        model_id=object_id,
        driver_type="protocol",
        params={"os_type": "macos"} if binding == "host/ssh" else {},
        decrypt_credentials=[
            {
                "credential_id": "cred-1",
                "credential_source": "vault",
                "vault_credential_id": "crd-1",
                "vault_actor_context": ACTOR,
                "port": 1234,
                "password": "must-not-copy",
            }
        ],
    )
    resolved = resolve_task_credential_pool(task, resolver=resolve)[0]
    assert calls == [(ACTOR, "crd-1")]
    assert resolved["port"] == 1234
    assert all(resolved[field] == value for field, value in expected.items())
    assert "vault_credential_id" not in resolved
    assert "vault_actor_context" not in resolved


def test_dispatch_rejects_disabled_or_type_mismatched_reference(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda candidate: ["sql"])
    task = SimpleNamespace(
        model_id="mysql",
        driver_type="protocol",
        params={},
        decrypt_credentials=[{"credential_source": "vault", "vault_credential_id": "crd-1", "vault_actor_context": ACTOR, "port": 3306}],
    )
    with pytest.raises(BaseAppException):
        resolve_task_credential_pool(task, resolver=lambda actor, credential_id: {"result": False, "message": "disabled"})
    with pytest.raises(BaseAppException):
        resolve_task_credential_pool(
            task, resolver=lambda actor, credential_id: {"result": True, "data": {"type": "ssh", "fields": {"username": "ops"}}}
        )


def test_dispatch_rejects_old_incomplete_builtin_credential_without_sending_empty_secret(monkeypatch):
    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda binding: ["sql"])
    task = SimpleNamespace(
        model_id="mysql",
        driver_type="protocol",
        params={},
        decrypt_credentials=[{"credential_source": "vault", "vault_credential_id": "crd-1", "vault_actor_context": ACTOR, "port": 3306}],
    )
    with pytest.raises(BaseAppException, match="认证字段不完整"):
        resolve_task_credential_pool(
            task,
            resolver=lambda actor, credential_id: {"result": True, "data": {"type": "sql", "fields": {"username": "db"}}},
        )


@pytest.mark.parametrize("type_key", ["ssh", "platform_api"])
@pytest.mark.parametrize("protocol,port", [("ssh", 2222), ("telnet", 2323)])
def test_network_config_uses_ssh_and_preserves_legacy_account_and_supplemental_enable(monkeypatch, type_key, protocol, port):
    assert binding_for_collect_object("network_config_file") == "network/ssh"
    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda binding: [binding.split("/")[1]])
    raw = {
        "credential_source": "vault",
        "vault_type_key": type_key,
        "vault_credential_id": "crd-platform",
        "vault_actor_context": ACTOR,
        "transport_protocol": protocol,
        "port": port,
        "username": "stale-user",
        "password": "stale-password",
        "enable_password": "extra-secret",
    }
    stored = CollectCredentialPoolService.normalize_pool([raw])[0]
    assert stored["enable_password"] == "extra-secret"
    assert "password" not in stored
    task = SimpleNamespace(model_id="network_config_file", driver_type="protocol", params={}, decrypt_credentials=[stored])
    actual = resolve_task_credential_pool(
        task,
        resolver=lambda actor, credential_id: {
            "result": True,
            "data": {"type": type_key, "fields": {"username": "vault-user", "password": "vault-secret", "auth_method": "password"}},
        },
    )[0]
    assert actual["username"] == "vault-user"
    assert actual["password"] == "vault-secret"
    assert actual["enable_password"] == "extra-secret"
    assert actual["transport_protocol"] == protocol
    assert actual["port"] == port


@pytest.mark.parametrize("extra,expected", [("******", "extra-secret"), ("", ""), ("replacement", "replacement")])
@pytest.mark.parametrize("type_key,new_reference", [("platform_api", "crd-platform"), ("ssh", "crd-platform"), ("ssh", "crd-new-ssh")])
def test_network_vault_edit_keeps_or_clears_extra_secret(extra, expected, type_key, new_reference):
    from apps.cmdb.services.collect_service import CollectModelService

    old = {
        "credential_id": "candidate",
        "credential_source": "vault",
        "vault_type_key": "platform_api",
        "vault_credential_id": "crd-platform",
        "enable_password": "extra-secret",
        "port": 22,
    }
    task = SimpleNamespace(model_id="network_config_file", driver_type="protocol", is_k8s=False, decrypt_credentials=[old])
    data = {
        "credential": [
            {**old, "vault_type_key": type_key, "vault_credential_id": new_reference, "enable_password": extra, "password": "stale-password"}
        ]
    }
    CollectModelService.format_update_credential(task, data)
    assert data["credential"][0]["enable_password"] == expected
    assert "password" not in data["credential"][0]


@pytest.mark.parametrize("protocol", ["ssh", "telnet"])
def test_network_config_rejects_private_key_instead_of_dispatching_empty_password(monkeypatch, protocol):
    monkeypatch.setattr("apps.cmdb.services.collect_vault_resolver.actual_builtin_type_keys", lambda binding: [binding.split("/")[1]])
    task = SimpleNamespace(
        model_id="network_config_file",
        driver_type="protocol",
        params={},
        decrypt_credentials=[
            {
                "credential_source": "vault",
                "vault_type_key": "ssh",
                "vault_credential_id": "ssh-key",
                "vault_actor_context": ACTOR,
                "transport_protocol": protocol,
                "port": 22,
            }
        ],
    )
    with pytest.raises(BaseAppException, match="仅支持 SSH 密码凭据"):
        resolve_task_credential_pool(
            task,
            resolver=lambda *_: {
                "result": True,
                "data": {
                    "type": "ssh",
                    "fields": {"username": "ops", "auth_method": "key", "private_key": "test-private-key"},
                },
            },
        )
