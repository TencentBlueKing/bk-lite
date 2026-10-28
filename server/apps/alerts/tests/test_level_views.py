"""告警等级视图集覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-配置.md：等级支持增删改查，删除受引用与"每类型至少保留一个"约束。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.alert_operator import AlarmStrategy, AlertAssignment, AlertShield
from apps.alerts.models.models import Alert, Level
from apps.alerts.serializers.assignment_shield import AlertAssignmentModelSerializer, AlertShieldModelSerializer
from apps.alerts.serializers.strategy import AlarmStrategySerializer
from apps.alerts.views.level import LevelModelViewSet


def _request(method, path, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    if data is None:
        request = fn(path)
    else:
        request = fn(path, data=data, format="json")
    force_authenticate(request, user=user)
    return request


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _make_level(level_id, level_type="alert", **over):
    defaults = dict(
        level_id=level_id,
        level_name=f"L{level_id}",
        level_display_name=f"等级{level_id}",
        level_type=level_type,
    )
    defaults.update(over)
    return Level.objects.create(**defaults)


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    # JsonResponse (e.g. WebUtils.response_error) is already rendered
    return json.loads(response.content)


@pytest.mark.django_db
def test_level_list(superuser):
    _make_level(0)
    _make_level(1)
    request = _request("get", "/level/", superuser)
    response = LevelModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert len(items) == 2


@pytest.mark.django_db
def test_level_create(superuser):
    request = _request("post", "/level/", superuser, data={
        "level_id": 5,
        "level_name": "Critical",
        "level_display_name": "严重",
        "level_type": "alert",
    })
    response = LevelModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    assert Level.objects.filter(level_id=5, level_type="alert").exists()


@pytest.mark.django_db
def test_level_create_duplicate_rejected(superuser):
    _make_level(5)
    request = _request("post", "/level/", superuser, data={
        "level_id": 5,
        "level_name": "Dup",
        "level_display_name": "重复",
        "level_type": "alert",
    })
    response = LevelModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_level_create_negative_id_rejected(superuser):
    request = _request("post", "/level/", superuser, data={
        "level_id": -1,
        "level_name": "Bad",
        "level_display_name": "坏",
        "level_type": "alert",
    })
    response = LevelModelViewSet.as_view({"post": "create"})(request)
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_level_update_cannot_change_level_id(superuser):
    level = _make_level(0)
    _make_level(1)  # keep more than one of type
    request = _request("put", f"/level/{level.id}/", superuser, data={
        "level_id": 9,
        "level_name": "L0",
        "level_display_name": "等级0",
        "level_type": "alert",
    })
    response = LevelModelViewSet.as_view({"put": "update"})(request, pk=str(level.id))
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_level_destroy_last_of_type_rejected(superuser):
    level = _make_level(0)
    request = _request("delete", f"/level/{level.id}/", superuser)
    response = LevelModelViewSet.as_view({"delete": "destroy"})(request, pk=str(level.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "至少保留一个" in json.dumps(payload, ensure_ascii=False)
    assert Level.objects.filter(id=level.id).exists()


@pytest.mark.django_db
def test_level_destroy_referenced_by_alert_rejected(superuser):
    level = _make_level(0)
    _make_level(1)
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    request = _request("delete", f"/level/{level.id}/", superuser)
    response = LevelModelViewSet.as_view({"delete": "destroy"})(request, pk=str(level.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "引用" in json.dumps(payload, ensure_ascii=False)


@pytest.mark.django_db
def test_level_destroy_success(superuser):
    level = _make_level(0)
    _make_level(1)
    request = _request("delete", f"/level/{level.id}/", superuser)
    response = LevelModelViewSet.as_view({"delete": "destroy"})(request, pk=str(level.id))
    response.render()
    # CustomRenderer 将 DELETE 204 改写为 200
    assert response.status_code == status.HTTP_200_OK
    assert not Level.objects.filter(id=level.id).exists()


# --------------------------------------------------------------------------
# 引用检查辅助方法直接单测
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_data_reference_message_unknown_type_empty():
    assert LevelModelViewSet._get_data_reference_message("unknown", "0") == ""


@pytest.mark.django_db
def test_get_data_reference_message_with_alert():
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp")
    msg = LevelModelViewSet._get_data_reference_message("alert", "0")
    assert "告警" in msg


@pytest.mark.django_db
def test_get_config_reference_message_assignment_frequency():
    from apps.alerts.models.alert_operator import AlertAssignment

    AlertAssignment.objects.create(name="分派A", notification_frequency={"0": {}})
    msg = LevelModelViewSet._get_config_reference_message("alert", "0")
    assert "分派策略" in msg


@pytest.mark.django_db
def test_find_match_rules_reference_name():
    from apps.alerts.models.alert_operator import AlertShield

    shield = AlertShield.objects.create(name="屏蔽A", match_rules=[[{"key": "level", "value": "0"}]])
    name = LevelModelViewSet._find_match_rules_reference_name(
        AlertShield.objects.all(), "0", "level"
    )
    assert name == "屏蔽A"


def _delete_level(user, level):
    request = _request("delete", f"/level/{level.id}/", user)
    return LevelModelViewSet.as_view({"delete": "destroy"})(request, pk=str(level.id))


def _persist_validated_match_rules(serializer_cls, model, name, rules, **fields):
    validated_rules = serializer_cls().validate_match_rules(rules)
    return model.objects.create(name=name, match_rules=validated_rules, **fields)


class _RuleQuery:
    def __init__(self, rows):
        self._rows = rows

    def only(self, *args, **kwargs):
        return self._rows


class _RuleRow:
    def __init__(self, name, match_rules):
        self.name = name
        self.match_rules = match_rules


_LIST_REFERENCE_CASES = [
    pytest.param(
        "event",
        AlertShieldModelSerializer,
        AlertShield,
        "any_of",
        {"match_type": "filter", "suppression_time": {}},
        id="shield-any-of",
    ),
    pytest.param(
        "event",
        AlertShieldModelSerializer,
        AlertShield,
        "none_of",
        {"match_type": "filter", "suppression_time": {}},
        id="shield-none-of",
    ),
    pytest.param(
        "alert",
        AlertAssignmentModelSerializer,
        AlertAssignment,
        "any_of",
        {"match_type": "filter"},
        id="assignment-any-of",
    ),
    pytest.param(
        "alert",
        AlertAssignmentModelSerializer,
        AlertAssignment,
        "none_of",
        {"match_type": "filter"},
        id="assignment-none-of",
    ),
    pytest.param(
        "event",
        AlarmStrategySerializer,
        AlarmStrategy,
        "any_of",
        {},
        id="correlation-any-of",
    ),
    pytest.param(
        "event",
        AlarmStrategySerializer,
        AlarmStrategy,
        "none_of",
        {},
        id="correlation-none-of",
    ),
]


@pytest.mark.django_db
@pytest.mark.parametrize("level_type,serializer_cls,model,operator,extra", _LIST_REFERENCE_CASES)
def test_level_destroy_rejects_list_match_rule_reference(superuser, level_type, serializer_cls, model, operator, extra):
    referenced = _make_level(10, level_type=level_type)
    other = _make_level(1, level_type=level_type)
    spare = _make_level(2, level_type=level_type)
    rules = [[{"key": "level", "operator": operator, "value": ["10", "2"]}]]
    _persist_validated_match_rules(serializer_cls, model, f"{model.__name__}-{operator}", rules, **extra)

    response = _delete_level(superuser, referenced)
    payload = _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "引用" in json.dumps(payload, ensure_ascii=False)
    assert Level.objects.filter(id=referenced.id).exists()

    response = _delete_level(superuser, other)
    response.render()
    assert response.status_code == status.HTTP_200_OK
    assert not Level.objects.filter(id=other.id).exists()
    assert Level.objects.filter(id=referenced.id).exists()
    assert Level.objects.filter(id=spare.id).exists()


@pytest.mark.django_db
def test_find_match_rules_reference_name_scalar_and_tuple():
    shield = AlertShield.objects.create(
        name="标量整值",
        match_type="filter",
        match_rules=[[{"key": "level", "value": "10"}]],
        suppression_time={},
    )
    shields = AlertShield.objects.filter(id=shield.id)
    assert LevelModelViewSet._find_match_rules_reference_name(shields, "10", "level") == "标量整值"
    assert LevelModelViewSet._find_match_rules_reference_name(shields, "1", "level") == ""
    assert LevelModelViewSet._find_match_rules_reference_name(shields, "0", "level") == ""

    shield.match_rules = [[{"key": "level", "value": 10}]]
    shield.save(update_fields=["match_rules"])
    shields = AlertShield.objects.filter(id=shield.id)
    assert LevelModelViewSet._find_match_rules_reference_name(shields, "10", "level") == "标量整值"
    assert LevelModelViewSet._find_match_rules_reference_name(shields, "1", "level") == ""

    query = _RuleQuery([_RuleRow("元组级别", [[{"key": "level", "value": ("10", "2")}]])])
    assert LevelModelViewSet._find_match_rules_reference_name(query, "10", "level") == "元组级别"
    assert LevelModelViewSet._find_match_rules_reference_name(query, "2", "level") == "元组级别"
    assert LevelModelViewSet._find_match_rules_reference_name(query, "1", "level") == ""
    assert LevelModelViewSet._find_match_rules_reference_name(query, "0", "level") == ""
