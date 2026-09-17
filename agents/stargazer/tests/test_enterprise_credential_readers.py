"""企业入口必须保留 Stargazer 原始认证字段，不能被占位构造器丢弃。"""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / "agents/stargazer"
SOURCE = ROOT / "enterprise/agents/stargazer/enterprise/plugins/inputs"
sys.path.insert(0, str(AGENT))
SNMP = ("f5", "security_device", "tape_library", "macrosan")
DATABASE = ("couchbase", "sap_hana", "iris", "tongrds", "tdsql")
API = ("ibm_storwize", "emc_symmetrix", "oraclezfs", "infinidat", "netapp_cluster")
VERIFIED = SNMP + DATABASE + API + ("ambari",)


def load_file(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def collector_class(monkeypatch):
    helper_name = "enterprise.plugins.inputs.account_inventory"
    monkeypatch.setitem(sys.modules, helper_name, load_file(helper_name, SOURCE / "account_inventory.py"))

    def load(model_id):
        module = load_file("source_" + model_id, SOURCE / model_id / (model_id + "_info.py"))
        name = "".join(part.capitalize() for part in model_id.split("_")) + "Info"
        return getattr(module, name)

    return load


@pytest.mark.parametrize("model_id", VERIFIED)
def test_actual_entry_consumes_credentials(collector_class, model_id):
    kwargs = {
        "host": "192.0.2.10",
        "port": 1443,
        "snmp_port": 1161,
        "user": "audit-user",
        "username": "audit-user",
        "password": "audit-secret",
        "version": "v2",
        "community": "audit-community",
        "verify_tls": False,
        "namespace": "CUSTOM",
        "bucket": "inventory",
    }
    obj = collector_class(model_id)(kwargs)
    if model_id in SNMP:
        assert obj._get_snmp_auth().communityName == "audit-community"
        assert obj.snmp_port == 1161
    elif model_id in DATABASE or model_id == "ambari":
        assert (obj.user, obj.password) == ("audit-user", "audit-secret")
        assert (obj.ambari_port if model_id == "ambari" else obj.port) == 1443
        if model_id == "iris":
            assert obj.namespace == "CUSTOM"
        if model_id == "couchbase":
            assert obj.bucket == "inventory"
    else:
        assert (obj.username, obj.password, obj.port) == ("audit-user", "audit-secret", 1443)
        assert obj.verify_tls is False


@pytest.mark.parametrize("model_id", VERIFIED)
def test_no_target_does_not_fabricate_success(collector_class, model_id):
    with pytest.raises(ValueError):
        collector_class(model_id)({"host": "", "username": "a", "password": "b"})


@pytest.mark.parametrize("model_id", SNMP)
@pytest.mark.parametrize(
    "level,auth,privacy", [("noauthnopriv", "", ""), ("authnopriv", "auth-key-123", ""), ("authpriv", "auth-key-123", "priv-key-123")]
)
def test_snmp_v3_fields_match_vault_keys(collector_class, model_id, level, auth, privacy):
    obj = collector_class(model_id)(
        {
            "host": "192.0.2.10",
            "version": "v3",
            "username": "audit-user",
            "level": level,
            "integrity": "sha",
            "privacy": "aes",
            "authkey": auth,
            "privkey": privacy,
            "snmp_port": 1161,
        }
    )
    security = obj._get_snmp_auth()
    assert security.userName == "audit-user"
    assert bool(security.authKey) == bool(auth)
    assert bool(security.privKey) == bool(privacy)


def test_tdsql_uses_native_connection_kwargs(collector_class, monkeypatch):
    from plugins.inputs.tdsql import tdsql_info

    calls = []
    monkeypatch.setattr(tdsql_info, "pymysql", SimpleNamespace(connect=lambda **kw: calls.append(kw)))
    obj = collector_class("tdsql")({"host": "192.0.2.10", "username": "audit-user", "password": "audit-secret", "port": 3307})
    obj._connect()
    assert calls[0]["user"] == "audit-user"
    assert calls[0]["password"] == "audit-secret"
    assert calls[0]["port"] == 3307


@pytest.mark.parametrize(
    "model_id", ("couchbase", "sap_hana", "iris", "tongrds", "ambari", "ibm_storwize", "emc_symmetrix", "oraclezfs", "infinidat")
)
def test_unimplemented_inventory_is_explicit(collector_class, model_id):
    obj = collector_class(model_id)({"host": "192.0.2.10", "username": "audit-user", "password": "audit-secret", "port": 443})
    with pytest.raises(NotImplementedError, match="inventory|Inventory"):
        obj.list_all_resources()


@pytest.mark.parametrize("model_id", SNMP)
def test_snmp_entry_keeps_udp_preflight(model_id):
    from core.collection.request_builder import _apply_preflight_defaults

    params = {"snmp_port": 161}
    _apply_preflight_defaults(params, model_id, "configuration")
    assert params["preflight_kind"] == "snmp"


@pytest.mark.asyncio
@pytest.mark.parametrize("model_id", SNMP)
async def test_snmp_entry_uses_real_collector_and_keeps_its_result_model(collector_class, monkeypatch, model_id):
    from plugins.inputs.network.snmp_facts import SnmpFacts

    calls = []

    async def collect(self):
        calls.append((self.community, self.snmp_port))
        return {"system": {"ip_addr": self.host, "sysname": "device-from-response"}, "interfaces": []}

    monkeypatch.setattr(SnmpFacts, "collect", collect)
    obj = collector_class(model_id)({"host": "192.0.2.10", "version": "v2", "community": "audit-community", "snmp_port": 1161})
    result = await obj.list_all_resources()
    assert result == {"success": True, "result": {model_id: [{"ip_addr": "192.0.2.10", "sysname": "device-from-response"}]}}
    assert calls == [("audit-community", 1161)]


@pytest.mark.asyncio
async def test_netapp_cluster_reaches_existing_rest_authentication(collector_class, monkeypatch):
    from plugins.inputs.netapp_ontap import netapp_ontap_info

    calls = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["verify"] is True

        async def get(self, url, **kwargs):
            calls.append((url, kwargs["auth"]))
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"uuid": "array-1", "name": "observed-cluster"} if url.endswith("/cluster") else {"records": []},
                raise_for_status=lambda: None,
            )

        async def aclose(self):
            pass

    monkeypatch.setattr(netapp_ontap_info.httpx, "AsyncClient", Client)
    obj = collector_class("netapp_cluster")({"host": "192.0.2.10", "username": "audit-user", "password": "audit-secret", "port": 1443})
    result = await obj.list_all_resources()
    assert result["success"] is True
    assert result["result"]["netapp_cluster"][0]["device_sn"] == "array-1"
    assert calls and all(auth == ("audit-user", "audit-secret") for _, auth in calls)
    assert all(url.startswith("https://192.0.2.10:1443/") for url, _ in calls)
