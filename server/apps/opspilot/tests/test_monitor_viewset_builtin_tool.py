from types import SimpleNamespace

from rest_framework.response import Response


def test_skill_tools_list_includes_builtin_monitor_tool(mocker):
    from apps.opspilot.viewsets.llm_view import SkillToolsViewSet

    viewset = SkillToolsViewSet()
    request = SimpleNamespace(user=SimpleNamespace(locale="en"))

    mocker.patch(
        "apps.core.utils.viewset_utils.AuthViewSet.list",
        return_value=Response([{"name": "custom-tool"}]),
    )

    response = SkillToolsViewSet.list.__wrapped__(viewset, request)

    assert response.status_code == 200
    assert any(item["name"] == "monitor" for item in response.data)
