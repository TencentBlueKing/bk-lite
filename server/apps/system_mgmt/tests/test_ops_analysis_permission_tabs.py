"""运营分析数据权限页签：英文 locale 下把 NATS 中文 display_name 译成英文。"""

import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.constants.constants import PERMISSION_DATASOURCE, PERMISSION_DIRECTORY
from apps.system_mgmt.viewset.group_data_rule_viewset import GroupDataRuleViewSet

pytestmark = pytest.mark.unit


def _operation_analysis_module_list():
    """与 nats.get_operation_analysis_module_list 同结构的静态目录。

    故意不经 nats/services/models 导入链：本地 INSTALL_APPS 未含 operation_analysis
    时，pre-commit 的 ops-analysis-i18n 钩子仍应能跑通本用例。
    """
    return [
        {
            "name": PERMISSION_DIRECTORY,
            "display_name": "目录",
            "children": [
                {"name": "dashboard", "display_name": "仪表盘"},
                {"name": "topology", "display_name": "拓扑图"},
                {"name": "architecture", "display_name": "架构图"},
            ],
        },
        {"name": PERMISSION_DATASOURCE, "display_name": "数据源", "children": []},
    ]


def test_get_app_module_translates_ops_analysis_tabs_for_english_locale():
    request = APIRequestFactory().get(
        "/api/v1/system_mgmt/group_data_rule/get_app_module/",
        {"app": "ops-analysis"},
    )
    force_authenticate(request, user=type("User", (), {"locale": "en", "is_superuser": True, "is_authenticated": True})())
    view = GroupDataRuleViewSet.as_view({"get": "get_app_module"})

    fake_client = type("C", (), {"get_module_list": staticmethod(_operation_analysis_module_list)})()
    with patch.object(GroupDataRuleViewSet, "get_client", return_value=fake_client):
        response = view(request)

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["result"] is True
    by_name = {item["name"]: item for item in payload["data"]}
    assert by_name["directory"]["display_name"] == "Directory"
    assert {child["name"]: child["display_name"] for child in by_name["directory"]["children"]} == {
        "dashboard": "Dashboard",
        "topology": "Topology",
        "architecture": "Architecture",
    }
    assert by_name["datasource"]["display_name"] == "Data source"
    assert _operation_analysis_module_list()[1]["display_name"] == "数据源"
