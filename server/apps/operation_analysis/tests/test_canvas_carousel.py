"""轮播列表：权限、组织过滤、条目校验与播放可用状态。"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.models.carousel import CanvasCarousel, CanvasCarouselItem
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, NetworkTopology, Report, Screen, Topology
from apps.operation_analysis.views.carousel_view import CanvasCarouselViewSet


def _request(method, path, user, data=None, team="1", include_children="0"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    if team is not None:
        request.COOKIES["current_team"] = team
    request.COOKIES["include_children"] = include_children
    force_authenticate(request, user=user)
    return request


def _render(response):
    if hasattr(response, "render"):
        response.render()
    content = getattr(response, "rendered_content", None) or getattr(response, "content", b"")
    if not content:
        return None
    return json.loads(content)


def _payload(response):
    body = _render(response)
    if isinstance(body, dict) and body.get("result") is True and "data" in body:
        return body["data"]
    return body


def _rows(response):
    body = _payload(response)
    if isinstance(body, dict) and "items" in body:
        return body["items"]
    return body


def _viewer(user, *, permission=None, groups=None, superuser=False):
    user.is_superuser = superuser
    user.permission = permission if permission is not None else {"ops-analysis": {"view-View", "view-AddChart", "view-EditChart", "view-DeleteChart"}}
    user.group_list = groups if groups is not None else [{"id": 1, "name": "Default"}]
    return user


def _directory(name="目录", groups=None, **kwargs):
    return Directory.objects.create(name=name, groups=groups or [1], created_by="testuser", **kwargs)


def _dashboard(name, groups=None, **kwargs):
    groups = groups or [1]
    if "directory" not in kwargs:
        kwargs["directory"] = _directory(f"{name}目录", groups=groups)
    return Dashboard.objects.create(name=name, groups=groups, created_by="testuser", **kwargs)


def _call(view, method, user, path="/carousel/", data=None, team="1", include_children="0", **kwargs):
    response = CanvasCarouselViewSet.as_view(view)(
        _request(method, path, user, data=data, team=team, include_children=include_children),
        **kwargs,
    )
    return response


def _create_payload(name="值班轮播", canvas=None, groups=None, items=None, dwell=30):
    if items is None:
        items = []
        if canvas is not None:
            items = [{"resource_type": "dashboard", "canvas_id": canvas.id}]
    payload = {
        "name": name,
        "desc": "说明",
        "default_dwell_seconds": dwell,
        "items": items,
    }
    if groups is not None:
        payload["groups"] = groups
    return payload


@pytest.mark.django_db
def test_permissions_split_view_add_edit_delete(authenticated_user):
    user = _viewer(authenticated_user, permission={"ops-analysis": set()})
    canvas = _dashboard("权限盘")

    denied_list = _call({"get": "list"}, "get", user)
    assert denied_list.status_code == status.HTTP_403_FORBIDDEN

    user.permission = {"ops-analysis": {"view-View"}}
    created = _call({"post": "create"}, "post", user, data=_create_payload(canvas=canvas))
    assert created.status_code == status.HTTP_403_FORBIDDEN

    user.permission = {"ops-analysis": {"view-AddChart"}}
    created = _call({"post": "create"}, "post", user, data=_create_payload(canvas=canvas))
    assert created.status_code == status.HTTP_201_CREATED
    carousel_id = _payload(created)["id"]

    user.permission = {"ops-analysis": {"view-View"}}
    listed = _call({"get": "list"}, "get", user)
    assert listed.status_code == status.HTTP_200_OK
    rows = _rows(listed)
    assert rows[0]["item_count"] == 1
    assert rows[0]["name"] == "值班轮播"

    renamed = _call(
        {"patch": "partial_update"},
        "patch",
        user,
        path=f"/carousel/{carousel_id}/",
        data={"name": "改名"},
        pk=carousel_id,
    )
    assert renamed.status_code == status.HTTP_403_FORBIDDEN

    user.permission = {"ops-analysis": {"view-EditChart"}}
    renamed = _call(
        {"patch": "partial_update"},
        "patch",
        user,
        path=f"/carousel/{carousel_id}/",
        data={"name": "改名"},
        pk=carousel_id,
    )
    assert renamed.status_code == status.HTTP_200_OK
    assert _payload(renamed)["name"] == "改名"

    user.permission = {"ops-analysis": {"view-View"}}
    deleted = _call({"delete": "destroy"}, "delete", user, path=f"/carousel/{carousel_id}/", pk=carousel_id)
    assert deleted.status_code == status.HTTP_403_FORBIDDEN

    user.permission = {"ops-analysis": {"view-DeleteChart"}}
    deleted = _call({"delete": "destroy"}, "delete", user, path=f"/carousel/{carousel_id}/", pk=carousel_id)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert not CanvasCarousel.objects.filter(pk=carousel_id).exists()


@pytest.mark.django_db
def test_org_filter_name_scope_and_include_children(authenticated_user):
    user = _viewer(authenticated_user)
    user.group_list = [{"id": 1, "name": "父"}, {"id": 2, "name": "子"}]
    user.group_tree = [{"id": 1, "name": "父", "subGroups": [{"id": 2, "name": "子"}]}]
    own = _dashboard("本组织盘", groups=[1])
    child_canvas = _dashboard("子组织盘", groups=[2])
    other = _dashboard("外组织盘", groups=[3])

    created = _call({"post": "create"}, "post", user, data=_create_payload("父组织轮播", own, groups=[1]))
    assert created.status_code == status.HTTP_201_CREATED
    child_list = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload("子组织轮播", child_canvas, groups=[2]),
        team="2",
    )
    assert child_list.status_code == status.HTTP_201_CREATED
    child_id = _payload(child_list)["id"]

    rows = _rows(_call({"get": "list"}, "get", user, team="1"))
    assert {row["name"] for row in rows} == {"父组织轮播"}

    rows = _rows(_call({"get": "list"}, "get", user, team="1", include_children="1"))
    assert {row["name"] for row in rows} == {"父组织轮播", "子组织轮播"}

    hidden = _call({"get": "retrieve"}, "get", user, path=f"/carousel/{child_id}/", pk=child_id, team="1")
    assert hidden.status_code == status.HTTP_404_NOT_FOUND

    same_name_other_org = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload("父组织轮播", other, groups=[3]),
        team="1",
    )
    assert same_name_other_org.status_code == status.HTTP_403_FORBIDDEN

    user.group_list = [{"id": 1}, {"id": 3}]
    duplicated = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload("父组织轮播", own, groups=[1]),
        team="1",
    )
    assert duplicated.status_code == status.HTTP_400_BAD_REQUEST

    disjoint = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload("父组织轮播", other, groups=[3]),
        team="3",
    )
    assert disjoint.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_item_validation_keeps_existing_invalid_reference(authenticated_user):
    user = _viewer(authenticated_user)
    visible = _dashboard("可见盘", groups=[1])
    hidden = _dashboard("隐藏盘", groups=[2])
    builtin = _dashboard("内置盘", groups=[1], is_build_in=True, build_in_key="carousel-builtin")

    rejected = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload("非法引用", items=[{"resource_type": "dashboard", "canvas_id": hidden.id}]),
    )
    assert rejected.status_code == status.HTTP_400_BAD_REQUEST
    assert not CanvasCarousel.objects.exists()

    created = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload(
            "混合",
            items=[
                {"resource_type": "dashboard", "canvas_id": visible.id, "dwell_seconds": 12},
                {"resource_type": "dashboard", "canvas_id": builtin.id},
            ],
            dwell=40,
        ),
    )
    assert created.status_code == status.HTTP_201_CREATED
    carousel_id = _payload(created)["id"]
    visible_item_id = CanvasCarouselItem.objects.get(carousel_id=carousel_id, canvas_id=visible.id).id

    visible.groups = [2]
    visible.save(update_fields=["groups"])

    kept = _call(
        {"patch": "partial_update"},
        "patch",
        user,
        path=f"/carousel/{carousel_id}/",
        data={
            "name": "仍保留失效项",
            "items": [
                {"id": visible_item_id, "resource_type": "dashboard", "canvas_id": visible.id, "dwell_seconds": 12},
                {
                    "id": CanvasCarouselItem.objects.get(carousel_id=carousel_id, canvas_id=builtin.id).id,
                    "resource_type": "dashboard",
                    "canvas_id": builtin.id,
                },
            ],
        },
        pk=carousel_id,
    )
    assert kept.status_code == status.HTTP_200_OK
    detail = _payload(kept)
    invalid = next(item for item in detail["items"] if item["canvas_id"] == visible.id)
    assert invalid["exists"] is True
    assert invalid["visible"] is False
    assert invalid["available"] is False
    assert "canvas_name" not in invalid
    assert "canvas_group_ids" not in invalid
    assert "hidden_group_ids" not in invalid
    assert detail["items"][1]["available"] is True
    assert detail["items"][1]["canvas_name"] == "内置盘"
    assert detail["items"][1]["resolved_dwell_seconds"] == 40
    assert invalid["resolved_dwell_seconds"] == 12

    swapped = _call(
        {"patch": "partial_update"},
        "patch",
        user,
        path=f"/carousel/{carousel_id}/",
        data={
            "items": [
                {"id": visible_item_id, "resource_type": "dashboard", "canvas_id": hidden.id},
            ]
        },
        pk=carousel_id,
    )
    assert swapped.status_code == status.HTTP_400_BAD_REQUEST
    assert CanvasCarouselItem.objects.filter(carousel_id=carousel_id).count() == 2


@pytest.mark.django_db
def test_dwell_bounds_item_limit_and_playback_availability(authenticated_user):
    user = _viewer(authenticated_user, groups=[{"id": 1, "name": "甲"}, {"id": 2, "name": "乙"}])
    directory = _directory("网目录")
    canvases = {
        "dashboard": _dashboard("盘", groups=[1, 2]),
        "topology": Topology.objects.create(name="拓扑", groups=[1], directory=directory, created_by="testuser"),
        "architecture": Architecture.objects.create(name="架构", groups=[1], directory=directory, created_by="testuser"),
        "screen": Screen.objects.create(name="大屏", groups=[1], directory=directory, created_by="testuser"),
        "report": Report.objects.create(name="报表", groups=[1], directory=directory, created_by="testuser"),
        "networkTopology": NetworkTopology.objects.create(
            name="网络",
            directory=directory,
            base_url="https://weops.example.com",
            groups=[1],
            created_by="testuser",
        ),
    }
    items = [{"resource_type": resource_type, "canvas_id": canvas.id} for resource_type, canvas in canvases.items()]
    created = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload("六种", items=items, groups=[1, 2], dwell=30),
    )
    assert created.status_code == status.HTTP_201_CREATED
    carousel_id = _payload(created)["id"]
    detail = _payload(created)
    dashboard_item = next(item for item in detail["items"] if item["resource_type"] == "dashboard")
    assert "hidden_group_ids" not in dashboard_item
    assert dashboard_item["canvas_group_ids"] == [1, 2]
    assert "skipped_count" not in detail

    too_short = _call(
        {"patch": "partial_update"},
        "patch",
        user,
        data={"default_dwell_seconds": 4},
        pk=carousel_id,
    )
    assert too_short.status_code == status.HTTP_400_BAD_REQUEST
    too_long = _call(
        {"patch": "partial_update"},
        "patch",
        user,
        data={"items": [{"resource_type": "dashboard", "canvas_id": canvases["dashboard"].id, "dwell_seconds": 301}]},
        pk=carousel_id,
    )
    assert too_long.status_code == status.HTTP_400_BAD_REQUEST

    overflow = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload(
            "超限",
            items=[{"resource_type": "dashboard", "canvas_id": canvases["dashboard"].id}] * 51,
            groups=[1],
        ),
    )
    assert overflow.status_code == status.HTTP_400_BAD_REQUEST

    Dashboard.objects.filter(pk=canvases["dashboard"].id).delete()
    Topology.objects.filter(pk=canvases["topology"].id).update(groups=[9])
    refreshed = _payload(_call({"get": "retrieve"}, "get", user, path=f"/carousel/{carousel_id}/", pk=carousel_id))
    by_type = {item["resource_type"]: item for item in refreshed["items"]}
    assert by_type["dashboard"]["exists"] is False
    assert by_type["dashboard"]["available"] is False
    assert "canvas_name" not in by_type["dashboard"]
    assert "canvas_group_ids" not in by_type["dashboard"]
    assert by_type["topology"]["exists"] is True
    assert by_type["topology"]["visible"] is False
    assert "canvas_name" not in by_type["topology"]
    assert "canvas_group_ids" not in by_type["topology"]
    assert by_type["architecture"]["available"] is True
    assert by_type["architecture"]["canvas_name"] == "架构"
    assert by_type["architecture"]["canvas_group_ids"] == [1]
    assert by_type["screen"]["available"] is True
    assert by_type["report"]["available"] is True
    assert by_type["networkTopology"]["available"] is True
    assert "skipped_count" not in refreshed
    assert sum(1 for item in refreshed["items"] if not item["available"]) == 2

    edges = _call(
        {"patch": "partial_update"},
        "patch",
        user,
        data={"default_dwell_seconds": 5},
        pk=carousel_id,
    )
    assert edges.status_code == status.HTTP_200_OK
    upper = _call(
        {"patch": "partial_update"},
        "patch",
        user,
        data={"default_dwell_seconds": 300},
        pk=carousel_id,
    )
    assert upper.status_code == status.HTTP_200_OK
    assert _payload(upper)["default_dwell_seconds"] == 300


@pytest.mark.django_db
def test_append_follows_current_org_visibility(authenticated_user):
    user = _viewer(authenticated_user)
    user.group_list = [{"id": 1, "name": "甲"}, {"id": 2, "name": "乙"}]
    canvas = _dashboard("可追加", groups=[1])
    another = _dashboard("另一张可追加", groups=[1])
    hidden = _dashboard("不可追加", groups=[2])
    created = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload("原列表", canvas, groups=[1, 2]),
    )
    carousel_id = _payload(created)["id"]

    user.permission = {"ops-analysis": {"view-EditChart"}}
    refused = _call(
        {"post": "append"},
        "post",
        user,
        path=f"/carousel/{carousel_id}/append/",
        data={"resource_type": "dashboard", "canvas_id": hidden.id},
        pk=carousel_id,
        team="1",
    )
    assert refused.status_code == status.HTTP_400_BAD_REQUEST
    assert CanvasCarouselItem.objects.filter(carousel_id=carousel_id).count() == 1

    appended = _call(
        {"post": "append"},
        "post",
        user,
        path=f"/carousel/{carousel_id}/append/",
        data={"resource_type": "dashboard", "canvas_id": another.id, "dwell_seconds": 8},
        pk=carousel_id,
    )
    assert appended.status_code == status.HTTP_200_OK
    assert len(_payload(appended)["items"]) == 2
    assert _payload(appended)["items"][-1]["resolved_dwell_seconds"] == 8

    user.permission = {"ops-analysis": {"view-View", "view-EditChart"}}
    rows = _rows(_call({"get": "list"}, "get", user, path="/carousel/?name=原列表"))
    assert {row["name"] for row in rows} == {"原列表"}


@pytest.mark.django_db
def test_directory_activation_gates_visibility_without_leaking_name(authenticated_user):
    user = _viewer(authenticated_user)
    directory = _directory("会停用", groups=[1])
    canvas = _dashboard("目录盘", groups=[1], directory=directory)
    created = _call({"post": "create"}, "post", user, data=_create_payload("停用前", canvas))
    assert created.status_code == status.HTTP_201_CREATED
    carousel_id = _payload(created)["id"]
    assert _payload(created)["items"][0]["canvas_name"] == "目录盘"
    assert _payload(created)["items"][0]["canvas_group_ids"] == [1]

    directory.is_active = False
    directory.save(update_fields=["is_active"])
    detail = _payload(_call({"get": "retrieve"}, "get", user, path=f"/carousel/{carousel_id}/", pk=carousel_id))
    item = detail["items"][0]
    assert item["exists"] is True
    assert item["visible"] is False
    assert item["available"] is False
    assert "canvas_name" not in item
    assert "canvas_group_ids" not in item
    assert "skipped_count" not in detail

    foreign_directory = _directory("外目录", groups=[2])
    foreign_canvas = _dashboard("画布在当前组织但目录不在", groups=[1], directory=foreign_directory)
    rejected = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload("目录不可见", foreign_canvas),
    )
    assert rejected.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_same_canvas_cannot_be_added_twice(authenticated_user):
    user = _viewer(authenticated_user)
    first = _dashboard("第一张")
    second = _dashboard("第二张")
    rejected = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload(
            "重复画布",
            items=[
                {"resource_type": "dashboard", "canvas_id": first.id},
                {"resource_type": "dashboard", "canvas_id": first.id},
            ],
        ),
    )
    assert rejected.status_code == status.HTTP_400_BAD_REQUEST
    assert not CanvasCarousel.objects.exists()

    created = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload(
            "两张不同画布",
            items=[
                {"resource_type": "dashboard", "canvas_id": first.id},
                {"resource_type": "dashboard", "canvas_id": second.id, "dwell_seconds": 12},
            ],
        ),
    )
    assert created.status_code == status.HTTP_201_CREATED
    carousel_id = _payload(created)["id"]
    rows = _rows(_call({"get": "list"}, "get", user))
    listed = next(row for row in rows if row["id"] == carousel_id)
    assert listed["duration_seconds"] == 42
    assert listed["playable_count"] == 2
    assert listed["canvas_keys"] == [f"dashboard:{first.id}", f"dashboard:{second.id}"]

    appended = _call(
        {"post": "append"},
        "post",
        user,
        path=f"/carousel/{carousel_id}/append/",
        data={"resource_type": "dashboard", "canvas_id": first.id},
        pk=carousel_id,
    )
    assert appended.status_code == status.HTTP_400_BAD_REQUEST
    assert CanvasCarouselItem.objects.filter(carousel_id=carousel_id).count() == 2

    updated = _call(
        {"patch": "partial_update"},
        "patch",
        user,
        path=f"/carousel/{carousel_id}/",
        data={
            "items": [
                {"resource_type": "dashboard", "canvas_id": second.id},
                {"resource_type": "dashboard", "canvas_id": second.id},
            ],
        },
        pk=carousel_id,
    )
    assert updated.status_code == status.HTTP_400_BAD_REQUEST
    kept = CanvasCarouselItem.objects.filter(carousel_id=carousel_id).order_by("position")
    assert [item.canvas_id for item in kept] == [first.id, second.id]


@pytest.mark.django_db
def test_list_duration_skips_invisible_canvases_without_names(authenticated_user):
    user = _viewer(authenticated_user)
    visible = _dashboard("可见盘", groups=[1])
    hidden_directory = _directory("将停用", groups=[1])
    hidden = _dashboard("隐藏盘", groups=[1], directory=hidden_directory)
    created = _call(
        {"post": "create"},
        "post",
        user,
        data=_create_payload(
            "含失效",
            items=[
                {"resource_type": "dashboard", "canvas_id": visible.id, "dwell_seconds": 10},
                {"resource_type": "dashboard", "canvas_id": hidden.id, "dwell_seconds": 200},
            ],
        ),
    )
    assert created.status_code == status.HTTP_201_CREATED
    carousel_id = _payload(created)["id"]
    hidden_directory.is_active = False
    hidden_directory.save(update_fields=["is_active"])

    rows = _rows(_call({"get": "list"}, "get", user))
    listed = next(row for row in rows if row["id"] == carousel_id)
    assert listed["item_count"] == 2
    assert listed["playable_count"] == 1
    assert listed["duration_seconds"] == 10
    assert "隐藏盘" not in json.dumps(listed, ensure_ascii=False)
    assert "canvas_name" not in listed
