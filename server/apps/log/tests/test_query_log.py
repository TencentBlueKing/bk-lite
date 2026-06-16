import asyncio
import json
import threading

import pytest
from django.utils import timezone
from rest_framework import status

from apps.log.models.log_group import LogGroup, LogGroupOrganization, SearchCondition
from apps.log.serializers.policy import AlertSerializer
from apps.log.utils.log_group import LogGroupQueryBuilder
from apps.log.models.policy import Alert, AlertSnapshot, Event, EventRawData, Policy, PolicyOrganization
from apps.log.utils.query_log import VictoriaMetricsAPI


class DummyResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line


def test_query_skips_invalid_json_lines(mocker):
    response = DummyResponse(
        [
            json.dumps({"_msg": "ok-1"}),
            '{"_msg":"bad\nraw-control"}',
            json.dumps({"_msg": "ok-2"}),
        ]
    )
    post_mock = mocker.patch("apps.log.utils.query_log.requests.post", return_value=response)

    api = VictoriaMetricsAPI()

    result = api.query("*", "", "", 10)

    assert result == [{"_msg": "ok-1"}, {"_msg": "ok-2"}]
    post_mock.assert_called_once()


def test_query_ignores_empty_lines(mocker):
    response = DummyResponse(["", json.dumps({"_msg": "ok"}), ""])
    mocker.patch("apps.log.utils.query_log.requests.post", return_value=response)

    api = VictoriaMetricsAPI()

    result = api.query("*", "", "", 10)

    assert result == [{"_msg": "ok"}]


def test_query_logs_malformed_line_context(mocker):
    response = DummyResponse(['{"_msg":"bad\nraw-control"}'])
    mocker.patch("apps.log.utils.query_log.requests.post", return_value=response)
    warning_mock = mocker.patch("apps.log.utils.query_log.logger.warning")

    api = VictoriaMetricsAPI()

    result = api.query("level:error", "start-ts", "end-ts", 5)

    assert result == []
    malformed_call = warning_mock.call_args_list[0]
    assert "VictoriaLogs query 返回非法 JSON 行，已跳过" in malformed_call.args[0]
    assert "error_window_repr=" in malformed_call.args[0]
    assert "query_preview=" not in malformed_call.args[0]
    extra = malformed_call.kwargs["extra"]
    assert extra["line_length"] > 0
    assert extra["error_position"] >= 0
    assert "\\n" in extra["error_window_repr"]


def _mock_group_permission(mocker, teams=None, instance_ids=None, instance_permissions=None):
    if instance_permissions is None:
        instance_permissions = [{"id": group_id, "permission": ["View", "Operate"]} for group_id in (instance_ids or [])]
    mocked_permission = {
        "team": teams or [],
        "instance": instance_permissions,
    }
    mocker.patch(
        "apps.log.services.access_scope.get_permission_rules",
        return_value=mocked_permission,
    )


def _mock_policy_permission(mocker, policy_id=None, organization=1):
    instance_permissions = []
    if policy_id is not None:
        instance_permissions.append({"id": policy_id, "permission": ["View", "Operate"]})

    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={
            "data": {
                "None": {
                    "instance": instance_permissions,
                }
            },
            "team": [organization],
        },
    )


def _mock_policy_permission_result(mocker, permission_data, teams=None):
    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={
            "data": permission_data,
            "team": teams or [],
        },
    )


def _create_policy(name, organization):
    policy = Policy.objects.create(
        name=name,
        alert_type="keyword",
        alert_name=name,
        alert_level="warning",
        alert_condition={"query": "error"},
        schedule={"type": "min", "value": 5},
        period={"type": "min", "value": 5},
    )
    PolicyOrganization.objects.create(policy=policy, organization=organization)
    return policy


def _create_alert_with_event(policy, alert_id, event_id):
    alert = Alert.objects.create(
        id=alert_id,
        policy=policy,
        source_id=f"source-{alert_id}",
        level="warning",
        content="raw log alert",
        start_event_time=timezone.now(),
    )
    event = Event.objects.create(
        id=event_id,
        policy=policy,
        alert=alert,
        source_id=alert.source_id,
        event_time=timezone.now(),
        level="warning",
        content="raw event content",
    )
    return alert, event


@pytest.mark.django_db
def test_alert_serializer_uses_rendered_alert_content_for_alert_name():
    policy = _create_policy("${log.container_name}-关键字分组测试", organization=1)
    alert = Alert.objects.create(
        id="alert-rendered-name",
        policy=policy,
        source_id="source-rendered-name",
        level="warning",
        content="bk-lite-server-关键字分组测试",
        start_event_time=timezone.now(),
    )

    data = AlertSerializer(alert).data

    assert data["alert_name"] == "bk-lite-server-关键字分组测试"


@pytest.mark.django_db
def test_alert_serializer_keeps_untrusted_alert_name_as_plain_string():
    malicious_name = '<img src=x onerror=alert(1)><script>alert("xss")</script>-关键字分组测试'
    policy = _create_policy("${log.container_name}-关键字分组测试", organization=1)
    alert = Alert.objects.create(
        id="alert-rendered-name-xss",
        policy=policy,
        source_id="source-rendered-name-xss",
        level="warning",
        content=malicious_name,
        start_event_time=timezone.now(),
    )

    data = AlertSerializer(alert).data

    assert data["alert_name"] == malicious_name


@pytest.mark.django_db
def test_search_endpoint_requires_log_groups(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Group 1", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/search/search/",
        data={"query": "level:error", "start_time": "", "end_time": "", "limit": 5},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["message"] == "log_groups:缺少日志分组"


@pytest.mark.django_db
def test_search_endpoint_rejects_unauthorized_log_group(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-2", name="Group 2", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-2", organization=2)
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/search/search/",
        data={"query": "*", "log_groups": ["g-2"]},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["result"] is False


@pytest.mark.django_db
def test_field_values_endpoint_requires_log_groups(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Group 1", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.get(
        "/api/v1/log/search/field_values/?filed=host&query=level:error",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["message"] == "缺少日志分组"


@pytest.mark.django_db
def test_hits_endpoint_requires_log_groups(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Group 1", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/search/hits/",
        data={"query": "*", "field": "_stream", "fields_limit": 5, "step": "5m"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["message"] == "log_groups:缺少日志分组"


@pytest.mark.django_db
def test_top_stats_endpoint_requires_log_groups(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Group 1", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/search/top_stats/",
        data={"query": "*", "attr": "_stream", "top_num": 5},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["message"] == "log_groups:缺少日志分组"


@pytest.mark.django_db
def test_tail_endpoint_requires_log_groups(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Group 1", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/search/tail/?query=*")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["message"] == "缺少日志分组"


@pytest.mark.django_db
def test_log_group_update_is_scoped_by_permission(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Allowed", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroup.objects.create(id="g-2", name="Denied", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    LogGroupOrganization.objects.create(log_group_id="g-2", organization=2)
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.patch(
        "/api/v1/log/log_group/g-2/",
        data={"name": "changed"},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_log_group_update_rejects_view_only_instance_permission(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Allowed", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=2)
    _mock_group_permission(
        mocker,
        teams=[],
        instance_permissions=[{"id": "g-1", "permission": ["View"]}],
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.patch(
        "/api/v1/log/log_group/g-1/",
        data={"name": "changed"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_log_group_destroy_rejects_view_only_instance_permission(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Allowed", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=2)
    _mock_group_permission(
        mocker,
        teams=[],
        instance_permissions=[{"id": "g-1", "permission": ["View"]}],
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.delete("/api/v1/log/log_group/g-1/")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_log_group_create_rejects_unauthorized_organizations(api_client, authenticated_user, mocker):
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/log_group/",
        data={
            "id": "g-new",
            "name": "New Group",
            "rule": {"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]},
            "organizations": [2],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "无权限绑定日志分组" in str(response.json())


@pytest.mark.django_db
def test_policy_create_rejects_unauthorized_organizations(api_client, authenticated_user, mocker):
    _mock_policy_permission_result(mocker, permission_data={}, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/policy/",
        data={
            "name": "cross-org-policy",
            "alert_type": "keyword",
            "alert_name": "cross-org-policy",
            "alert_level": "warning",
            "alert_condition": {"query": "error"},
            "schedule": {"type": "min", "value": 5},
            "period": {"type": "min", "value": 5},
            "organizations": [2],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Policy.objects.count() == 0


@pytest.mark.django_db
def test_policy_create_returns_bound_organizations(api_client, authenticated_user, mocker):
    _mock_policy_permission_result(mocker, permission_data={}, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/policy/",
        data={
            "name": "bound-org-policy",
            "alert_type": "keyword",
            "alert_name": "bound-org-policy",
            "alert_level": "warning",
            "alert_condition": {"query": "error"},
            "schedule": {"type": "min", "value": 5},
            "period": {"type": "min", "value": 5},
            "organizations": [1],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["data"]["organizations"] == [1]


@pytest.mark.django_db
def test_policy_create_rejects_invalid_organizations_payload(api_client, authenticated_user, mocker):
    _mock_policy_permission_result(mocker, permission_data={}, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/policy/",
        data={
            "name": "invalid-org-policy",
            "alert_type": "keyword",
            "alert_name": "invalid-org-policy",
            "alert_level": "warning",
            "alert_condition": {"query": "error"},
            "schedule": {"type": "min", "value": 5},
            "period": {"type": "min", "value": 5},
            "organizations": ["bad"],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["message"] == "organizations entries must be integers"
    assert Policy.objects.count() == 0


@pytest.mark.django_db
def test_policy_update_hides_unauthorized_policy(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy-update", organization=2)
    _mock_policy_permission_result(mocker, permission_data={}, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.patch(
        f"/api/v1/log/policy/{policy.id}/",
        data={"alert_name": "changed"},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    policy.refresh_from_db()
    assert policy.alert_name == "denied-policy-update"


@pytest.mark.django_db
def test_policy_update_rejects_view_only_instance_permission(api_client, authenticated_user, mocker):
    policy = _create_policy("view-only-policy", organization=2)
    _mock_policy_permission_result(
        mocker,
        permission_data={
            "None": {
                "instance": [{"id": policy.id, "permission": ["View"]}],
            }
        },
        teams=[1],
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.patch(
        f"/api/v1/log/policy/{policy.id}/",
        data={"alert_name": "changed"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    policy.refresh_from_db()
    assert policy.alert_name == "view-only-policy"


@pytest.mark.django_db
def test_policy_update_returns_updated_organizations(api_client, authenticated_user, mocker):
    policy = _create_policy("update-org-policy", organization=1)
    _mock_policy_permission_result(
        mocker,
        permission_data={
            "None": {
                "instance": [{"id": policy.id, "permission": ["Operate"]}],
            }
        },
        teams=[1],
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.patch(
        f"/api/v1/log/policy/{policy.id}/",
        data={"organizations": [1, 1]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["organizations"] == [1]


@pytest.mark.django_db
def test_policy_update_rejects_invalid_organizations_payload(api_client, authenticated_user, mocker):
    policy = _create_policy("invalid-update-org-policy", organization=1)
    _mock_policy_permission_result(
        mocker,
        permission_data={
            "None": {
                "instance": [{"id": policy.id, "permission": ["Operate"]}],
            }
        },
        teams=[1],
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.patch(
        f"/api/v1/log/policy/{policy.id}/",
        data={"organizations": ["bad"]},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["message"] == "organizations entries must be integers"
    assert list(policy.policyorganization_set.values_list("organization", flat=True)) == [1]


@pytest.mark.django_db
def test_policy_update_rejects_target_org_outside_authorized_scope(api_client, authenticated_user, mocker):
    policy = _create_policy("scoped-policy", organization=2)
    _mock_policy_permission_result(
        mocker,
        permission_data={
            "None": {
                "instance": [{"id": policy.id, "permission": ["Operate"]}],
            },
            "all": {"team": [2]},
        },
        teams=[1],
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.patch(
        f"/api/v1/log/policy/{policy.id}/",
        data={"organizations": [3]},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert list(policy.policyorganization_set.values_list("organization", flat=True)) == [2]


@pytest.mark.django_db
def test_policy_enable_rejects_view_only_instance_permission(api_client, authenticated_user, mocker):
    policy = _create_policy("toggle-policy", organization=2)
    _mock_policy_permission_result(
        mocker,
        permission_data={
            "None": {
                "instance": [{"id": policy.id, "permission": ["View"]}],
            }
        },
        teams=[1],
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        f"/api/v1/log/policy/{policy.id}/enable/",
        data={"enabled": False},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_policy_destroy_hides_unauthorized_policy(api_client, authenticated_user, mocker):
    policy = _create_policy("delete-policy", organization=2)
    _mock_policy_permission_result(mocker, permission_data={}, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.delete(f"/api/v1/log/policy/{policy.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert Policy.objects.filter(id=policy.id).exists()


@pytest.mark.django_db
def test_search_condition_rejects_unauthorized_log_groups(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-2", name="Denied", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-2", organization=2)
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/search_conditions/",
        data={
            "name": "saved-query",
            "condition": {"query": "*", "log_groups": ["g-2"]},
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert SearchCondition.objects.count() == 0


@pytest.mark.django_db
def test_search_condition_list_hides_inaccessible_saved_conditions(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Allowed", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroup.objects.create(id="g-2", name="Denied", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    LogGroupOrganization.objects.create(log_group_id="g-2", organization=2)
    SearchCondition.objects.create(name="allowed", condition={"query": "*", "log_groups": ["g-1"]}, organization=1, created_by="alice")
    SearchCondition.objects.create(name="denied", condition={"query": "*", "log_groups": ["g-2"]}, organization=1, created_by="alice")
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/search_conditions/")

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert len(payload["data"]) == 1
    assert payload["data"][0]["name"] == "allowed"


@pytest.mark.django_db
def test_log_group_builder_keeps_user_query_when_only_default_group_has_empty_rule():
    LogGroup.objects.create(id="default", name="Default", rule={})

    final_query, group_info = LogGroupQueryBuilder.build_query_with_groups('instance_id:"uuid"', ["default"])

    assert final_query == 'instance_id:"uuid"'
    assert group_info == [{"id": "default", "name": "Default", "status": "empty_rule"}]


@pytest.mark.django_db
def test_log_group_builder_keeps_base_query_when_default_is_selected_with_other_groups():
    LogGroup.objects.create(id="default", name="Default", rule={})
    LogGroup.objects.create(id="g-1", name="Group 1", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})

    final_query, group_info = LogGroupQueryBuilder.build_query_with_groups("*", ["default", "g-1"])

    assert final_query == "*"
    assert group_info == [
        {"id": "default", "name": "Default", "status": "empty_rule"},
        {"id": "g-1", "name": "Group 1", "status": "applied"},
    ]


@pytest.mark.django_db
def test_search_endpoint_with_specific_group_does_not_expand_to_other_accessible_groups(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="default", name="Default", rule={})
    LogGroup.objects.create(id="g-1", name="Group 1", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="default", organization=1)
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    _mock_group_permission(mocker, teams=[1])

    search_mock = mocker.patch("apps.log.views.search.SearchService.search_logs", return_value=[])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/search/search/",
        data={
            "query": 'instance_id:"uuid"',
            "start_time": "",
            "end_time": "",
            "limit": 10,
            "log_groups": ["g-1"],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    search_mock.assert_called_once_with('instance_id:"uuid"', "", "", 10, ["g-1"])


@pytest.mark.django_db
def test_field_values_endpoint_uses_explicit_log_groups(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Group 1", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    _mock_group_permission(mocker, teams=[1])
    field_values_mock = mocker.patch("apps.log.views.search.SearchService.field_values", return_value={"values": []})

    api_client.cookies["current_team"] = "1"
    response = api_client.get(
        "/api/v1/log/search/field_values/?filed=host&query=level:error&log_groups=g-1",
    )

    assert response.status_code == status.HTTP_200_OK
    field_values_mock.assert_called_once_with("", "", "host", 100, query="level:error", log_groups=["g-1"])


@pytest.mark.django_db
def test_hits_endpoint_uses_explicit_log_groups(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="Group 1", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    _mock_group_permission(mocker, teams=[1])
    hits_mock = mocker.patch("apps.log.views.search.SearchService.search_hits", return_value={"hits": []})

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/search/hits/",
        data={"query": "*", "field": "_stream", "fields_limit": 5, "step": "5m", "log_groups": ["g-1"]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    hits_mock.assert_called_once_with("*", "", "", "_stream", 5, "5m", ["g-1"])


@pytest.mark.django_db
def test_search_condition_retrieve_returns_404_for_inaccessible_saved_condition(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-2", name="Denied", rule={"mode": "AND", "conditions": [{"field": "app", "op": "==", "value": "demo"}]})
    LogGroupOrganization.objects.create(log_group_id="g-2", organization=2)
    condition = SearchCondition.objects.create(
        name="denied",
        condition={"query": "*", "log_groups": ["g-2"]},
        organization=1,
        created_by="alice",
    )
    _mock_group_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/search_conditions/{condition.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_alert_retrieve_hides_unauthorized_policy_alert(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy", organization=2)
    alert, _ = _create_alert_with_event(policy, "alert-denied", "event-denied")
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/alert/{alert.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_alert_closed_hides_unauthorized_policy_alert(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy-closed", organization=2)
    alert, _ = _create_alert_with_event(policy, "alert-closed-denied", "event-closed-denied")
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(f"/api/v1/log/alert/{alert.id}/closed/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_event_retrieve_hides_unauthorized_policy_event(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy-event", organization=2)
    _, event = _create_alert_with_event(policy, "alert-event-denied", "event-denied")
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/event/{event.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_event_raw_data_retrieve_hides_unauthorized_policy_event(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy-raw-detail", organization=2)
    _, event = _create_alert_with_event(policy, "alert-raw-detail-denied", "event-raw-detail-denied")
    raw = EventRawData.objects.create(event=event, data={"message": "raw"})
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/event_raw_data/{raw.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_last_event_returns_404_without_policy_permission(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy-last-event", organization=2)
    alert, _ = _create_alert_with_event(policy, "alert-last-event-denied", "event-last-event-denied")
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/alert/last_event/?alert_id={alert.id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["result"] is False


@pytest.mark.django_db
def test_event_raw_data_by_event_id_returns_404_without_policy_permission(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy-raw", organization=2)
    _, event = _create_alert_with_event(policy, "alert-raw-denied", "event-raw-denied")
    EventRawData.objects.create(event=event, data={"message": "raw"})
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/event_raw_data/by_event_id/?event_id={event.id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["result"] is False


@pytest.mark.django_db
def test_alert_snapshots_hides_unauthorized_policy_alert(api_client, authenticated_user, mocker):
    policy = _create_policy("denied-policy-snapshot", organization=2)
    alert, _ = _create_alert_with_event(policy, "alert-snapshot-denied", "event-snapshot-denied")
    AlertSnapshot.objects.create(alert=alert, policy=policy, source_id=alert.source_id, snapshots=[])
    _mock_policy_permission(mocker, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/alert/snapshots/{alert.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["result"] is False


@pytest.mark.django_db
def test_event_retrieve_allows_authorized_policy_event(api_client, authenticated_user, mocker):
    policy = _create_policy("allowed-policy-event", organization=1)
    _, event = _create_alert_with_event(policy, "alert-allowed", "event-allowed")
    _mock_policy_permission(mocker, policy_id=policy.id, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/event/{event.id}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["id"] == event.id


@pytest.mark.django_db
def test_alert_snapshots_returns_data_for_authorized_policy(api_client, authenticated_user, mocker):
    policy = _create_policy("allowed-policy-snapshot", organization=1)
    alert, _ = _create_alert_with_event(policy, "alert-snapshot-allowed", "event-snapshot-allowed")
    AlertSnapshot.objects.create(alert=alert, policy=policy, source_id=alert.source_id, snapshots=[{"type": "event"}])
    _mock_policy_permission(mocker, policy_id=policy.id, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/alert/snapshots/{alert.id}/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["alert_info"]["id"] == alert.id
    assert response.json()["data"]["snapshot_info"]["snapshot_count"] == 1


# ---------------------------------------------------------------------------
# Issue #3359: tail_async 的 iter_lines 必须在线程池中运行，不得阻塞事件循环
# ---------------------------------------------------------------------------

class _BlockingStreamResponse:
    """
    模拟一个"第一行来得很慢"的流式响应：
    iter_lines() 在产出第一行前会用 threading.Event.wait() 阻塞约 0.1s。
    若 iter_lines 仍在事件循环线程里调用，事件循环会被阻塞，
    同期调度的并发协程就无法运行，counter 不会递增。
    修复后，iter_lines 在独立线程中运行，事件循环自由调度，counter 可以递增。
    """

    status_code = 200

    def __init__(self, lines, block_secs=0.1):
        self._lines = lines
        self._block_secs = block_secs
        self.encoding = "utf-8"

    def raise_for_status(self):
        pass

    def iter_lines(self, chunk_size=None, decode_unicode=False):
        import time
        time.sleep(self._block_secs)  # 模拟等待网络数据的阻塞
        yield from self._lines

    def close(self):
        pass


@pytest.mark.asyncio
async def test_tail_async_iter_lines_runs_in_thread_not_event_loop(mocker):
    """
    验证修复：iter_lines 的阻塞等待必须在线程池里发生，事件循环在此期间
    应能调度其他协程（counter 递增）。
    若把修复 revert（直接 for line in response.iter_lines(...)），
    事件循环在 iter_lines 阻塞期间被冻结，counter 不会递增，断言失败。
    """
    lines = ["line1", "line2", "line3"]
    fake_resp = _BlockingStreamResponse(lines, block_secs=0.1)

    mocker.patch(
        "apps.log.utils.query_log.requests.post",
        return_value=fake_resp,
    )

    api = VictoriaMetricsAPI()

    # 并发协程：在 tail_async 运行期间尽量多递增 counter
    counter = 0

    async def increment_counter():
        nonlocal counter
        for _ in range(200):
            counter += 1
            await asyncio.sleep(0)

    collected = []
    counter_task = asyncio.create_task(increment_counter())

    async for line in api.tail_async("*"):
        collected.append(line)

    await counter_task

    # 修复后：iter_lines 在线程里阻塞，事件循环自由调度，counter 应已递增
    assert collected == ["line1", "line2", "line3"], f"收到的行不匹配: {collected}"
    assert counter > 0, (
        "counter 未递增——iter_lines 仍在事件循环线程里阻塞，事件循环被冻结。"
        "这说明修复未生效（iter_lines 没有被卸载到线程池）。"
    )
