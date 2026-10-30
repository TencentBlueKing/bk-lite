import time
from types import SimpleNamespace

import pytest

from apps.cmdb.collection.plugins.community.custom_script.generic import CustomScriptCollectionPlugin
from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.custom_collect_plugin import CustomCollectPlugin
from apps.cmdb.node_configs.custom_script import CustomScriptNodeParams
from apps.cmdb.services.custom_collect_plugin import validate_plugin_payload
from apps.cmdb.services.encrypt_collect_password import get_collect_model_passwords

SCRIPT = '#!/bin/bash\necho \'[{"inst_name":"demo"}]\'\n'


def _plugin_payload():
    return validate_plugin_payload(
        {
            "name": "自定义主机",
            "plugin_id": "custom_host_scan",
            "model_id": "host",
            "os_type": "linux",
            "shell": "bash",
            "content": SCRIPT,
            "team": [1],
        }
    )


def test_custom_script_host_targets_keep_management_ip():
    from apps.cmdb.serializers.collect_serializer import CollectModelSerializer

    host_uuid = "6f1d7b8e-3c2a-4f61-9b2e-1a2b3c4d5e6f"
    serializer = CollectModelSerializer.__new__(CollectModelSerializer)
    serializer._query_authorized_instances = lambda uuids: [
        {"inst_uuid": uuids[0], "model_id": "host", "inst_name": "demo-host", "ip_addr": "10.0.0.8"}
    ]
    attrs = {"instances": [{"inst_uuid": host_uuid}], "ip_range": ""}
    serializer._normalize_custom_script_targets(attrs)
    assert attrs["instances"][0]["ip_addr"] == "10.0.0.8"
    assert attrs["instances"][0]["model_id"] == "host"
    assert attrs["ip_range"] == ""


def test_job_collect_custom_script_follows_target_model_not_os():
    from apps.cmdb.collection.collect_tasks.custom_script import CustomScriptCollect
    from apps.cmdb.collection.collect_tasks.job_collect import JobCollect

    def task(model_id, os_type):
        return SimpleNamespace(
            id=25,
            model_id=model_id,
            task_type=CollectPluginTypes.CUSTOM_SCRIPT,
            team=[1],
            params={"os_type": os_type},
            instances=[],
            is_k8s=False,
            is_host=False,
        )

    linux_host = CustomScriptCollect(25, task=task("host", "linux"))
    windows_host = CustomScriptCollect(25, task=task("host", "windows"))
    nginx = CustomScriptCollect(28, task=task("nginx", "windows"))
    assert linux_host.filter_collect_task is False
    assert windows_host.filter_collect_task is False
    assert nginx.filter_collect_task is True
    assert JobCollect(task=task("nginx", "linux")).collect_manage[CollectPluginTypes.CUSTOM_SCRIPT].__func__ is JobCollect.collect_custom_script


def test_custom_plugin_list_filter_uses_plugin_pk():
    from unittest.mock import MagicMock

    from apps.cmdb.filters.collect_filters import CollectModelFilter

    queryset = MagicMock()
    CollectModelFilter.filter_custom_plugin_pk(queryset, "custom_plugin_pk", "7")
    queryset.filter.assert_called_once_with(params__contains={"custom_plugin_pk": 7})
    assert CollectModelFilter.filter_custom_plugin_pk(queryset, "custom_plugin_pk", "bad") == queryset.none.return_value


def test_validate_keeps_custom_script_identity_when_builtin_host_form_submits(monkeypatch):
    """同模型内置主机表单提交 task_type=host 时，不能丢掉自定义插件归属。"""
    from apps.cmdb.serializers.collect_serializer import CollectModelSerializer

    plugin = SimpleNamespace(id=7, model_id="host", os_type="linux", team=[1])
    monkeypatch.setattr(
        "apps.cmdb.services.custom_script_credentials.load_plugin",
        lambda plugin_pk: plugin if int(plugin_pk) == 7 else None,
    )
    serializer = CollectModelSerializer.__new__(CollectModelSerializer)
    serializer.parent = None
    serializer.instance = SimpleNamespace(
        task_type=CollectPluginTypes.CUSTOM_SCRIPT,
        model_id="host",
        driver_type="job",
        params={"custom_plugin_pk": 7, "os_type": "linux"},
        team=[1],
        instances=[],
        ip_range="10.0.0.1-10.0.0.2",
        timeout=60,
    )
    serializer._context = {"request": SimpleNamespace(user=SimpleNamespace(is_superuser=True), COOKIES={})}
    result = serializer.validate(
        {
            "task_type": "host",
            "model_id": "host",
            "driver_type": "job",
            "team": [1],
            "ip_range": "10.0.0.1-10.0.0.2",
            "instances": [],
            "params": {"ip_precheck": True},
            "timeout": 60,
        }
    )
    assert result["task_type"] == CollectPluginTypes.CUSTOM_SCRIPT
    assert result["params"]["custom_plugin_pk"] == 7
    assert result["model_id"] == "host"


def test_update_keeps_the_task_plugin_when_another_plugin_is_selected(monkeypatch):
    from apps.cmdb.serializers.collect_serializer import CollectModelSerializer

    plugins = {
        4: SimpleNamespace(id=4, model_id="host", os_type="linux", team=[1]),
        5: SimpleNamespace(id=5, model_id="host", os_type="windows", team=[1]),
    }
    monkeypatch.setattr("apps.cmdb.services.custom_script_credentials.load_plugin", lambda plugin_pk: plugins.get(int(plugin_pk)))
    serializer = CollectModelSerializer.__new__(CollectModelSerializer)
    serializer.parent = None
    serializer.instance = SimpleNamespace(params={"custom_plugin_pk": 4}, model_id="host")
    serializer._context = {}
    attrs = {"params": {"custom_plugin_pk": 5}, "model_id": "host"}
    serializer._apply_custom_script_contract(attrs)
    assert attrs["params"]["custom_plugin_pk"] == 4
    assert attrs["params"]["os_type"] == "linux"


def test_custom_script_transport_fields_do_not_depend_on_model_tree():
    assert get_collect_model_passwords("host", "job", task_type=CollectPluginTypes.CUSTOM_SCRIPT) == [
        "password",
        "private_key",
        "passphrase",
    ]


@pytest.mark.django_db
def test_node_params_headers_carry_plugin_identity_not_script_body():
    plugin = CustomCollectPlugin.objects.create(**_plugin_payload())
    task = CollectModels(
        id=7,
        name="custom-host",
        model_id="host",
        driver_type="job",
        task_type=CollectPluginTypes.CUSTOM_SCRIPT,
        timeout=120,
        credential={"username": "root", "password": "plain-pass", "port": 22},
        access_point=[{"id": "node-1", "ip": "10.0.0.1"}],
        params={"custom_plugin_pk": plugin.id},
        instances=[],
    )
    node = CustomScriptNodeParams(task, resolve_credentials=False)
    headers = node.custom_headers()
    rendered = " ".join(headers.values())
    assert headers["cmdbcustom_plugin_id"] == "custom_host_scan"
    assert headers["cmdbos_type"] == "linux"
    assert headers["cmdbnode_id"] == "node-1"
    assert "echo" not in rendered
    assert plugin.content not in rendered


@pytest.mark.django_db
def test_format_plugin_keeps_model_fields_and_drops_blank_inst_name(monkeypatch):
    plugin = CustomCollectPlugin.objects.create(**_plugin_payload())
    task = CollectModels.objects.create(
        name="custom-host",
        model_id="host",
        driver_type="job",
        task_type=CollectPluginTypes.CUSTOM_SCRIPT,
        cycle_value_type="cycle",
        params={"custom_plugin_pk": plugin.id},
    )
    monkeypatch.setattr(
        "apps.cmdb.collection.plugins.community.custom_script.generic.ModelManage.search_model_attr",
        lambda model_id: [
            {"attr_id": "inst_name", "attr_type": "str"},
            {"attr_id": "port", "attr_type": "int"},
        ],
    )
    collector = CustomScriptCollectionPlugin("task", task.id, task.id, collect_inst=task)
    now = int(time.time())
    collector.format_data(
        {
            "result": [
                {"metric": {"__name__": "custom_host_scan_info", "inst_name": "demo", "port": "8", "agent_id": "x"}, "value": [now, "1"]},
                {"metric": {"__name__": "custom_host_scan_info", "port": "9"}, "value": [now, "1"]},
            ]
        }
    )
    collector.format_metrics()
    assert collector.result["host"] == [{"inst_name": "demo", "port": 8}]
    assert collector._dropped_records == 1


def test_custom_script_host_record_inherits_access_point_cloud(monkeypatch):
    plugin = SimpleNamespace(plugin_id="custom_host_linux_scan")
    task = SimpleNamespace(
        id=29,
        params={"custom_plugin_pk": 4},
        model_id="host",
        instances=[],
        access_point={"cloud_region": 1, "id": "node-1"},
    )
    monkeypatch.setattr(CustomScriptCollectionPlugin, "_plugin", lambda self: plugin)
    monkeypatch.setattr(
        "apps.cmdb.collection.plugins.community.custom_script.generic.ModelManage.search_model_attr",
        lambda model_id: [
            {"attr_id": "inst_name", "attr_type": "str"},
            {"attr_id": "ip_addr", "attr_type": "str"},
            {"attr_id": "cloud", "attr_type": "int"},
        ],
    )
    collector = CustomScriptCollectionPlugin("task", 29, 29, collect_inst=task)
    collector.format_data(
        {
            "result": [
                {
                    "metric": {
                        "__name__": "custom_host_linux_scan_info_gauge",
                        "inst_name": "demo-host-v2",
                        "ip_addr": "10.10.41.149",
                    },
                    "value": [int(time.time()), "1"],
                }
            ]
        }
    )
    collector.format_metrics()
    assert collector.result["host"] == [{"inst_name": "demo-host-v2", "ip_addr": "10.10.41.149", "cloud": 1}]


def test_network_custom_script_writes_device_models_not_network(monkeypatch):
    task = SimpleNamespace(id=14, params={}, model_id="network", instances=[])

    def boom(model_id):
        raise AssertionError(model_id)

    monkeypatch.setattr(CustomScriptCollectionPlugin, "_plugin", lambda self: SimpleNamespace(plugin_id="custom_network"))
    monkeypatch.setattr("apps.cmdb.collection.plugins.community.custom_script.generic.ModelManage.search_model_attr", boom)
    monkeypatch.setattr(
        "apps.cmdb.collection.plugins.community.custom_script.generic._existing_device_models",
        lambda names: {"10.10.69.1-firewall": "firewall"} if "10.10.69.1-firewall" in names else {},
    )
    collector = CustomScriptCollectionPlugin("task", 14, 14, collect_inst=task)
    now = int(time.time())
    collector.format_data(
        {
            "result": [
                {
                    "metric": {
                        "__name__": "custom_network_info_gauge",
                        "inst_name": "10.10.69.247-switch",
                        "model_id": "switch",
                        "sys_desc": "custom",
                        "sysdescr": "raw",
                    },
                    "value": [now, "1"],
                },
                {
                    "metric": {"__name__": "custom_network_info_gauge", "inst_name": "r1", "device_type": "router", "soid": "1.2.3"},
                    "value": [now, "1"],
                },
                {
                    "metric": {"__name__": "custom_network_info_gauge", "inst_name": "10.10.69.1-firewall", "sys_desc": "fw"},
                    "value": [now, "1"],
                },
                {
                    "metric": {"__name__": "custom_network_info_gauge", "inst_name": "unknown", "brand": "H3C"},
                    "value": [now, "1"],
                },
            ]
        }
    )
    collector.format_metrics()
    assert "network" not in collector.result
    assert collector.result["switch"] == [
        {"inst_name": "10.10.69.247-switch", "sys_desc": "custom"},
        {"inst_name": "unknown", "brand": "H3C"},
    ]
    assert collector.result["router"] == [{"inst_name": "r1", "soid": "1.2.3"}]
    assert collector.result["firewall"] == [{"inst_name": "10.10.69.1-firewall", "sys_desc": "fw"}]


def test_custom_script_sync_queries_the_vm_gauge_series(monkeypatch):
    plugin = SimpleNamespace(plugin_id="custom_host_linux_scan")
    task = SimpleNamespace(id=29, params={"custom_plugin_pk": 7}, model_id="host", instances=[])
    monkeypatch.setattr(CustomScriptCollectionPlugin, "_plugin", lambda self: plugin)
    collector = CustomScriptCollectionPlugin("task", 29, 29, collect_inst=task)
    assert collector._metrics == ["custom_host_linux_scan_info_gauge"]
    assert collector.prom_sql() == "custom_host_linux_scan_info_gauge{instance_id='cmdb_29'}"


def test_task_type_constant_is_custom_script():
    assert CollectPluginTypes.CUSTOM_SCRIPT == "custom_script"
    assert SimpleNamespace(task_type=CollectPluginTypes.CUSTOM_SCRIPT).task_type != "host"


TASK_ID = 6613


def _saved_passwords(*passwords):
    return [{"username": f"user-{index}", "password": password, "port": 5986} for index, password in enumerate(passwords)]


def _custom_script_node(monkeypatch, *, os_type, credentials):
    plugin = SimpleNamespace(
        id=7,
        plugin_id="custom_host_scan",
        os_type=os_type,
        shell="powershell" if os_type == "windows" else "bash",
        team=[1],
    )
    monkeypatch.setattr("apps.cmdb.node_configs.custom_script.load_plugin", lambda plugin_pk: plugin)
    task = SimpleNamespace(
        id=TASK_ID,
        model_id="host",
        driver_type="job",
        task_type=CollectPluginTypes.CUSTOM_SCRIPT,
        timeout=120,
        access_point=[{"id": "node-1", "ip": "10.0.0.1"}],
        params={"custom_plugin_pk": plugin.id, "os_type": os_type},
        instances=[],
        ip_range="",
    )
    return CustomScriptNodeParams(task, resolved_credentials=credentials)


def _assert_indexed_password_envs(node, passwords):
    env = node.env_config()
    headers = node.custom_headers()
    rendered = " ".join(headers.values())
    for index, password in enumerate(passwords):
        env_name = f"PASSWORD_password_cmdb_{TASK_ID}_{index}"
        assert env[env_name] == password
        assert headers[f"cmdbcredential_{index}_password"] == "${" + env_name + "}"
        assert password not in rendered
    assert f"PASSWORD_password_cmdb_{TASK_ID}" not in env


def test_windows_two_saved_passwords_publish_indexed_env(monkeypatch):
    passwords = ("saved-win-0", "saved-win-1")
    node = _custom_script_node(monkeypatch, os_type="windows", credentials=_saved_passwords(*passwords))
    _assert_indexed_password_envs(node, passwords)


def test_windows_three_saved_passwords_publish_indexed_env(monkeypatch):
    passwords = ("saved-win-0", "saved-win-1", "saved-win-2")
    node = _custom_script_node(monkeypatch, os_type="windows", credentials=_saved_passwords(*passwords))
    _assert_indexed_password_envs(node, passwords)


def test_windows_single_password_keeps_unindexed_env_name(monkeypatch):
    password = "saved-win-only"
    node = _custom_script_node(monkeypatch, os_type="windows", credentials=_saved_passwords(password))
    env = node.env_config()
    headers = node.custom_headers()
    env_name = f"PASSWORD_password_cmdb_{TASK_ID}"
    assert env == {env_name: password}
    assert headers["cmdbpassword"] == "${" + env_name + "}"
    assert "cmdbcredential_0_password" not in headers
    assert password not in " ".join(headers.values())


@pytest.mark.parametrize(
    ("passwords", "indexed"),
    [
        (("saved-linux-only",), False),
        (("saved-linux-0", "saved-linux-1"), True),
    ],
)
def test_linux_password_env_names_follow_parent(monkeypatch, passwords, indexed):
    node = _custom_script_node(monkeypatch, os_type="linux", credentials=_saved_passwords(*passwords))
    if indexed:
        _assert_indexed_password_envs(node, passwords)
        return
    env = node.env_config()
    headers = node.custom_headers()
    env_name = f"PASSWORD_password_cmdb_{TASK_ID}"
    assert env == {env_name: passwords[0]}
    assert headers["cmdbpassword"] == "${" + env_name + "}"
    assert passwords[0] not in " ".join(headers.values())
