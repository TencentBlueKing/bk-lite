"""SNMP 插件合同测试：验证实际展开、渲染后的下发配置。"""

import tomllib

from jinja2 import Template

from apps.monitor.management.services.plugin_migrate import _expand_local_template_assets


def render_snmp_config(template, plugin_dir):
    expanded = _expand_local_template_assets(template, plugin_dir)
    rendered = Template(expanded).render(
        version=3,
        config_id="contract",
        ip="192.0.2.1",
        port=161,
        interval=60,
        timeout=5,
        instance_id="contract",
        instance_type="switch",
        community="public",
        sec_name="contract",
        sec_level="authPriv",
        auth_protocol="SHA",
        priv_protocol="AES",
        auth_password="AUTH_SECRET_SENTINEL",
        priv_password="PRIV_SECRET_SENTINEL",
    )
    return rendered, tomllib.loads(rendered)


def assert_snmpv3_env_credentials(template, plugin_dir):
    rendered, config = render_snmp_config(template, plugin_dir)
    snmp = config["inputs"]["snmp"][0]
    assert snmp["version"] == 3
    assert snmp["auth_password"] == "${AUTH_PASSWORD__contract}"
    assert snmp["priv_password"] == "${PRIV_PASSWORD__contract}"
    assert "AUTH_SECRET_SENTINEL" not in rendered
    assert "PRIV_SECRET_SENTINEL" not in rendered


def assert_common_ifmib_counters(template, plugin_dir):
    _, config = render_snmp_config(template, plugin_dir)
    snmp = config["inputs"]["snmp"][0]
    assert any(field["oid"] == "1.3.6.1.2.1.1.3.0" for field in snmp["field"])
    interface = next(table for table in snmp["table"] if table["name"] == "interface")
    fields = {field["name"]: field for field in interface["field"]}
    # 公共 IF-MIB 同时提供 64 位主路径与旧设备 32 位回退，不能只检查品牌源模板。
    for name, oid in {
        "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",
        "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
        "ifInOctets": "1.3.6.1.2.1.2.2.1.10",
        "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
    }.items():
        assert fields[name]["oid"] == oid
    assert fields["ifDescr"]["is_tag"] is True
