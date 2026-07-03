"""monitor.services.custom_snmp_plugin.CustomSnmpPluginService 规格测试。

聚焦不触 DB 的纯逻辑：采集片段标记注入/提取/替换、agent 解析、duration 归一化、
子配置渲染上下文拼装、传播回滚、update_collect_template 入参校验分支。
SNMP 采集片段编辑直接影响下发配置，校验必须严格。
"""

import pydantic.root_model  # noqa

from types import SimpleNamespace
from unittest import mock

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.services.custom_snmp_plugin import (
    DEFAULT_CUSTOM_SNMP_COLLECT_SNIPPET,
    SNMP_COLLECT_MARKER_END,
    SNMP_COLLECT_MARKER_START,
    CustomSnmpPluginService,
)

pytestmark = pytest.mark.unit


_FIELD_SECTION = (
    "[[inputs.snmp]]\n"
    '  agents = ["udp://127.0.0.1:161"]\n'
    "\n"
    "[[inputs.snmp.field]]\n"
    '  oid = ".1.3.6.1.2.1.1.3.0"\n'
    '  name = "uptime"\n'
)


class TestMarkerInjection:
    def test_注入采集标记包裹片段(self):
        result = CustomSnmpPluginService._inject_collect_markers(_FIELD_SECTION)
        assert SNMP_COLLECT_MARKER_START in result
        assert SNMP_COLLECT_MARKER_END in result
        # 标记包裹的是 snmp.field 起始处的片段
        assert "[[inputs.snmp.field]]" in result
        # 主配置 inputs.snmp 仍在标记之前
        assert result.index("[[inputs.snmp]]") < result.index(SNMP_COLLECT_MARKER_START)

    def test_已有标记则原样返回(self):
        content = f"head\n{SNMP_COLLECT_MARKER_START}\nbody\n{SNMP_COLLECT_MARKER_END}\n"
        assert CustomSnmpPluginService._inject_collect_markers(content) == content

    def test_缺少可编辑片段抛异常(self):
        with pytest.raises(BaseAppException):
            CustomSnmpPluginService._inject_collect_markers("[[inputs.cpu]]\n")


class TestExtractAndReplace:
    def test_提取采集片段(self):
        content = f"head\n{SNMP_COLLECT_MARKER_START}\nsnippet line\n{SNMP_COLLECT_MARKER_END}\ntail\n"
        assert CustomSnmpPluginService._extract_collect_snippet(content) == "snippet line"

    def test_提取缺标记抛异常(self):
        with pytest.raises(BaseAppException):
            CustomSnmpPluginService._extract_collect_snippet("no markers here")

    def test_替换采集片段保留头尾(self):
        content = f"head\n{SNMP_COLLECT_MARKER_START}\nold\n{SNMP_COLLECT_MARKER_END}\ntail\n"
        result = CustomSnmpPluginService._replace_collect_snippet(content, "new body")
        assert "new body" in result
        assert "old" not in result
        assert "head" in result and "tail" in result
        # 标记仍然存在
        assert SNMP_COLLECT_MARKER_START in result and SNMP_COLLECT_MARKER_END in result

    def test_替换缺标记抛异常(self):
        with pytest.raises(BaseAppException):
            CustomSnmpPluginService._replace_collect_snippet("no markers", "x")

    def test_注入后可提取出默认片段(self):
        injected = CustomSnmpPluginService._inject_collect_markers(_FIELD_SECTION)
        replaced = CustomSnmpPluginService._replace_collect_snippet(injected, DEFAULT_CUSTOM_SNMP_COLLECT_SNIPPET)
        extracted = CustomSnmpPluginService._extract_collect_snippet(replaced)
        assert extracted == DEFAULT_CUSTOM_SNMP_COLLECT_SNIPPET.strip("\n")


class TestParseIpPort:
    def test_正常解析(self):
        ip, port = CustomSnmpPluginService._parse_ip_port("udp://10.0.0.5:1610")
        assert ip == "10.0.0.5"
        assert port == 1610

    def test_空agent抛异常(self):
        with pytest.raises(BaseAppException):
            CustomSnmpPluginService._parse_ip_port("")

    def test_缺端口抛异常(self):
        with pytest.raises(BaseAppException):
            CustomSnmpPluginService._parse_ip_port("udp://10.0.0.5")


class TestNormalizeDuration:
    def test_去掉秒后缀(self):
        assert CustomSnmpPluginService._normalize_duration("10s") == "10"

    def test_非字符串原样返回(self):
        assert CustomSnmpPluginService._normalize_duration(10) == 10

    def test_无秒后缀原样返回(self):
        assert CustomSnmpPluginService._normalize_duration("10m") == "10m"


class TestBuildChildRenderContext:
    def test_从子配置内容构造渲染上下文(self):
        # toml_to_dict 期望 [[section.sub]] 数组表，取 config=value[0]
        toml = (
            "[[inputs.snmp]]\n"
            'agents = ["udp://192.168.1.10:161"]\n'
            'interval = "30s"\n'
            'timeout = "5s"\n'
            "[inputs.snmp.tags]\n"
            'instance_id = "inst-x"\n'
            'instance_type = "switch"\n'
        )
        config_obj = SimpleNamespace(config_type="snmp_field", id="abc123")
        child_config = {"content": toml}

        ctx = CustomSnmpPluginService._build_child_render_context(config_obj, child_config, "tmpl-9")

        assert ctx["ip"] == "192.168.1.10"
        assert ctx["port"] == 161
        assert ctx["instance_id"] == "inst-x"
        assert ctx["instance_type"] == "switch"
        assert ctx["interval"] == "30"  # 去秒后缀
        assert ctx["timeout"] == "5"
        assert ctx["type"] == "snmp_field"
        assert ctx["config_id"] == "ABC123"  # id.upper()
        assert ctx["plugin_id"] == "tmpl-9"
        assert ctx["monitor_plugin_id"] == "tmpl-9"


class TestRollbackPropagation:
    def test_逆序回滚并收集失败(self):
        calls = []

        def fake_update(cid, content):
            calls.append((cid, content))
            if cid == "b":
                raise RuntimeError("rollback fail")

        node_mgmt = SimpleNamespace(update_child_config_content=fake_update)
        applied = [
            {"id": "a", "original_content": "ca"},
            {"id": "b", "original_content": "cb"},
        ]
        failures = CustomSnmpPluginService._rollback_propagation(node_mgmt, applied)

        # 逆序：先 b 后 a
        assert calls[0][0] == "b"
        assert calls[1][0] == "a"
        assert failures == ["b"]


class TestPropagateCollectTemplate:
    def test_空计划直接返回(self):
        # 不应实例化 NodeMgmt
        assert CustomSnmpPluginService.propagate_collect_template([]) is None

    def test_下发失败触发回滚并抛异常(self):
        calls = []

        class FakeNodeMgmt:
            def update_child_config_content(self, cid, content):
                calls.append((cid, content))
                if content == "boom":
                    raise RuntimeError("apply fail")

        with mock.patch("apps.monitor.services.custom_snmp_plugin.NodeMgmt", FakeNodeMgmt):
            plan = [
                {"id": "x", "rendered_content": "ok", "original_content": "orig-x"},
                {"id": "y", "rendered_content": "boom", "original_content": "orig-y"},
            ]
            with pytest.raises(BaseAppException) as exc:
                CustomSnmpPluginService.propagate_collect_template(plan)
            assert "采集模板同步失败" in str(exc.value)
        # x 先以 rendered 应用成功；y 应用失败触发回滚，x 以 original 回滚
        assert ("x", "ok") in calls
        assert ("y", "boom") in calls
        assert ("x", "orig-x") in calls


class TestUpdateCollectTemplateValidation:
    def _plugin(self):
        return SimpleNamespace(id=1, template_id="t1")

    def test_空片段抛异常(self):
        with pytest.raises(BaseAppException) as exc:
            CustomSnmpPluginService.update_collect_template(self._plugin(), "   ")
        assert "采集片段不能为空" in str(exc.value)

    def test_包含主配置节抛异常(self):
        with pytest.raises(BaseAppException) as exc:
            CustomSnmpPluginService.update_collect_template(self._plugin(), "[[inputs.snmp]]\n oid='x'")
        assert "主配置" in str(exc.value)

    def test_包含模板语法抛异常(self):
        with pytest.raises(BaseAppException) as exc:
            CustomSnmpPluginService.update_collect_template(self._plugin(), "[[inputs.snmp.field]]\n name = {{ x }}")
        assert "模板语法" in str(exc.value)
