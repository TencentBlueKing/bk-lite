"""opspilot.metis.llm.tools.tools_loader.ToolsLoader 测试。

规格（按需加载 langchain 工具）：
- load_tools：解析 'langchain:<name>' URL，加载对应类别工具；非法 URL/未知类别→[]
- _resolve_tool_module：模块对象直接返回；字符串导入；导入失败→None（不抛）
- _process_tool：deepcopy 工具；enable_extra_prompt 时追加额外描述
- _apply_extra_prompts：追加 extra_tools_prompt / 动态参数提示模板
- _discover_specific_tool：未知类别→[]
真实模块导入会拉起一堆 langchain 依赖，故用轻量假模块/假工具构造，避免外部边界。
"""

import types

import pytest

from apps.opspilot.metis.llm.tools.tools_loader import ToolsLoader

pytestmark = pytest.mark.unit


class _FakeStructuredTool:
    """轻量替身：用 isinstance(obj, StructuredTool) 识别工具，这里直接 patch 该类型。"""

    def __init__(self, name, description=""):
        self.name = name
        self.description = description
        self.args_schema = None

    def __deepcopy__(self, memo):
        clone = _FakeStructuredTool(self.name, self.description)
        return clone


@pytest.fixture
def patch_structured_tool(mocker):
    # 让 _extract_tools_from_module 把 _FakeStructuredTool 当作工具识别
    mocker.patch(
        "apps.opspilot.metis.llm.tools.tools_loader.StructuredTool",
        _FakeStructuredTool,
    )


def _make_module(name, **members):
    mod = types.ModuleType(name)
    for k, v in members.items():
        setattr(mod, k, v)
    return mod


class TestResolveToolModule:
    def test_传入模块对象直接返回(self):
        mod = _make_module("apps.opspilot.metis.llm.tools.fake")
        assert ToolsLoader._resolve_tool_module("fake", mod) is mod

    def test_非字符串非模块返回_none(self):
        assert ToolsLoader._resolve_tool_module("bad", 12345) is None

    def test_导入失败返回_none不抛(self):
        # 不存在的模块路径，ModuleNotFoundError 被吞为 None
        assert ToolsLoader._resolve_tool_module("ghost", "no.such.module.path.xyz") is None


class TestExtractTools:
    def test_仅提取_structuredtool_成员(self, patch_structured_tool):
        t1 = _FakeStructuredTool("tool_a")
        t2 = _FakeStructuredTool("tool_b")
        mod = _make_module("m", tool_a=t1, tool_b=t2, NOT_A_TOOL="x", CONST=1)

        extracted = ToolsLoader._extract_tools_from_module(mod, enable_extra_prompt=True)
        names = {info["func"].name for info in extracted}
        assert names == {"tool_a", "tool_b"}
        assert all(info["enable_extra_prompt"] is True for info in extracted)

    def test_无工具返回空列表(self, patch_structured_tool):
        mod = _make_module("m", x=1, y="str")
        assert ToolsLoader._extract_tools_from_module(mod, False) == []


class TestApplyExtraPrompts:
    def test_追加_extra_tools_prompt(self):
        func = _FakeStructuredTool("t", description="base")
        ToolsLoader._apply_extra_prompts(func, "EXTRA", {})
        assert func.description == "base\nEXTRA"

    def test_无额外提示不改描述(self):
        func = _FakeStructuredTool("t", description="base")
        ToolsLoader._apply_extra_prompts(func, "", {})
        assert func.description == "base"

    def test_动态参数提示走模板渲染(self, mocker):
        rendered = mocker.patch(
            "apps.opspilot.metis.llm.tools.tools_loader.TemplateLoader.render_template",
            return_value="RENDERED",
        )
        func = _FakeStructuredTool("t", description="base")
        ToolsLoader._apply_extra_prompts(func, "", {"db": "mysql instance"})

        assert func.description == "base\nRENDERED"
        # 模板路径与拼接后的参数描述被正确传入
        args, kwargs = rendered.call_args
        assert args[0] == "prompts/tools/dynamic_param_generation"
        assert "db:mysql instance" in args[1]["param_descriptions"]


class TestProcessTool:
    def test_deepcopy_隔离原工具(self):
        original = _FakeStructuredTool("t", description="base")
        tool_info = {"func": original, "enable_extra_prompt": True}
        processed = ToolsLoader._process_tool(tool_info, "EXTRA", {})

        assert processed is not original
        assert processed.description == "base\nEXTRA"
        # 原工具不受影响
        assert original.description == "base"

    def test_enable_extra_prompt_false_不追加(self):
        original = _FakeStructuredTool("t", description="base")
        tool_info = {"func": original, "enable_extra_prompt": False}
        processed = ToolsLoader._process_tool(tool_info, "EXTRA", {})
        assert processed.description == "base"

    def test_处理异常返回_none(self, mocker):
        # deepcopy 抛异常时被捕获，返回 None（不影响其他工具）
        mocker.patch("apps.opspilot.metis.llm.tools.tools_loader.copy.deepcopy", side_effect=ValueError("x"))
        assert ToolsLoader._process_tool({"func": object(), "enable_extra_prompt": False}, "", {}) is None


class TestDiscoverSpecificTool:
    def test_未知类别返回空(self):
        assert ToolsLoader._discover_specific_tool("does_not_exist") == []

    def test_已知类别但模块解析失败返回空(self, mocker):
        mocker.patch.object(ToolsLoader, "_resolve_tool_module", return_value=None)
        assert ToolsLoader._discover_specific_tool("kubernetes") == []


class TestLoadTools:
    def test_非法_url_格式返回空(self):
        assert ToolsLoader.load_tools("badurl") == []

    def test_未知工具类别返回空(self):
        assert ToolsLoader.load_tools("langchain:totally_unknown_tool") == []

    def test_正常加载并处理工具(self, mocker, patch_structured_tool):
        t = _FakeStructuredTool("k_tool", description="d")
        mocker.patch.object(
            ToolsLoader,
            "_discover_specific_tool",
            return_value=[{"func": t, "enable_extra_prompt": True}],
        )
        tools = ToolsLoader.load_tools("langchain:kubernetes", extra_tools_prompt="EXTRA")
        assert len(tools) == 1
        assert tools[0].description == "d\nEXTRA"

    def test_发现为空时返回空列表(self, mocker):
        mocker.patch.object(ToolsLoader, "_discover_specific_tool", return_value=[])
        assert ToolsLoader.load_tools("langchain:kubernetes") == []


class TestToolModulesRegistry:
    def test_注册表包含核心数据库与_k8s_类别(self):
        for cat in ["kubernetes", "mysql", "redis", "postgres", "ssh"]:
            assert cat in ToolsLoader.TOOL_MODULES
            path, enable = ToolsLoader.TOOL_MODULES[cat]
            assert isinstance(path, str)
            assert isinstance(enable, bool)

    def test_monitor_刻意不在静态注册表(self):
        assert "monitor" not in ToolsLoader.TOOL_MODULES
