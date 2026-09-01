"""LoginModuleViewSet 剩余：域名/重名校验、bk_lite 更新与级联删除。"""
import json

import pytest
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.system_mgmt.models import Group, LoginModule, User
from apps.system_mgmt.viewset.login_module_viewset import LoginModuleViewSet

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


def _actor():
    user = UserFactory(domain="domain.com", is_superuser=True)
    user.locale = "zh-Hans"
    return user


def _body(resp):
    return json.loads(resp.content)


def _req(action, method, actor, data=None, pk=None):
    fn = getattr(factory, method)
    request = fn("/x/", data=data or {}, format="json") if data is not None else fn("/x/")
    force_authenticate(request, user=actor)
    kwargs = {} if pk is None else {"pk": pk}
    return LoginModuleViewSet.as_view({method: action})(request, **kwargs)


def test_create_rejects_empty_domain_duplicate_name_and_bk_lite_domain():
    actor = _actor()
    empty = _req("create", "post", actor, data={"name": "ldap-a", "source_type": "ldap", "other_config": {}})
    assert _body(empty)["result"] is False
    assert _body(empty)["message"] == "创建登录模块需要提供域名。"

    LoginModule.objects.create(name="ldap-a", source_type="ldap", other_config={"domain": "a.com"})
    dup_name = _req(
        "create",
        "post",
        actor,
        data={"name": "ldap-a", "source_type": "ldap", "other_config": {"domain": "b.com"}},
    )
    assert _body(dup_name)["result"] is False
    assert _body(dup_name)["message"] == "已存在同名且同类型的登录模块。"

    LoginModule.objects.create(name="lite-a", source_type="bk_lite", other_config={"domain": "lite.com"})
    dup_domain = _req(
        "create",
        "post",
        actor,
        data={"name": "ldap-b", "source_type": "ldap", "other_config": {"domain": "lite.com"}},
    )
    assert _body(dup_domain)["result"] is False
    assert _body(dup_domain)["message"] == "该域名的登录模块已存在。"


def test_update_bk_lite_validates_domain_name_and_domain_unique():
    actor = _actor()
    target = LoginModule.objects.create(name="lite-edit", source_type="bk_lite", other_config={"domain": "old.com"})
    LoginModule.objects.create(name="lite-other", source_type="bk_lite", other_config={"domain": "taken.com"})

    empty = _req(
        "update",
        "put",
        actor,
        data={"name": "lite-edit", "source_type": "bk_lite", "other_config": {}},
        pk=target.id,
    )
    assert _body(empty)["result"] is False
    assert _body(empty)["message"] == "创建登录模块需要提供域名。"

    dup_name = _req(
        "update",
        "put",
        actor,
        data={"name": "lite-other", "source_type": "bk_lite", "other_config": {"domain": "new.com"}},
        pk=target.id,
    )
    assert _body(dup_name)["result"] is False
    assert _body(dup_name)["message"] == "已存在同名且同类型的登录模块。"

    dup_domain = _req(
        "update",
        "put",
        actor,
        data={"name": "lite-edit", "source_type": "bk_lite", "other_config": {"domain": "taken.com"}},
        pk=target.id,
    )
    assert _body(dup_domain)["result"] is False
    assert _body(dup_domain)["message"] == "该域名的登录模块已存在。"


def test_destroy_bk_lite_deletes_domain_users_groups_and_periodic_task():
    actor = _actor()
    top = Group.objects.create(name="LiteRoot", parent_id=0, description="lite-desc")
    Group.objects.create(name="LiteChild", parent_id=top.id, description="lite-desc")
    User.objects.create(
        username="lite-user",
        display_name="u",
        email="u@lite.com",
        password="x",
        domain="lite-del.com",
        group_list=[],
    )
    keep = User.objects.create(
        username="keep-user",
        display_name="k",
        email="k@example.com",
        password="x",
        domain="other.com",
        group_list=[],
    )
    schedule = IntervalSchedule.objects.create(every=1, period=IntervalSchedule.HOURS)
    PeriodicTask.objects.create(name="sync_user_group_lite-del", interval=schedule, task="x")
    module = LoginModule.objects.create(
        name="lite-del",
        source_type="bk_lite",
        other_config={"domain": "lite-del.com", "root_group": "LiteRoot"},
    )
    resp = _req("destroy", "delete", actor, pk=module.id)
    assert resp.status_code == 204
    assert not LoginModule.objects.filter(pk=module.id).exists()
    assert not User.objects.filter(username="lite-user").exists()
    assert User.objects.filter(pk=keep.pk).exists()
    assert not Group.objects.filter(description="lite-desc").exists()
    assert not PeriodicTask.objects.filter(name="sync_user_group_lite-del").exists()
