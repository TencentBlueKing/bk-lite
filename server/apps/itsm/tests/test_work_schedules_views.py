import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from django.db import connection, connections

from apps.itsm.models.extend import ChangeWindow, DutyShift
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.extend import resource_item, resources
from apps.itsm.views.users import UserSearchView
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db

CHANGE = ["change-View", "change-Add", "change-Edit", "change-Delete"]
DUTY = ["duty-View", "duty-Add", "duty-Edit", "duty-Delete"]
WINDOW = {"name": "发布窗口", "start_at": "2026-12-01T09:00:00+08:00", "end_at": "2026-12-01T11:00:00+08:00"}


def data(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def test_change_window_dates_required_and_strictly_increasing():
    for window in (
        {"name": "仅名称"},
        {**WINDOW, "start_at": "2026-12-01T09:00:00"},
        {**WINDOW, "start_at": "2026-12-01"},
        {**WINDOW, "start_at": WINDOW["end_at"]},
        {**WINDOW, "start_at": "2026-12-01T12:00:00+08:00"},
    ):
        assert resources(request("post", window, permissions=CHANGE), "changes").status_code == 400
    assert not ChangeWindow.objects.exists()


def test_change_window_overlap_uses_instants_and_same_domain_for_create_and_edit():
    first = data(resources(request("post", WINDOW, permissions=CHANGE), "changes"))
    adjacent = {**WINDOW, "name": "接续发布", "start_at": WINDOW["end_at"], "end_at": "2026-12-01T04:00:00Z"}
    second = data(resources(request("post", adjacent, permissions=CHANGE), "changes"))
    assert data(resource_item(request("patch", {"name": "更名"}, permissions=CHANGE), "changes", first["id"]))["name"] == "更名"
    overlap = {"start_at": "2026-12-01T02:00:00Z"}
    assert resource_item(request("patch", overlap, permissions=CHANGE), "changes", second["id"]).status_code == 400
    assert resources(request("post", {**WINDOW, **overlap}, permissions=CHANGE), "changes").status_code == 400
    assert data(resources(request("post", WINDOW, permissions=CHANGE, domain="other.test"), "changes"))["id"] != first["id"]
    assert resource_item(request("delete", permissions=CHANGE, domain="other.test"), "changes", first["id"]).status_code == 404
    assert data(resource_item(request("delete", permissions=CHANGE), "changes", first["id"])) == {"id": first["id"]}


def test_change_window_permission_flags_and_invalid_collection_method():
    readonly = data(resources(request(permissions=["change-View"]), "changes"))
    assert [readonly[key] for key in ("can_add", "can_edit", "can_delete")] == [False, False, False]
    editor = data(resources(request(permissions=CHANGE), "changes"))
    assert [editor[key] for key in ("can_add", "can_edit", "can_delete")] == [True, True, True]
    assert resources(request("post", WINDOW, permissions=["change-View"]), "changes").status_code == 403
    assert resources(request("patch", WINDOW, permissions=CHANGE), "changes").status_code == 405
    assert not ChangeWindow.objects.exists()


def test_duty_roster_requires_day_and_active_same_domain_members():
    User.objects.create(username="local", display_name="值班员", domain="domain.com")
    User.objects.create(username="off", domain="domain.com", disabled=True)
    User.objects.create(username="external", domain="other.test")
    shift = {"name": "白班", "day": "2026-12-01", "members": ["local"]}
    for invalid in ({"day": None}, {"day": "2026-12-32"}, {"members": []}, {"members": "local"}, {"members": ["off"]}, {"members": ["external"]}):
        assert resources(request("post", {**shift, **invalid}, permissions=DUTY), "duties").status_code == 400
    saved = data(resources(request("post", {**shift, "members": ["local", "local"]}, permissions=DUTY), "duties"))
    assert saved["day"] == "2026-12-01"
    assert saved["members"] == ["local"]
    assert resource_item(request("patch", {"members": ["external"]}, permissions=DUTY), "duties", saved["id"]).status_code == 400
    assert resource_item(request("patch", {"day": "2026-12-02"}, permissions=DUTY, domain="other.test"), "duties", saved["id"]).status_code == 404
    assert resource_item(request("patch", {"day": "2026-12-02"}, permissions=["duty-View"]), "duties", saved["id"]).status_code == 403
    changed = data(resource_item(request("patch", {"day": "2026-12-02"}, permissions=DUTY), "duties", saved["id"]))
    assert changed["day"] == "2026-12-02"
    assert changed["members"] == ["local"]
    listed = data(resources(request(permissions=["duty-View"]), "duties"))
    assert listed["items"] == [changed]
    assert [listed[key] for key in ("can_add", "can_edit", "can_delete")] == [False, False, False]


def test_legacy_duty_check_in_cannot_modify_the_roster():
    shift = DutyShift.objects.create(name="白班", day=date(2026, 12, 1), members=["local"], domain="domain.com")
    response = resources(request("post", {"name": shift.name, "check_in": True}, permissions=DUTY), "duties")
    assert response.status_code == 400
    shift.refresh_from_db()
    assert shift.members == ["local"]
    assert DutyShift.objects.count() == 1


@pytest.mark.parametrize("permission", ["duty-Add", "duty-Edit", "org-Edit"])
def test_schedule_and_group_editors_can_search_local_member_options(permission):
    User.objects.create(username="member", domain="domain.com")
    User.objects.create(username="member_disabled", domain="domain.com", disabled=True)
    User.objects.create(username="member_external", domain="other.test")
    response = UserSearchView().get(request(payload={"q": "member"}, permissions=[permission]))
    assert response.status_code == 200
    assert [item["username"] for item in response.data["items"]] == ["member"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_overlapping_windows_only_create_one():
    if not connection.features.has_select_for_update:
        pytest.skip("并发写入验证需要支持行锁的数据库")
    start = Barrier(2)

    def create():
        try:
            start.wait(timeout=10)
            return resources(request("post", WINDOW, permissions=CHANGE, domain="overlap.test"), "changes").status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create)
        second = executor.submit(create)
        assert sorted([first.result(timeout=20), second.result(timeout=20)]) == [200, 400]
    assert ChangeWindow.objects.filter(domain="overlap.test").count() == 1
