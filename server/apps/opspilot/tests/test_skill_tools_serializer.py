"""SkillToolsSerializer 的展示名(display_name)/描述翻译逻辑单元测试。

内置工具的 ``name`` 字段被当作 ID 使用（如 ``current_time``、``mysql``），
``display_name`` 需要按当前语言从 language yaml(``tools.{name}.name``)动态翻译，
未配置翻译时回退到 ``name``。这里通过 mock LanguageLoader 校验翻译与回退逻辑，
不依赖数据库。
"""

from apps.opspilot.serializers.llm_serializer import SkillToolsSerializer


def _make_serializer():
    # 绕过 DRF Serializer.__init__，仅用于调用 SerializerMethodField 的实现方法
    return SkillToolsSerializer.__new__(SkillToolsSerializer)


def _make_instance(name):
    class _Inst:
        pass

    inst = _Inst()
    inst.name = name
    inst.description = f"{name} description"
    inst.tools = []
    return inst


def test_get_display_name_uses_translation(mocker):
    serializer = _make_serializer()
    loader = mocker.Mock()
    loader.get.return_value = "当前时间"
    mocker.patch.object(SkillToolsSerializer, "_get_language_loader", return_value=loader)

    inst = _make_instance("current_time")

    assert serializer.get_display_name(inst) == "当前时间"
    loader.get.assert_called_once_with("tools.current_time.name")


def test_get_display_name_falls_back_to_name_when_untranslated(mocker):
    serializer = _make_serializer()
    loader = mocker.Mock()
    loader.get.return_value = None
    mocker.patch.object(SkillToolsSerializer, "_get_language_loader", return_value=loader)

    # 自定义 MCP 工具通常没有翻译映射，应回退到原始 name
    inst = _make_instance("my_custom_mcp_tool")

    assert serializer.get_display_name(inst) == "my_custom_mcp_tool"


def test_get_description_tr_uses_translation_then_falls_back(mocker):
    serializer = _make_serializer()
    loader = mocker.Mock()
    mocker.patch.object(SkillToolsSerializer, "_get_language_loader", return_value=loader)

    inst = _make_instance("current_time")

    loader.get.return_value = "翻译后的描述"
    assert serializer.get_description_tr(inst) == "翻译后的描述"

    loader.get.return_value = None
    assert serializer.get_description_tr(inst) == "current_time description"
