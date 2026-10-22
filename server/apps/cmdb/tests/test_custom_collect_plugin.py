from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.change_record import ChangeRecord
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.custom_collect_plugin import CustomCollectPlugin
from apps.cmdb.serializers.custom_collect_plugin import CustomCollectPluginSerializer
from apps.cmdb.services.custom_collect_plugin import ensure_deletable, ensure_model_deletable, reference_count, validate_plugin_payload
from apps.cmdb.views.custom_collect_plugin import CustomCollectPluginViewSet
from apps.core.exceptions.base_app_exception import BaseAppException

SCRIPT = '#!/bin/bash\necho \'[{"inst_name":"demo"}]\'\n'


def _payload(**overrides):
    data = {
        "name": "自定义主机",
        "plugin_id": "custom_host_scan",
        "model_id": "host",
        "os_type": "linux",
        "shell": "bash",
        "content": SCRIPT,
        "team": [1],
    }
    data.update(overrides)
    return data


def _request():
    return SimpleNamespace(user=SimpleNamespace(username="alice", group_list=[{"id": 1, "name": "org-a"}], is_superuser=False), COOKIES={})


def test_plugin_id_suffix_is_prefixed_by_server():
    with pytest.raises(BaseAppException, match="插件标识"):
        validate_plugin_payload(_payload(plugin_id="a"))
    with pytest.raises(BaseAppException, match="插件标识"):
        validate_plugin_payload(_payload(plugin_id=""))


@pytest.mark.django_db
def test_plugin_id_without_prefix_is_stored_with_custom_prefix():
    created = validate_plugin_payload(_payload(plugin_id="host_scan"))
    assert created["plugin_id"] == "custom_host_scan"
    again = validate_plugin_payload(_payload(plugin_id="custom_host_scan"))
    assert again["plugin_id"] == "custom_host_scan"


@pytest.mark.django_db
def test_plugin_id_collision_hides_owner():
    CustomCollectPlugin.objects.create(**validate_plugin_payload(_payload()))
    with pytest.raises(BaseAppException, match="标识已被占用"):
        validate_plugin_payload(_payload(name="另一份", team=[2]))


def test_shell_must_match_os_and_script_has_size_limit():
    with pytest.raises(BaseAppException, match="解释器"):
        validate_plugin_payload(_payload(os_type="windows", shell="bash"))
    with pytest.raises(BaseAppException, match="64KB"):
        validate_plugin_payload(_payload(content="a" * (64 * 1024 + 1)))


@pytest.mark.django_db
def test_content_change_bumps_version_and_audit_snapshot_omits_script():
    created = validate_plugin_payload(_payload())
    plugin = CustomCollectPlugin.objects.create(**created)
    assert plugin.version == 1
    assert plugin.content_checksum.startswith("sha256:")
    assert "content" not in plugin.audit_snapshot()
    assert SCRIPT not in str(plugin.audit_snapshot())

    updated = validate_plugin_payload(_payload(content=SCRIPT + "\n"), instance=plugin)
    assert updated["version"] == 2
    assert updated["content_checksum"] != plugin.content_checksum


@pytest.mark.django_db
def test_referenced_plugin_locks_model_os_and_cannot_delete():
    plugin = CustomCollectPlugin.objects.create(**validate_plugin_payload(_payload()))
    CollectModels.objects.create(
        name="host-custom",
        model_id="host",
        driver_type="job",
        task_type="custom_script",
        cycle_value_type="cycle",
        params={"custom_plugin_pk": plugin.id},
    )
    with pytest.raises(BaseAppException, match="操作系统"):
        validate_plugin_payload(_payload(os_type="windows", shell="powershell"), instance=plugin)
    with pytest.raises(BaseAppException, match="目标模型"):
        validate_plugin_payload(_payload(model_id="nginx"), instance=plugin)
    with pytest.raises(BaseAppException, match="引用"):
        ensure_deletable(plugin)
    with pytest.raises(BaseAppException, match="自定义采集插件"):
        ensure_model_deletable("host")
    ensure_model_deletable("nginx")


@pytest.mark.django_db
def test_serializer_persists_checksum_without_accepting_client_version(monkeypatch):
    monkeypatch.setattr("apps.core.utils.serializers.User.objects.filter", lambda *args, **kwargs: SimpleNamespace(values=lambda *a, **k: []))
    serializer = CustomCollectPluginSerializer(data=_payload(version=99, content_checksum="sha256:forged"), context={"request": _request()})
    assert serializer.is_valid(), serializer.errors
    plugin = serializer.save()
    assert plugin.version == 1
    assert plugin.content_checksum != "sha256:forged"
    assert not ChangeRecord.objects.filter(message__contains=SCRIPT).exists()


@pytest.mark.django_db
def test_serializer_rejects_invalid_plugin(monkeypatch):
    monkeypatch.setattr("apps.core.utils.serializers.User.objects.filter", lambda *args, **kwargs: SimpleNamespace(values=lambda *a, **k: []))
    serializer = CustomCollectPluginSerializer(data=_payload(plugin_id="a"), context={"request": _request()})
    with pytest.raises(ValidationError):
        serializer.is_valid(raise_exception=True)


def _list_user():
    return SimpleNamespace(
        username="alice",
        domain="domain.com",
        is_superuser=True,
        is_active=True,
        is_authenticated=True,
        locale="en",
        group_list=[{"id": 1, "name": "org-a"}],
        permission={"cmdb": {"auto_collection-View", "auto_collection-Delete"}},
        roles=["admin"],
    )


def _create_plugin(index, *, team=None):
    created = validate_plugin_payload(
        _payload(
            name=f"列表插件{index}",
            plugin_id=f"custom_list_{index:02d}",
            team=team or [1],
        )
    )
    return CustomCollectPlugin.objects.create(**created)


def _reference_plugin(plugin, task_index):
    CollectModels.objects.create(
        name=f"list-task-{plugin.id}-{task_index}",
        model_id="host",
        driver_type="job",
        task_type="custom_script",
        cycle_value_type="cycle",
        params={"custom_plugin_pk": plugin.id},
    )


def _plugin_request(method, path, user):
    request = getattr(APIRequestFactory(), method)(path)
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _collect_model_count_queries(captured):
    table = CollectModels._meta.db_table.lower()
    matched = []
    for query in captured:
        sql = " ".join(query["sql"].lower().split())
        if table in sql and "count(" in sql:
            matched.append(sql)
    return matched


def _assert_list_counts(items, expected):
    assert [item["id"] for item in items] == sorted(expected, reverse=True)
    for item in items:
        assert "content" not in item
        assert item["reference_count"] == expected[item["id"]]
        assert item["reference_count"] == reference_count(item["id"])


@pytest.mark.django_db
def test_list_reference_count_queries_stay_flat_for_one_twenty_and_fifty():
    """列表引用数与单插件 COUNT 口径一致，CollectModels COUNT 不随条数增加。"""
    user = _list_user()
    outside = _create_plugin(0, team=[2])
    primary = _create_plugin(1)
    for task_index in range(3):
        _reference_plugin(primary, task_index)
    expected = {primary.id: 3}
    view = CustomCollectPluginViewSet.as_view({"get": "list"})

    def measure(size):
        request = _plugin_request("get", "/api/v1/cmdb/api/custom_collect_plugin/", user)
        with CaptureQueriesContext(connection) as captured:
            response = view(request)
        assert response.status_code == 200
        assert isinstance(response.data, list)
        assert len(response.data) == size
        assert outside.id not in {item["id"] for item in response.data}
        _assert_list_counts(response.data, expected)
        return len(_collect_model_count_queries(captured.captured_queries))

    counts = {1: measure(1)}
    for index in range(2, 21):
        plugin = _create_plugin(index)
        expected[plugin.id] = 0
    counts[20] = measure(20)
    for index in range(21, 51):
        plugin = _create_plugin(index)
        expected[plugin.id] = 0
    counts[50] = measure(50)

    assert 0 in expected.values()
    assert counts[1] == counts[20] == counts[50]
    assert counts[50] < 50

    page_request = _plugin_request("get", "/api/v1/cmdb/api/custom_collect_plugin/?page_size=2", user)
    page = view(page_request)
    assert page.status_code == 200
    assert page.data["count"] == 50
    assert len(page.data["items"]) == 2
    for item in page.data["items"]:
        assert item["reference_count"] == expected[item["id"]]
        assert "content" not in item

    unbounded = view(_plugin_request("get", "/api/v1/cmdb/api/custom_collect_plugin/", user))
    assert isinstance(unbounded.data, list)
    assert len(unbounded.data) == 50

    detail_view = CustomCollectPluginViewSet.as_view({"get": "retrieve"})
    detail_request = _plugin_request("get", f"/api/v1/cmdb/api/custom_collect_plugin/{primary.id}/", user)
    with CaptureQueriesContext(connection) as detail_captured:
        detail = detail_view(detail_request, pk=primary.id)
    assert detail.status_code == 200
    assert detail.data["reference_count"] == 3
    assert detail.data["content"]
    assert len(_collect_model_count_queries(detail_captured.captured_queries)) == 1

    destroy_view = CustomCollectPluginViewSet.as_view({"delete": "destroy"})
    destroy_request = _plugin_request("delete", f"/api/v1/cmdb/api/custom_collect_plugin/{primary.id}/", user)
    destroyed = destroy_view(destroy_request, pk=primary.id)
    assert destroyed.status_code == 400
    assert CustomCollectPlugin.objects.filter(id=primary.id).exists()
