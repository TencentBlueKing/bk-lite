"""plugin_controller 工具规格测试。

聚焦 TOML 转义/内联表、模板上下文归一化、Jinja 模板渲染、模板按采集器分组。
"""

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models.plugin import MonitorPlugin, MonitorPluginConfigTemplate
from apps.monitor.utils import plugin_controller as pc
from apps.monitor.utils.plugin_controller import Controller


class TestEscapeTomlString:
    def test_escapes_specials(self):
        assert pc._escape_toml_string('a"b\\c\nd') == 'a\\"b\\\\c\\nd'

    def test_non_string_coerced(self):
        assert pc._escape_toml_string(123) == "123"


class TestToTomlDict:
    def test_empty(self):
        assert pc.to_toml_dict({}) == "{}"

    def test_inline_table(self):
        assert pc.to_toml_dict({"a": "1", "b": "2"}) == '{ "a" = "1", "b" = "2" }'

    def test_escapes_values(self):
        assert pc.to_toml_dict({"k": 'v"x'}) == '{ "k" = "v\\"x" }'


class TestEscapeTomlContextStrings:
    def test_nested(self):
        out = pc._escape_toml_context_strings({"a": 'x"y', "b": ['z"', 1], "c": {"d": 'q"'}})
        assert out["a"] == 'x\\"y'
        assert out["b"][0] == 'z\\"'
        assert out["b"][1] == 1
        assert out["c"]["d"] == 'q\\"'


class TestNormalizeTemplateContext:
    def test_joins_metrics_modules_list(self):
        out = pc._normalize_template_context({"metrics_modules": [" a ", "b", ""]})
        assert out["metrics_modules"] == "a,b"

    def test_bool_winrm_to_string(self):
        assert pc._normalize_template_context({"winrm_cert_validation": True})["winrm_cert_validation"] == "true"
        assert pc._normalize_template_context({"winrm_cert_validation": False})["winrm_cert_validation"] == "false"


class TestRenderTemplate:
    def test_renders_with_logical_instance_value(self):
        ctrl = Controller({})
        out = ctrl.render_template("host={{ instance_id }}", {"logical_instance_value": "h1"})
        assert out == "host=h1"

    def test_parses_tuple_instance_id(self):
        ctrl = Controller({})
        out = ctrl.render_template("host={{ instance_id }}", {"instance_id": "('h1', 'eth0')"})
        assert out == "host=h1"

    def test_unauthorized_variable_raises(self):
        ctrl = Controller({})
        with pytest.raises(BaseAppException):
            ctrl.render_template("x={{ evil_var }}", {"instance_id": "('h1',)"})

    def test_allowed_variable_renders(self):
        ctrl = Controller({})
        out = ctrl.render_template("port={{ port }}", {"port": "161", "instance_id": "('h1',)"})
        assert out == "port=161"

    def test_send_variable_renders(self):
        """回归:net_response.child.toml.j2 引用 {{ send }} 必须能渲染。

        Bug: send 不在 _MONITOR_TEMPLATE_ALLOWED_VARIABLES 白名单里,
        validate_template_variables 直接抛 TemplateSecurityError,
        上层包成 BaseAppException('采集模板包含未授权变量: ...')。
        fix: 把 send 加进白名单。本测试断言:加完后不抛错且能渲染出非空字符串。
        注意 context 里故意不放 'send' —— 这才能复现客户现场路径:
        validate_template_variables 只看 safe_context.keys() | 白名单,
        把 send 同时放 context 会让测试哪怕在没有白名单时也通过(误判)。
        """
        ctrl = Controller({})
        out = ctrl.render_template(
            'send = "{{ send }}"',
            {"instance_id": "('h',)"},
        )
        assert isinstance(out, str)
        assert out.startswith("send = ")
        assert "BaseAppException" not in type(out).__name__  # 纯保险,不抛错覆盖在调用本身

    def test_expect_variable_renders(self):
        """回归:net_response.child.toml.j2 引用 {{ expect }} 必须能渲染。

        与 test_send_variable_renders 对称,见其 docstring。
        """
        ctrl = Controller({})
        out = ctrl.render_template(
            'expect = "{{ expect }}"',
            {"instance_id": "('h',)"},
        )
        assert isinstance(out, str)
        assert out.startswith("expect = ")


@pytest.mark.django_db
class TestGetTemplatesByCollector:
    def test_groups_by_type(self):
        plugin = MonitorPlugin.objects.create(
            name="PCPlugin", collector="Telegraf", collect_type="snmp", template_type="builtin",
        )
        MonitorPluginConfigTemplate.objects.create(
            plugin=plugin, type="base", config_type="base", file_type="toml", content="a",
        )
        MonitorPluginConfigTemplate.objects.create(
            plugin=plugin, type="child", config_type="child", file_type="toml", content="b",
        )
        ctrl = Controller({"monitor_plugin_id": plugin.id})
        out = ctrl.get_templates_by_collector("Telegraf", "snmp")
        assert set(out.keys()) == {"base", "child"}
        assert out["base"][0]["content"] == "a"

    def test_filters_by_collector_when_no_plugin_id(self):
        plugin = MonitorPlugin.objects.create(
            name="PCPlugin2", collector="Exporter", collect_type="http", template_type="builtin",
        )
        MonitorPluginConfigTemplate.objects.create(
            plugin=plugin, type="base", config_type="base", file_type="yaml", content="c",
        )
        ctrl = Controller({})
        out = ctrl.get_templates_by_collector("Exporter", "http")
        assert "base" in out
