"""技能包导入失败文案按 loader 翻译，导入器仍抛中文原句。"""

from types import SimpleNamespace

from apps.opspilot.viewsets.llm_view import SkillPackageViewSet


def test_missing_skill_md_uses_loader_template(mocker):
    view = SkillPackageViewSet()
    view.loader = mocker.Mock()
    view.loader.get.return_value = "The skill package is missing {filename}"

    text = view._skill_package_import_message(SimpleNamespace(), ValueError("技能包缺少 SKILL.md"))

    assert text == "The skill package is missing SKILL.md"
    view.loader.get.assert_called_once_with("error.skill_package_missing_file")


def test_unmapped_import_error_stays_original(mocker):
    view = SkillPackageViewSet()
    view.loader = mocker.Mock()

    text = view._skill_package_import_message(SimpleNamespace(), ValueError("技能包包含非法路径"))

    assert text == "技能包包含非法路径"
    view.loader.get.assert_not_called()
