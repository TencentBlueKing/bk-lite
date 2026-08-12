"""自定义 SNMP 模板创建接口规格测试。"""

import pytest

from apps.monitor.models import MonitorPlugin, MonitorPluginConfigTemplate, MonitorPluginUITemplate
from apps.monitor.models.monitor_object import MonitorObject

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

BASE = "/api/v1/monitor/api/monitor_plugin"


def _response_data(response):
    body = response.json()
    return body.get("data", body)


def test_没有内置_snmp插件的监控对象也能创建可配置模板(api_client, authenticated_user):
    authenticated_user.permission = {"monitor": {"integration_configure-Add"}}
    monitor_object = MonitorObject.objects.create(
        name="CustomSnmpWithoutBuiltin",
        display_name="无内置 SNMP 对象",
        level="base",
        instance_id_keys=["instance_id"],
    )

    response = api_client.post(
        f"{BASE}/",
        {
            "name": "custom-snmp-without-builtin",
            "display_name": "通用 SNMP 模板",
            "template_id": "custom-snmp-without-builtin",
            "template_type": "snmp",
            "monitor_object": [monitor_object.id],
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    created_plugin = _response_data(response)
    plugin_id = created_plugin["id"]
    assert created_plugin["status_query"] == "any({plugin_id='custom-snmp-without-builtin'}) by (instance_id)"

    collect_response = api_client.get(f"{BASE}/{plugin_id}/collect_template/")
    assert collect_response.status_code == 200
    collect_template = _response_data(collect_response)
    assert collect_template["content"].startswith("# [[inputs.snmp.field]]")

    ui_response = api_client.get(f"{BASE}/{plugin_id}/ui_template/")
    assert ui_response.status_code == 200
    ui_template = _response_data(ui_response)["ui_template"]
    assert ui_template["object_name"] == "CustomSnmpWithoutBuiltin"
    assert ui_template["instance_type"] == "CustomSnmpWithoutBuiltin"
    assert ui_template["config_type"] == ["custom_snmp"]
    assert {field["name"] for field in ui_template["form_fields"]} >= {
        "version",
        "community",
        "sec_name",
        "interval",
        "timeout",
    }
    assert {column["name"] for column in ui_template["table_columns"]} == {
        "node_ids",
        "ip",
        "instance_name",
        "group_ids",
    }

    update_response = api_client.put(
        f"{BASE}/{plugin_id}/collect_template/",
        {"content": ("[[inputs.snmp.field]]\n" '  oid = ".1.3.6.1.2.1.1.3.0"\n' '  name = "snmp_uptime"')},
        format="json",
    )
    assert update_response.status_code == 200, update_response.content
    assert 'name = "snmp_uptime"' in _response_data(update_response)["content"]


def test_内置_snmp插件来源不唯一时回退通用模板(api_client, authenticated_user):
    authenticated_user.permission = {"monitor": {"integration_configure-Add"}}
    monitor_object = MonitorObject.objects.create(
        name="CustomSnmpAmbiguousBuiltin",
        level="base",
        instance_id_keys=["instance_id"],
    )
    for index in range(2):
        builtin = MonitorPlugin.objects.create(
            name=f"ambiguous-builtin-{index}",
            collector="Telegraf",
            collect_type="snmp",
            template_type="builtin",
        )
        builtin.monitor_object.add(monitor_object)

    response = api_client.post(
        f"{BASE}/",
        {
            "name": "custom-snmp-ambiguous-builtin",
            "display_name": "歧义来源回退模板",
            "template_id": "custom-snmp-ambiguous-builtin",
            "template_type": "snmp",
            "monitor_object": [monitor_object.id],
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    plugin_id = _response_data(response)["id"]
    ui_response = api_client.get(f"{BASE}/{plugin_id}/ui_template/")
    assert ui_response.status_code == 200
    assert _response_data(ui_response)["ui_template"]["config_type"] == ["custom_snmp"]


def test_内置_snmp插件缺少可复用配置时回退通用模板(api_client, authenticated_user):
    authenticated_user.permission = {"monitor": {"integration_configure-Add"}}
    monitor_object = MonitorObject.objects.create(
        name="CustomSnmpIncompleteBuiltin",
        level="base",
        instance_id_keys=["instance_id"],
    )
    builtin = MonitorPlugin.objects.create(
        name="incomplete-builtin-snmp",
        collector="Telegraf",
        collect_type="snmp",
        template_type="builtin",
    )
    builtin.monitor_object.add(monitor_object)

    response = api_client.post(
        f"{BASE}/",
        {
            "name": "custom-snmp-incomplete-builtin",
            "display_name": "不完整来源回退模板",
            "template_id": "custom-snmp-incomplete-builtin",
            "template_type": "snmp",
            "monitor_object": [monitor_object.id],
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    plugin_id = _response_data(response)["id"]
    collect_response = api_client.get(f"{BASE}/{plugin_id}/collect_template/")
    assert collect_response.status_code == 200
    assert _response_data(collect_response)["type"] == "custom_snmp"


def test_结构完整的唯一内置_snmp插件继续作为初始模板(api_client, authenticated_user):
    authenticated_user.permission = {"monitor": {"integration_configure-Add"}}
    monitor_object = MonitorObject.objects.create(
        name="CustomSnmpReusableBuiltin",
        level="base",
        instance_id_keys=["instance_id"],
    )
    builtin = MonitorPlugin.objects.create(
        name="reusable-builtin-snmp",
        collector="Telegraf",
        collect_type="snmp",
        template_type="builtin",
        status_query="any({collect_type='snmp'}) by (instance_id)",
        node_selector={"is_container": False},
    )
    builtin.monitor_object.add(monitor_object)
    MonitorPluginConfigTemplate.objects.create(
        plugin=builtin,
        type="reusable_snmp",
        config_type="child",
        file_type="toml",
        content=(
            "[[inputs.snmp]]\n"
            '    agents = ["udp://{{ ip }}:{{ port }}"]\n'
            '    interval = "{{ interval }}s"\n'
            '    timeout = "{{ timeout }}s"\n'
            "    version = 2\n"
            '    community = "{{ community }}"\n'
            "    [inputs.snmp.tags]\n"
            '        instance_id = "{{ instance_id }}"\n'
            '        instance_type = "{{ instance_type }}"\n'
            '        collect_type = "snmp"\n'
            '        config_type = "reusable_snmp"\n'
            "    [[inputs.snmp.field]]\n"
            '        oid = ".1.3.6.1.2.1.1.3.0"\n'
            '        name = "source_metric"\n'
        ),
    )
    MonitorPluginUITemplate.objects.create(
        plugin=builtin,
        content={
            "object_name": monitor_object.name,
            "instance_type": "reusable_snmp",
            "collect_type": "snmp",
            "config_type": ["reusable_snmp"],
            "collector": "Telegraf",
            "instance_id": "{{uuid}}",
            "form_fields": [{"name": "source_only_field", "label": "来源字段", "type": "input"}],
            "table_columns": [],
        },
    )

    response = api_client.post(
        f"{BASE}/",
        {
            "name": "custom-snmp-reusable-builtin",
            "display_name": "复用来源模板",
            "template_id": "custom-snmp-reusable-builtin",
            "template_type": "snmp",
            "monitor_object": [monitor_object.id],
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    created_plugin = _response_data(response)
    assert created_plugin["status_query"] == "any({plugin_id='custom-snmp-reusable-builtin'}) by (instance_id)"
    assert created_plugin["node_selector"] == {"is_container": False}
    plugin_id = created_plugin["id"]

    ui_response = api_client.get(f"{BASE}/{plugin_id}/ui_template/")
    assert ui_response.status_code == 200
    ui_template = _response_data(ui_response)["ui_template"]
    assert ui_template["config_type"] == ["reusable_snmp"]
    assert [field["name"] for field in ui_template["form_fields"]] == ["source_only_field"]

    collect_response = api_client.get(f"{BASE}/{plugin_id}/collect_template/")
    assert collect_response.status_code == 200
    assert "source_metric" not in _response_data(collect_response)["content"]
