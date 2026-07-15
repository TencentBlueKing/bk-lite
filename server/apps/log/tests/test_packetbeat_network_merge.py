import json
import types
from pathlib import Path

import pytest
import yaml

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.models import CollectConfig, CollectInstance, CollectType
from apps.log.services.collect_type import CollectTypeService
from apps.log.utils.plugin_controller import Controller


PLUGIN_DIR = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Packetbeat" / "flows"
COLLECTOR_FILE = (
    Path(__file__).resolve().parents[2] / "node_mgmt" / "support-files" / "collectors" / "Packetbeat.json"
)


def render_flows_child(**context):
    defaults = {
        "instance_id": "packetbeat-network-1",
        "device": "any",
        "enable_http": True,
        "enable_tcp_udp": True,
        "ports": "80,8080,8000,5000,8002",
        "capture_body": False,
        "flows_period": 10,
        "flows_timeout": 30,
    }
    defaults.update(context)
    return Controller({}).render_template(str(PLUGIN_DIR), "flows.child.yaml.j2", defaults)


def load_packetbeat_child_fragment(rendered: str):
    return yaml.safe_load(f"packetbeat.protocols:\n{rendered}")


def test_update_config_parses_packetbeat_flows_child_fragment():
    from apps.log.views.collect_config import parse_collect_config_content

    config = types.SimpleNamespace(
        is_child=True,
        file_type="yaml",
        collect_instance=types.SimpleNamespace(
            collect_type=types.SimpleNamespace(collector="Packetbeat", name="flows")
        ),
    )

    content = parse_collect_config_content(config, render_flows_child())

    assert content["packetbeat.protocols"][0]["type"] == "http"
    assert content["packetbeat.flows"]["period"] == "10s"


@pytest.mark.parametrize(
    ("rendered", "expected"),
    [
        ("key: value\n", {"key": "value"}),
        ("- module: nginx\n", [{"module": "nginx"}]),
    ],
)
def test_update_config_keeps_other_yaml_shapes(rendered, expected):
    from apps.log.views.collect_config import parse_collect_config_content

    config = types.SimpleNamespace(
        is_child=True,
        file_type="yaml",
        collect_instance=types.SimpleNamespace(
            collect_type=types.SimpleNamespace(collector="Filebeat", name="nginx")
        ),
    )

    assert parse_collect_config_content(config, rendered) == expected


def test_update_config_keeps_toml_parsing_without_collect_type_relation():
    from apps.log.views.collect_config import parse_collect_config_content

    config = types.SimpleNamespace(is_child=False, file_type="toml")

    assert parse_collect_config_content(config, 'key = "value"\n') == {"key": "value"}


def test_packetbeat_parent_config_uses_device_template_default():
    collectors = json.loads(COLLECTOR_FILE.read_text(encoding="utf-8"))
    linux_config = next(item for item in collectors if item["id"] == "Packetbeat_linux")["default_config"]["nats"]
    windows_config = next(item for item in collectors if item["id"] == "Packetbeat_windows")["default_config"]["nats"]

    assert 'packetbeat.interfaces.device: "${PACKETBEAT_DEVICE}"' in linux_config
    assert 'packetbeat.interfaces.device: "${PACKETBEAT_DEVICE}"' in windows_config


def test_packetbeat_parent_device_renders_from_child_global_env():
    from apps.node_mgmt.services.sidecar import Sidecar

    collectors = json.loads(COLLECTOR_FILE.read_text(encoding="utf-8"))
    linux_config = next(item for item in collectors if item["id"] == "Packetbeat_linux")["default_config"]["nats"]

    rendered = Sidecar.render_template(linux_config, {"PACKETBEAT_DEVICE": "eth0,eth1"})

    assert 'packetbeat.interfaces.device: "eth0,eth1"' in rendered


def test_flows_template_defaults_enable_http_and_tcp_udp():
    rendered = render_flows_child()
    data = load_packetbeat_child_fragment(rendered)

    assert data["packetbeat.flows"]["period"] == "10s"
    assert data["packetbeat.flows"]["timeout"] == "30s"
    assert data["packetbeat.flows"]["fields"]["collect_type"] == "flows"
    assert data["packetbeat.protocols"][0]["type"] == "http"
    assert data["packetbeat.protocols"][0]["ports"] == [80, 8080, 8000, 5000, 8002]
    assert data["packetbeat.protocols"][0]["fields"]["collect_type"] == "http"
    assert "packetbeat.interfaces.device" not in data
    assert "packetbeat.protocols:" not in rendered


def test_flows_template_can_disable_http():
    data = load_packetbeat_child_fragment(render_flows_child(enable_http=False))

    assert "packetbeat.flows" in data
    assert data["packetbeat.protocols"] is None


def test_flows_template_can_disable_tcp_udp():
    data = load_packetbeat_child_fragment(render_flows_child(enable_tcp_udp=False))

    assert "packetbeat.flows" not in data
    assert data["packetbeat.protocols"][0]["type"] == "http"


def test_flows_template_rejects_disabling_everything():
    with pytest.raises(BaseAppException, match="至少开启 HTTP 或 TCP/UDP"):
        Controller.validate_packetbeat_network_switches(
            {
                "collector": "Packetbeat",
                "collect_type": "flows",
                "enable_http": False,
                "enable_tcp_udp": False,
            }
        )


def test_flows_switch_validation_only_applies_to_packetbeat():
    Controller.validate_packetbeat_network_switches(
        {
            "collector": "Otherbeat",
            "collect_type": "flows",
            "enable_http": False,
            "enable_tcp_udp": False,
        }
    )


@pytest.mark.parametrize(
    "ports",
    [
        "80,abc",
        "0,80",
        "65536",
        ["80", "abc"],
    ],
)
def test_flows_template_rejects_invalid_http_ports(ports):
    with pytest.raises(BaseAppException, match="HTTP 监听端口必须是 1-65535"):
        Controller.validate_packetbeat_http_ports(
            {
                "collector": "Packetbeat",
                "collect_type": "flows",
                "enable_http": True,
                "ports": ports,
            }
        )


def test_flows_template_allows_missing_ports_when_http_disabled():
    Controller.validate_packetbeat_http_ports(
        {
            "collector": "Packetbeat",
            "collect_type": "flows",
            "enable_http": False,
            "ports": "abc",
        }
    )


def test_flows_template_accepts_valid_http_ports():
    Controller.validate_packetbeat_http_ports(
        {
            "collector": "Packetbeat",
            "collect_type": "flows",
            "enable_http": True,
            "ports": "80, 8080,65535",
        }
    )


def test_child_env_global_values_are_available_to_parent_render():
    from apps.node_mgmt.services.sidecar import Sidecar

    child_configs = [
        types.SimpleNamespace(
            env_config={
                "PACKETBEAT_DEVICE": "eth0,eth1",
                "TOKEN__ABC": "child-only",
            }
        )
    ]

    assert Sidecar.collect_child_render_variables(child_configs) == {
        "PACKETBEAT_DEVICE": "eth0,eth1",
    }


def test_flows_child_env_sets_unsuffixed_packetbeat_device():
    child_env = Controller.build_child_env_config(
        {"nats_password": "secret"},
        "config-1",
        {
            "collector": "Packetbeat",
            "collect_type": "flows",
            "device": "eth0,eth1",
        },
    )

    assert child_env["NATS_PASSWORD__CONFIG-1"] == "secret"
    assert child_env["PACKETBEAT_DEVICE_INPUT"] == "eth0,eth1"
    assert child_env["PACKETBEAT_DEVICE"] == "any"


def test_packetbeat_multi_device_normalizes_to_any_on_linux():
    assert Controller.normalize_packetbeat_device("eth0,lo", "linux") == "any"
    assert Controller.normalize_packetbeat_device("eth0", "linux") == "eth0"
    assert Controller.normalize_packetbeat_device("", "linux") == "any"


def test_flows_child_env_preserves_input_device_and_renders_normalized_device():
    child_env = Controller.build_child_env_config(
        {},
        "config-1",
        {
            "collector": "Packetbeat",
            "collect_type": "flows",
            "device": "eth0,lo",
            "operating_system": "linux",
        },
    )

    assert child_env["PACKETBEAT_DEVICE_INPUT"] == "eth0,lo"
    assert child_env["PACKETBEAT_DEVICE"] == "any"


def test_http_packetbeat_collect_type_is_hidden_from_new_entry_list_only():
    from apps.log.views.collect_config import should_hide_collect_type_entry

    assert should_hide_collect_type_entry({"name": "http", "collector": "Packetbeat"}) is True
    assert should_hide_collect_type_entry({"name": "flows", "collector": "Packetbeat"}) is False
    assert should_hide_collect_type_entry({"name": "http", "collector": "Vector"}) is False


@pytest.mark.django_db
def test_collect_type_list_hides_packetbeat_http_but_keeps_model():
    from rest_framework.test import APIRequestFactory, force_authenticate

    from apps.log.views.collect_config import CollectTypeViewSet

    http_type = CollectType.objects.create(
        name="http",
        collector="Packetbeat",
        icon="ll-flows_网络流量",
    )
    flows_type = CollectType.objects.create(
        name="flows",
        collector="Packetbeat",
        icon="ll-flows_网络流量",
    )

    request = APIRequestFactory().get("/log/collect_types/")
    force_authenticate(request, user=types.SimpleNamespace(locale="zh", is_authenticated=True))

    response = CollectTypeViewSet.as_view({"get": "list"})(request)
    data = json.loads(response.content)["data"]

    assert response.status_code == 200
    assert [item["id"] for item in data] == [flows_type.id]
    assert CollectType.objects.filter(id=http_type.id).exists()


@pytest.mark.django_db
def test_update_flows_config_preserves_child_packetbeat_device_env(monkeypatch):
    collect_type = CollectType.objects.create(
        name="flows",
        collector="Packetbeat",
        icon="ll-flows_网络流量",
    )
    instance = CollectInstance.objects.create(
        id="packetbeat-network-1",
        name="packetbeat-network-1",
        collect_type=collect_type,
        node_id="node-1",
    )
    CollectConfig.objects.create(
        id="child-config-1",
        collect_instance=instance,
        file_type="yaml",
        is_child=True,
    )
    updated_child_configs = []

    class StubNodeMgmt:
        def cloudregion_tls_env_by_node_id(self, node_id):
            return {}

        def get_nodes_by_ids(self, node_ids):
            return [{"id": node_ids[0], "operating_system": "linux"}]

        def update_child_config_content(self, config_id, content, env_config):
            updated_child_configs.append(
                {
                    "config_id": config_id,
                    "content": content,
                    "env_config": env_config,
                }
            )

    monkeypatch.setattr("apps.log.services.collect_type.NodeMgmt", StubNodeMgmt)
    monkeypatch.setattr("apps.log.utils.plugin_controller.NodeMgmt", StubNodeMgmt)

    CollectTypeService.update_instance_config_v2(
        child_info={
            "id": "child-config-1",
            "env_config": {"PACKETBEAT_DEVICE": "eth0,eth1"},
            "content": {
                "device": "eth0,eth1",
                "enable_http": True,
                "enable_tcp_udp": True,
                "ports": "80,8080",
                "flows_period": 10,
                "flows_timeout": 30,
            },
        },
        base_info=None,
        instance_id=instance.id,
        collect_type_id=collect_type.id,
    )

    assert updated_child_configs[0]["config_id"] == "child-config-1"
    assert updated_child_configs[0]["env_config"] == {
        "PACKETBEAT_DEVICE": "any",
        "PACKETBEAT_DEVICE_INPUT": "eth0,eth1",
    }


@pytest.mark.django_db
def test_update_flows_config_rejects_invalid_http_ports(monkeypatch):
    collect_type = CollectType.objects.create(
        name="flows",
        collector="Packetbeat",
        icon="ll-flows_网络流量",
    )
    instance = CollectInstance.objects.create(
        id="packetbeat-network-invalid-ports",
        name="packetbeat-network-invalid-ports",
        collect_type=collect_type,
        node_id="node-1",
    )
    CollectConfig.objects.create(
        id="child-config-invalid-ports",
        collect_instance=instance,
        file_type="yaml",
        is_child=True,
    )
    update_child_config_content = types.SimpleNamespace(called=False)

    class StubNodeMgmt:
        def cloudregion_tls_env_by_node_id(self, node_id):
            return {}

        def get_nodes_by_ids(self, node_ids):
            return [{"id": node_ids[0], "operating_system": "linux"}]

        def update_child_config_content(self, config_id, content, env_config):
            update_child_config_content.called = True

    monkeypatch.setattr("apps.log.services.collect_type.NodeMgmt", StubNodeMgmt)
    monkeypatch.setattr("apps.log.utils.plugin_controller.NodeMgmt", StubNodeMgmt)

    with pytest.raises(BaseAppException, match="HTTP 监听端口必须是 1-65535"):
        CollectTypeService.update_instance_config_v2(
            child_info={
                "id": "child-config-invalid-ports",
                "env_config": {"PACKETBEAT_DEVICE": "any"},
                "content": {
                    "device": "any",
                    "enable_http": True,
                    "enable_tcp_udp": True,
                    "ports": "80,abc",
                    "flows_period": 10,
                    "flows_timeout": 30,
                },
            },
            base_info=None,
            instance_id=instance.id,
            collect_type_id=collect_type.id,
        )

    assert update_child_config_content.called is False
