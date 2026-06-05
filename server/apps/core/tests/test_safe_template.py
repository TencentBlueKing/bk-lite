import pytest

from apps.core.utils.safe_template import (
    TemplateSecurityError,
    build_sandboxed_env,
    check_dangerous_patterns,
    safe_render,
    sanitize_template_context,
    validate_template_variables,
)


class TestCheckDangerousPatterns:
    def test_blocks_dunder_access(self):
        with pytest.raises(TemplateSecurityError):
            check_dangerous_patterns("{{ cycler.__init__.__globals__.os.popen('id').read() }}")

    def test_blocks_cycler(self):
        with pytest.raises(TemplateSecurityError):
            check_dangerous_patterns("{{ cycler }}")

    def test_blocks_popen(self):
        with pytest.raises(TemplateSecurityError):
            check_dangerous_patterns("{{ popen('id') }}")

    def test_blocks_import(self):
        with pytest.raises(TemplateSecurityError):
            check_dangerous_patterns("{{ import os }}")

    def test_allows_plain_text(self):
        check_dangerous_patterns("hello world 123")

    def test_allows_toml_content(self):
        # 纯文本配置片段不应因基础字符被误判
        snippet = '[[inputs.snmp.field]]\n  oid = ".1.3.6.1.2.1.1.3.0"\n  name = "sysUpTime"'
        check_dangerous_patterns(snippet)

    def test_allows_markdown_table_text(self):
        check_dangerous_patterns("| 输入 | 意图 | 理由 |")

    def test_blocks_filter_only_inside_expression(self):
        with pytest.raises(TemplateSecurityError):
            check_dangerous_patterns("{{ name | upper }}")


class TestSafeRender:
    def test_simple_variable(self):
        result = safe_render("Hello {{ name }}", {"name": "world"})
        assert result == "Hello world"

    def test_nested_variable(self):
        result = safe_render("{{ user.name }}", {"user": {"name": "alice"}})
        assert result == "Hello alice" or result == "alice"

    def test_missing_variable_returns_empty(self):
        result = safe_render("Hello {{ missing }}", {})
        assert result == "Hello "

    def test_blocks_ssti_payload(self):
        with pytest.raises(TemplateSecurityError):
            safe_render("{{ cycler.__init__.__globals__.os.popen('id').read() }}", {})

    def test_empty_string(self):
        assert safe_render("", {}) == ""

    def test_none_returns_none(self):
        assert safe_render(None, {}) is None


class TestBuildSandboxedEnv:
    def test_basic_render(self):
        env = build_sandboxed_env()
        tpl = env.from_string("Hello {{ name }}")
        assert tpl.render(name="world") == "Hello world"

    def test_blocks_dunder_access(self):
        env = build_sandboxed_env()
        tpl = env.from_string("{{ cycler.__init__.__globals__ }}")
        from jinja2.sandbox import SecurityError as JinjaSandboxError

        with pytest.raises((JinjaSandboxError, Exception)):
            tpl.render()

    def test_globals_cleared(self):
        env = build_sandboxed_env()
        assert "cycler" not in env.globals
        assert "joiner" not in env.globals
        assert "namespace" not in env.globals
        assert "lipsum" not in env.globals

    def test_filters_cleared_by_default(self):
        env = build_sandboxed_env()
        assert len(env.filters) == 0

    def test_extra_filters_applied(self):
        env = build_sandboxed_env(extra_filters={"upper": str.upper})
        tpl = env.from_string("{{ name | upper }}")
        assert tpl.render(name="hello") == "HELLO"

    def test_default_filter_not_enabled_by_default(self):
        env = build_sandboxed_env()
        with pytest.raises(Exception, match="No filter named 'default'"):
            env.from_string("{{ value | default('fallback', true) }}")

    def test_control_statements_work(self):
        env = build_sandboxed_env()
        tpl = env.from_string("{% for i in items %}{{ i }},{% endfor %}")
        assert tpl.render(items=["a", "b", "c"]) == "a,b,c,"

    def test_cannot_access_os_via_object_chain(self):
        env = build_sandboxed_env()
        # 即使传入对象，沙箱也会阻止访问 __globals__
        tpl = env.from_string("{{ obj.__class__.__mro__ }}")
        from jinja2.sandbox import SecurityError as JinjaSandboxError

        with pytest.raises(JinjaSandboxError):
            tpl.render(obj="test")

    def test_blocks_public_callable_on_context_object(self):
        env = build_sandboxed_env()

        class Obj:
            def dangerous(self):
                return "called"

        tpl = env.from_string("{{ obj.dangerous() }}")
        from jinja2.sandbox import SecurityError as JinjaSandboxError
        with pytest.raises(JinjaSandboxError):
            tpl.render(obj=Obj())

    def test_validate_template_variables_blocks_unapproved_names(self):
        env = build_sandboxed_env()

        with pytest.raises(TemplateSecurityError, match="未授权变量"):
            validate_template_variables("{{ settings.SECRET_KEY }}", env, {"instance_id"})

    def test_sanitize_template_context_converts_objects_to_strings(self):
        class Obj:
            secret = "hidden"

            def __str__(self):
                return "plain"

        context = sanitize_template_context({"obj": Obj(), "items": [Obj()]})

        assert context == {"obj": "plain", "items": ["plain"]}

    def test_real_world_telegraf_template(self):
        env = build_sandboxed_env(extra_filters={"to_toml": lambda d: str(d)})
        template_content = """[[inputs.snmp]]
  agents = ["udp://{{ instance_id }}:{{ port }}"]
  version = {{ version }}
"""
        tpl = env.from_string(template_content)
        result = tpl.render(instance_id="192.168.1.1", port="161", version="2")
        assert "192.168.1.1" in result
        assert "161" in result
