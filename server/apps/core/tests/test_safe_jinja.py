"""Jinja2 SSTI / 模板注入 安全回归测试。

对应 2026-05 安全审计报告中确认的多处「用户可控内容进入默认 Jinja2 渲染」
导致 SSTI/RCE 的漏洞点。这些用例确保：

1. 统一安全渲染入口 :func:`render_secure_template` 会拦截全部已知 PoC，
   不执行系统命令、不泄露 Python 运行时对象。
2. 正常的 ``{{ variable }}`` 变量替换不被误伤。
3. 各业务 sink（ChatFlow 变量管理器、监控插件控制器、SNMP 采集片段校验）
   均不再可被 PoC 触发命令执行。

新增/调整 Jinja2 渲染逻辑时，请保持本文件用例通过。
"""

import pytest
from jinja2.exceptions import SecurityError, TemplateError, UndefinedError

from apps.core.utils.safe_jinja import (
    contains_template_syntax,
    create_secure_jinja_environment,
    render_secure_template,
)

pytestmark = pytest.mark.unit

# 安全审计报告「六、建议回归用例」中列出的全部 PoC payload。
SSTI_POCS = [
    "{{ cycler.__init__.__globals__.os.popen('id').read() }}",
    "{{ joiner.__init__.__globals__.os.popen('id').read() }}",
    "{{ namespace.__init__.__globals__.os.popen('id').read() }}",
    "{{ self.__init__.__globals__ }}",
    "{{ ''.__class__.__mro__ }}",
    "{{ ''.__class__.__mro__[1].__subclasses__() }}",
    "{{ config.__class__.__mro__ }}",
    "{{ request.__class__.__mro__ }}",
    "{{ lipsum.__globals__.os.popen('id').read() }}",
]

# 命令执行 / 对象泄露的特征串，渲染结果中绝不应出现。
LEAK_MARKERS = ("uid=", "gid=", "groups=", "<class", "object at 0x", "__main__")


def _assert_no_leak(rendered: str):
    lowered = rendered.lower()
    for marker in LEAK_MARKERS:
        assert marker.lower() not in lowered, f"渲染结果疑似逃逸/命令执行: {rendered!r}"


class TestRenderSecureTemplate:
    @pytest.mark.parametrize("payload", SSTI_POCS)
    def test_ssti_poc_is_blocked(self, payload):
        """每条 PoC 要么抛出安全异常，要么渲染为无害空串，绝不执行命令。"""
        try:
            rendered = render_secure_template(payload, {})
        except (SecurityError, UndefinedError, TemplateError):
            return  # 被沙箱拦截，符合预期
        # 未抛异常时（如未定义变量被渲染为空），必须确认没有任何逃逸痕迹
        _assert_no_leak(rendered)

    def test_plain_variable_substitution(self):
        out = render_secure_template(
            "instance={{ instance_id }} ip={{ ip }}",
            {"instance_id": "i-001", "ip": "10.0.0.1"},
        )
        assert out == "instance=i-001 ip=10.0.0.1"

    def test_filters_still_available_when_kept(self):
        out = render_secure_template("{{ name | upper }}", {"name": "abc"}, clear_globals=False)
        assert out == "ABC"

    def test_none_returns_none(self):
        assert render_secure_template(None, {}) is None

    def test_strict_undefined_raises(self):
        with pytest.raises(UndefinedError):
            render_secure_template("{{ missing }}", {}, strict_undefined=True)

    def test_attribute_access_blocked(self):
        with pytest.raises(SecurityError):
            render_secure_template("{{ s.__class__ }}", {"s": "x"})


class TestCreateSecureEnvironment:
    def test_globals_cleared_by_default(self):
        env = create_secure_jinja_environment()
        assert "cycler" not in env.globals
        assert "lipsum" not in env.globals

    def test_globals_kept_when_requested(self):
        env = create_secure_jinja_environment(clear_globals=False)
        assert "range" in env.globals


class TestContainsTemplateSyntax:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("plain toml line", False),
            ("no template here", False),
            ("", False),
            (None, False),
            ("# {{ cycler }}", True),
            ("{% for x in y %}", True),
            ("value = {{ ip }}", True),
        ],
    )
    def test_detection(self, text, expected):
        assert contains_template_syntax(text) is expected


class TestVariableManagerSink:
    """ChatFlow 变量管理器：SSTI 不应执行，正常变量正常解析。"""

    def _vm(self):
        from apps.opspilot.utils.chat_flow_utils.engine.core.variable_manager import VariableManager

        return VariableManager()

    @pytest.mark.parametrize("payload", SSTI_POCS)
    def test_resolve_template_blocks_ssti(self, payload):
        vm = self._vm()
        # resolve_template 在渲染失败时返回原始模板字符串（不执行）
        result = vm.resolve_template(payload)
        _assert_no_leak(result)

    def test_resolve_template_normal(self):
        vm = self._vm()
        vm.set_variable("ip", "10.0.0.1")
        assert vm.resolve_template("ip={{ ip }}") == "ip=10.0.0.1"


class TestMonitorPluginControllerSink:
    """监控插件控制器：用户可控采集模板内容中的 SSTI 不应执行。"""

    def _controller(self):
        from apps.monitor.utils.plugin_controller import Controller

        return Controller({})

    @pytest.mark.parametrize("payload", SSTI_POCS)
    def test_render_template_blocks_ssti(self, payload):
        controller = self._controller()
        try:
            rendered = controller.render_template(payload, {})
        except (SecurityError, UndefinedError, TemplateError):
            return
        _assert_no_leak(rendered)

    def test_render_template_normal(self):
        controller = self._controller()
        assert controller.render_template("name={{ svc }}", {"svc": "abc"}) == "name=abc"


class TestSnmpCollectSnippetValidation:
    """SNMP 采集片段保存前的安全护栏：拒绝模板表达式 / 双下划线。

    与 ``CustomSnmpPluginService.update_collect_template`` 中的护栏逻辑保持一致：
    ``contains_template_syntax(snippet) or "__" in snippet`` 命中即拒绝。
    """

    @pytest.mark.parametrize("payload", SSTI_POCS)
    def test_malicious_snippet_is_caught_by_guard(self, payload):
        snippet = f"# {payload}\n[[inputs.snmp.field]]\n  oid = \".1.3.6.1.2.1.1.3.0\""
        assert contains_template_syntax(snippet) or "__" in snippet

    def test_clean_snippet_passes_guard(self):
        snippet = "[[inputs.snmp.field]]\n  oid = \".1.3.6.1.2.1.1.3.0\"\n  name = \"sysUpTime\""
        assert not (contains_template_syntax(snippet) or "__" in snippet)
