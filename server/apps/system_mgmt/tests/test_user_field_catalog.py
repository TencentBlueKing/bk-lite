"""用户字段保存接口：标识、类型、停用和删除规则。"""

import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.system_mgmt.models import Group, IntegrationInstance, Role, User, UserFieldDefinition, UserFieldValue, UserSyncSource
from apps.system_mgmt.viewset.user_field_viewset import UserFieldViewSet
from apps.system_mgmt.viewset.user_viewset import UserViewSet

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


def _body(resp):
    return json.loads(resp.content)


def _actor():
    user = UserFactory(domain="domain.com", is_superuser=True, locale="zh-Hans")
    user.group_list = []
    return user


def _field(action, data=None, method="post"):
    actor = _actor()
    request = getattr(factory, method)("/x/", data=data or {}, format="json")
    force_authenticate(request, user=actor)
    return UserFieldViewSet.as_view({method: action})(request)


def _source_mapping(mapping):
    instance = IntegrationInstance.objects.create(
        name="field-map",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready"},
        config={},
    )
    return UserSyncSource.objects.create(
        name="field-map-source",
        integration_instance=instance,
        enabled=True,
        root_group_name="Field Map Root",
        business_config={"root_department_id": "0"},
        field_mapping=mapping,
        schedule_config={"mode": "disabled"},
    )


def test_field_key_is_immutable_and_cannot_reuse_profile_names():
    created = _field("create_field", {"name": "工牌", "key": "badge_no", "field_type": "text"})
    assert _body(created)["result"] is True
    field_id = _body(created)["data"]["id"]

    renamed = _field("update_field", {"id": field_id, "name": "工牌号", "key": "badge", "description": "说明"})
    assert _body(renamed)["message"] == "字段标识保存后不能修改"

    reserved = _field("create_field", {"name": "工号", "key": "employee_no", "field_type": "text"})
    assert _body(reserved)["result"] is False
    disabled_key = _field("create_field", {"name": "禁用", "key": "disabled", "field_type": "text"})
    assert _body(disabled_key)["result"] is False


def test_type_change_and_delete_are_blocked_by_values_or_mappings():
    created = _field("create_field", {"name": "工牌", "key": "badge_no", "field_type": "text", "description": "旧说明"})
    field_id = _body(created)["data"]["id"]
    definition = UserFieldDefinition.objects.get(id=field_id)
    group = Group.objects.create(name="field-users")
    user = User.objects.create(
        username="field-user",
        display_name="字段用户",
        email="field-user@example.com",
        password="x",
        domain="domain.com",
        group_list=[group.id],
    )
    UserFieldValue.objects.create(user=user, field=definition, value="A1")

    changed = _field("update_field", {"id": field_id, "name": "工牌", "field_type": "number", "description": "新说明"})
    assert _body(changed)["message"] == "已有值或已被同步映射的字段不能修改类型"
    removed = _field("delete_field", {"id": field_id})
    assert _body(removed)["message"] == "已有值或已被同步映射的字段不能删除"

    UserFieldValue.objects.all().delete()
    _source_mapping({"username": "user_id", "badge_no": "badge"})
    mapped_type = _field("update_field", {"id": field_id, "name": "工牌", "field_type": "date"})
    assert _body(mapped_type)["message"] == "已有值或已被同步映射的字段不能修改类型"
    mapped_disable = _field("disable_field", {"id": field_id})
    assert _body(mapped_disable)["message"] == "请先解除同步映射，再停用字段"

    source = UserSyncSource.objects.get(name="field-map-source")
    source.field_mapping = {"username": "user_id"}
    source.save(update_fields=["field_mapping"])
    disabled = _field("disable_field", {"id": field_id})
    assert _body(disabled)["result"] is True
    definition.refresh_from_db()
    assert definition.is_enabled is False

    renamed = _field("update_field", {"id": field_id, "name": "历史工牌", "description": "保留"})
    assert _body(renamed)["result"] is True
    definition.refresh_from_db()
    assert definition.name == "历史工牌"
    assert UserFieldDefinition.objects.filter(id=field_id).exists()


def test_disabled_field_is_not_written_by_user_save_and_stays_readable():
    definition = UserFieldDefinition.objects.create(name="工牌", key="badge_no", field_type="text", is_enabled=False)
    group = Group.objects.create(name="save-users")
    Role.objects.get_or_create(name="admin", app="")
    user = User.objects.create(
        username="save-user",
        display_name="保存用户",
        email="save-user@example.com",
        password="x",
        domain="domain.com",
        group_list=[group.id],
        locale="zh-Hans",
        timezone="Asia/Shanghai",
    )
    UserFieldValue.objects.create(user=user, field=definition, value="A1")
    actor = _actor()
    actor.group_list = [{"id": group.id}]
    request = factory.post(
        "/x/",
        data={
            "user_id": user.id,
            "username": user.username,
            "lastName": "保存用户",
            "email": user.email,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [group.id],
            "roles": [],
            "custom_fields": {"badge_no": "B2"},
        },
        format="json",
    )
    force_authenticate(request, user=actor)
    response = UserViewSet.as_view({"post": "update_user"})(request)
    assert _body(response)["result"] is False
    assert UserFieldValue.objects.get(user=user, field=definition).value == "A1"

    detail_request = factory.post("/x/", data={"user_id": user.id}, format="json")
    force_authenticate(detail_request, user=actor)
    detail = UserViewSet.as_view({"post": "get_user_detail"})(detail_request)
    rows = _body(detail)["data"]["custom_fields"]
    assert rows[0]["key"] == "badge_no"
    assert rows[0]["value"] == "A1"
    assert rows[0]["is_enabled"] is False
