"""运营分析数据权限页签：英文 locale 下把 NATS 中文 display_name 译成英文。"""

import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.nats.nats import get_operation_analysis_module_list
from apps.system_mgmt.viewset.group_data_rule_viewset import GroupDataRuleViewSet

pytestmark = pytest.mark.unit


def test_get_app_module_translates_ops_analysis_tabs_for_english_locale():
    request = APIRequestFactory().get(
        "/api/v1/system_mgmt/group_data_rule/get_app_module/",
        {"app": "ops-analysis"},
    )
    force_authenticate(request, user=type("User", (), {"locale": "en", "is_superuser": True, "is_authenticated": True})())
    view = GroupDataRuleViewSet.as_view({"get": "get_app_module"})

    fake_client = type("C", (), {"get_module_list": staticmethod(get_operation_analysis_module_list)})()
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
    assert get_operation_analysis_module_list()[1]["display_name"] == "数据源"
