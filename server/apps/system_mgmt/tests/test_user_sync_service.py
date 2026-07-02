from datetime import timedelta
from types import SimpleNamespace
import time
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.system_mgmt.models import Group, IntegrationInstance, User, UserSyncRun, UserSyncRunStatusChoices, UserSyncSource, UserSyncTriggerModeChoices
from apps.system_mgmt.providers.adapters import feishu as feishu_adapter
from apps.system_mgmt.providers.adapters.feishu import FeishuUserSyncAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.serializers.user_sync_source_serializer import UserSyncSourceSerializer
from apps.system_mgmt.services import user_sync_service as user_sync_service_module
from apps.system_mgmt.services.user_sync_service import (
    detect_root_group_name_conflicts,
    execute_user_sync,
    get_user_sync_business_value,
    preview_user_sync,
)


@pytest.fixture(autouse=True)
def clear_feishu_token_cache():
    feishu_adapter._FEISHU_TENANT_TOKEN_CACHE.clear()
    yield
    feishu_adapter._FEISHU_TENANT_TOKEN_CACHE.clear()


@pytest.fixture
def ready_integration_instance(db):
    return IntegrationInstance.objects.create(
        name="feishu-sync",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready", "login_auth": "pending_verification", "im_notification": "pending_verification"},
        config={"app_id": "cli_xxx", "app_secret": "plain-secret"},
    )


def test_user_sync_source_model_does_not_expose_exploration_fields():
    field_names = {field.name for field in UserSyncSource._meta.fields}

    assert "address_book_app" not in field_names
    assert "organization_sync_mode" not in field_names
    assert "user_filter_rule" not in field_names


def test_user_sync_source_model_keeps_provider_business_params_in_business_config_only():
    field_names = {field.name for field in UserSyncSource._meta.fields}

    assert "sync_scope" not in field_names
    assert "root_department_id" not in field_names


@pytest.mark.django_db
def test_user_sync_source_serializer_rejects_conflicting_root_group_name(ready_integration_instance):
    Group.objects.create(name="Feishu Root", parent_id=0)

    serializer = UserSyncSourceSerializer(
        data={
            "name": "source-a",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "Feishu Root",
            "business_config": {"root_department_id": "0"},
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    assert serializer.is_valid() is False
    assert "root_group_name" in serializer.errors


@pytest.mark.django_db
def test_create_source_rejects_existing_root_group_name_in_active_source(ready_integration_instance):
    UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root A",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    serializer = UserSyncSourceSerializer(
        data={
            "name": "source-b",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "Root A",
            "business_config": {"root_department_id": "0"},
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    assert serializer.is_valid() is False
    assert "root_group_name" in serializer.errors


@pytest.mark.django_db
def test_historical_duplicate_root_group_sources_are_reported_but_not_auto_repaired(ready_integration_instance):
    UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Dup Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )
    UserSyncSource.objects.create(
        name="source-b",
        integration_instance=ready_integration_instance,
        enabled=False,
        root_group_name="Dup Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    conflicts = detect_root_group_name_conflicts()

    assert "Dup Root" in conflicts
    assert len(conflicts["Dup Root"]) == 2

@pytest.mark.django_db
def test_user_sync_source_records_collection_returns_paginated_runs(
    api_client, authenticated_user, ready_integration_instance
):
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    api_client.cookies["current_team"] = "1"

    source_a = UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root A",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )
    source_b = UserSyncSource.objects.create(
        name="source-b",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root B",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    oldest_run = UserSyncRun.objects.create(
        source=source_a,
        status=UserSyncRunStatusChoices.SUCCESS,
        started_at=timezone.now() - timedelta(hours=2),
    )
    middle_run = UserSyncRun.objects.create(
        source=source_b,
        status=UserSyncRunStatusChoices.FAILED,
        started_at=timezone.now() - timedelta(hours=1),
    )
    newest_run = UserSyncRun.objects.create(
        source=source_a,
        status=UserSyncRunStatusChoices.RUNNING,
        started_at=timezone.now() - timedelta(minutes=10),
    )

    response = api_client.get(
        "/api/v1/system_mgmt/user_sync_source/records/",
        {"page": 1, "page_size": 2},
    )

    assert response.status_code == 200
    assert response.data["count"] == 3
    assert [item["id"] for item in response.data["items"]] == [newest_run.id, middle_run.id]
    assert response.data["items"][0]["source_name"] == source_a.name
    assert response.data["items"][1]["source_name"] == source_b.name
    assert response.data["items"][0]["started_at"] > response.data["items"][1]["started_at"]
    assert oldest_run.id not in [item["id"] for item in response.data["items"]]


@pytest.mark.django_db
def test_execute_user_sync_creates_run_groups_and_users(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Feishu Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [
                {"id": "dept-a", "parent_id": "0", "name": "Dept A"},
                {"id": "dept-b", "parent_id": "dept-a", "name": "Dept B"},
            ],
            "user_list": [
                {
                    "user_id": "ou_user_1",
                    "name": "User One",
                    "email": "user1@example.com",
                    "mobile": "13800000000",
                    "department_ids": ["dept-b"],
                }
            ],
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_user_sync(source.id)

    assert result["result"] is True

    run = UserSyncRun.objects.get(source=source)
    assert run.status == UserSyncRunStatusChoices.SUCCESS
    assert run.synced_user_count == 1
    assert run.synced_group_count == 2

    root_group = Group.objects.get(name="Feishu Root", parent_id=0)
    leaf_group = Group.objects.get(name="Dept B")
    assert root_group.sync_source_id == source.id
    assert leaf_group.sync_source_id == source.id

    user = User.objects.get(username="ou_user_1", domain="domain.com")
    assert user.sync_source_id == source.id
    assert user.group_list == [leaf_group.id]
    assert user.email == "user1@example.com"


# ---------------------------------------------------------------------------
# Task 2: business_config helper
# ---------------------------------------------------------------------------


def test_get_user_sync_business_value_prefers_business_config():
    """business_config key is the canonical source of provider business parameters."""
    source = SimpleNamespace(business_config={"root_department_id": "dept-biz"})
    assert get_user_sync_business_value(source, "root_department_id", "0") == "dept-biz"


def test_get_user_sync_business_value_returns_default_when_both_absent():
    source = SimpleNamespace(business_config={})
    assert get_user_sync_business_value(source, "root_department_id", "fallback") == "fallback"


def test_get_user_sync_business_value_handles_none_business_config():
    source = SimpleNamespace(business_config=None)
    assert get_user_sync_business_value(source, "root_department_id", "0") == "0"


def test_feishu_user_sync_uses_find_by_department_endpoint():
    class DummyResponse:
        def __init__(self, payload, status_code=200, headers=None):
            self._payload = payload
            self.status_code = status_code
            self.headers = headers or {}

        def json(self):
            return self._payload

    requested_urls = []

    def fake_post(*args, **kwargs):
        return DummyResponse({"code": 0, "tenant_access_token": "tenant-token"})

    def fake_get(url, *args, **kwargs):
        requested_urls.append(url)
        if "departments/" in url:
            return DummyResponse({"code": 0, "data": {"items": [], "has_more": False}})
        return DummyResponse({"code": 0, "data": {"items": [], "has_more": False}})

    source = SimpleNamespace(name="preview-source", business_config={"root_department_id": "0"})

    with patch("apps.system_mgmt.providers.adapters.feishu.requests.post", side_effect=fake_post), patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=fake_get
    ):
        result = FeishuUserSyncAdapter.sync_users({"app_id": "cli_xxx", "app_secret": "secret"}, "feishu", "user_sync", source=source)

    assert result.success is True
    assert any(url.endswith("/contact/v3/users/find_by_department") for url in requested_urls)


def test_feishu_list_departments_returns_all_node_and_children():
    class DummyResponse:
        def __init__(self, payload, status_code=200, headers=None):
            self._payload = payload
            self.status_code = status_code
            self.headers = headers or {}

        def json(self):
            return self._payload

    requested_params = []

    def fake_post(*args, **kwargs):
        return DummyResponse({"code": 0, "tenant_access_token": "tenant-token"})

    def fake_get(url, *args, **kwargs):
        requested_params.append(kwargs.get("params") or {})
        return DummyResponse(
            {
                "code": 0,
                "data": {
                    "items": [
                        {"open_department_id": "dept-a", "parent_department_id": "0", "name": "Dept A"},
                        {"open_department_id": "dept-b", "parent_department_id": "dept-a", "name": "Dept B"},
                    ],
                    "has_more": False,
                },
            }
        )

    with patch("apps.system_mgmt.providers.adapters.feishu.requests.post", side_effect=fake_post), patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=fake_get
    ):
        result = FeishuUserSyncAdapter.list_departments(
            {"app_id": "cli_xxx", "app_secret": "secret"},
            "feishu",
            "user_sync",
            business_config={"department_id_type": "open_department_id"},
        )

    assert result.success is True
    assert result.payload["all_department_id"] == "0"
    assert result.payload["items"][0]["is_all"] is True
    assert result.payload["items"][0]["children"][0]["id"] == "dept-a"
    assert result.payload["items"][0]["children"][0]["children"][0]["id"] == "dept-b"
    assert requested_params[0]["department_id_type"] == "open_department_id"


def test_feishu_user_sync_uses_requested_department_id_type_for_group_ids():
    class DummyResponse:
        def __init__(self, payload, status_code=200, headers=None):
            self._payload = payload
            self.status_code = status_code
            self.headers = headers or {}

        def json(self):
            return self._payload

    def fake_post(*args, **kwargs):
        return DummyResponse({"code": 0, "tenant_access_token": "tenant-token"})

    def fake_get(url, *args, **kwargs):
        if "departments/" in url:
            return DummyResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "department_id": "internal-dept-a",
                                "open_department_id": "open-dept-a",
                                "parent_department_id": "0",
                                "name": "Dept A",
                            }
                        ],
                        "has_more": False,
                    },
                }
            )
        return DummyResponse({"code": 0, "data": {"items": [], "has_more": False}})

    source = SimpleNamespace(
        name="typed-source",
        business_config={"root_department_id": "0", "department_id_type": "open_department_id"},
    )

    with patch("apps.system_mgmt.providers.adapters.feishu.requests.post", side_effect=fake_post), patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=fake_get
    ):
        result = FeishuUserSyncAdapter.sync_users(
            {"app_id": "cli_xxx", "app_secret": "secret"},
            "feishu",
            "user_sync",
            source=source,
        )

    assert result.success is True
    assert result.payload["group_list"][0]["id"] == "open-dept-a"


def test_feishu_user_sync_defaults_to_fetch_child_true():
    class DummyResponse:
        def __init__(self, payload, status_code=200, headers=None):
            self._payload = payload
            self.status_code = status_code
            self.headers = headers or {}

        def json(self):
            return self._payload

    requested_params = []

    def fake_post(*args, **kwargs):
        return DummyResponse({"code": 0, "tenant_access_token": "tenant-token"})

    def fake_get(url, *args, **kwargs):
        requested_params.append(kwargs.get("params") or {})
        return DummyResponse({"code": 0, "data": {"items": [], "has_more": False}})

    source = SimpleNamespace(name="default-fetch-child-source", business_config={"root_department_id": "0"})

    with patch("apps.system_mgmt.providers.adapters.feishu.requests.post", side_effect=fake_post), patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=fake_get
    ):
        result = FeishuUserSyncAdapter.sync_users(
            {"app_id": "cli_xxx", "app_secret": "secret"},
            "feishu",
            "user_sync",
            source=source,
        )

    assert result.success is True
    assert requested_params[0]["fetch_child"] == "true"
    assert requested_params[1]["fetch_child"] == "true"


@pytest.mark.django_db
def test_feishu_user_sync_serializer_drops_deprecated_fetch_child_config(ready_integration_instance):
    payload = CapabilityExecutionResult.success_result(
        "departments loaded",
        payload={
            "items": [{"id": "__all__", "name": "全部部门", "parent_id": None, "children": []}],
            "all_department_id": "0",
            "selected_id": "__all__",
            "selection_missing": False,
        },
    )
    serializer = UserSyncSourceSerializer(
        data={
            "name": "source-with-old-fetch-child",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "Feishu Root",
            "business_config": {
                "root_department_id": "0",
                "department_id_type": "open_department_id",
                "user_id_type": "open_id",
                "fetch_child": False,
            },
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute", return_value=payload):
        assert serializer.is_valid(), serializer.errors

    assert "fetch_child" not in serializer.validated_data["business_config"]


def test_feishu_list_departments_marks_missing_selection():
    class DummyResponse:
        def __init__(self, payload, status_code=200, headers=None):
            self._payload = payload
            self.status_code = status_code
            self.headers = headers or {}

        def json(self):
            return self._payload

    def fake_post(*args, **kwargs):
        return DummyResponse({"code": 0, "tenant_access_token": "tenant-token"})

    def fake_get(url, *args, **kwargs):
        return DummyResponse({"code": 0, "data": {"items": [], "has_more": False}})

    with patch("apps.system_mgmt.providers.adapters.feishu.requests.post", side_effect=fake_post), patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=fake_get
    ):
        result = FeishuUserSyncAdapter.list_departments(
            {"app_id": "cli_xxx", "app_secret": "secret"},
            "feishu",
            "user_sync",
            business_config={"root_department_id": "stale-dept", "department_id_type": "department_id"},
        )

    assert result.success is True
    assert result.payload["selected_id"] == ""
    assert result.payload["selection_missing"] is True


@pytest.mark.django_db
def test_user_sync_department_options_returns_all_selection_for_real_root(
    api_client, authenticated_user, ready_integration_instance
):
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    api_client.cookies["current_team"] = "1"

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "items": [{"id": "__all__", "name": "全部部门", "parent_id": None, "children": [], "selectable": True, "is_all": True}],
            "all_department_id": "0",
            "selected_id": "__all__",
            "selection_missing": False,
        },
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute", return_value=payload) as mock_execute:
        response = api_client.get(
            "/api/v1/system_mgmt/user_sync_source/department_options/",
            {"integration_instance": ready_integration_instance.id, "current_root_department_id": "0", "department_id_type": "department_id"},
        )

    assert response.status_code == 200
    assert response.data["selected_id"] == "__all__"
    assert response.data["selection_missing"] is False
    assert mock_execute.call_args.kwargs["business_config"]["department_id_type"] == "department_id"


def test_feishu_user_sync_reuses_cached_token_when_not_expiring():
    class DummyResponse:
        def __init__(self, payload, status_code=200, headers=None):
            self._payload = payload
            self.status_code = status_code
            self.headers = headers or {}

        def json(self):
            return self._payload

    token_calls = []
    auth_headers = []

    def fake_post(*args, **kwargs):
        token_calls.append(kwargs.get("json"))
        return DummyResponse({"code": 0, "tenant_access_token": "tenant-token-1", "expire": 7200})

    def fake_get(url, *args, **kwargs):
        auth_headers.append(kwargs["headers"]["Authorization"])
        return DummyResponse({"code": 0, "data": {"items": [], "has_more": False}})

    source = SimpleNamespace(name="cache-source", business_config={"root_department_id": "0"})

    with patch("apps.system_mgmt.providers.adapters.feishu.requests.post", side_effect=fake_post), patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=fake_get
    ):
        first_result = FeishuUserSyncAdapter.sync_users({"app_id": "cli_xxx", "app_secret": "secret"}, "feishu", "user_sync", source=source)
        second_result = FeishuUserSyncAdapter.sync_users({"app_id": "cli_xxx", "app_secret": "secret"}, "feishu", "user_sync", source=source)

    assert first_result.success is True
    assert second_result.success is True
    assert len(token_calls) == 1
    assert auth_headers == ["Bearer tenant-token-1", "Bearer tenant-token-1", "Bearer tenant-token-1", "Bearer tenant-token-1"]


def test_feishu_user_sync_refreshes_token_once_after_auth_failure():
    class DummyResponse:
        def __init__(self, payload, status_code=200, headers=None):
            self._payload = payload
            self.status_code = status_code
            self.headers = headers or {}

        def json(self):
            return self._payload

    token_calls = []
    user_request_headers = []

    def fake_post(*args, **kwargs):
        token_calls.append(kwargs.get("json"))
        token_index = len(token_calls)
        return DummyResponse({"code": 0, "tenant_access_token": f"tenant-token-{token_index}", "expire": 7200})

    def fake_get(url, *args, **kwargs):
        authorization = kwargs["headers"]["Authorization"]
        if "departments/" in url:
            return DummyResponse({"code": 0, "data": {"items": [], "has_more": False}})

        user_request_headers.append(authorization)
        if len(user_request_headers) == 1:
            return DummyResponse({"code": 99991663, "msg": "tenant_access_token expired"}, status_code=401, headers={"X-Tt-Logid": "req-1"})
        return DummyResponse({"code": 0, "data": {"items": [], "has_more": False}}, headers={"X-Tt-Logid": "req-2"})

    source = SimpleNamespace(name="refresh-source", business_config={"root_department_id": "0"})

    with patch("apps.system_mgmt.providers.adapters.feishu.requests.post", side_effect=fake_post), patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=fake_get
    ):
        result = FeishuUserSyncAdapter.sync_users({"app_id": "cli_xxx", "app_secret": "secret"}, "feishu", "user_sync", source=source)

    assert result.success is True
    assert len(token_calls) == 2
    assert user_request_headers == ["Bearer tenant-token-1", "Bearer tenant-token-2"]


def test_feishu_user_sync_pre_refreshes_expiring_cached_token():
    class DummyResponse:
        def __init__(self, payload, status_code=200, headers=None):
            self._payload = payload
            self.status_code = status_code
            self.headers = headers or {}

        def json(self):
            return self._payload

    token_calls = []
    auth_headers = []
    cache_key = feishu_adapter._get_feishu_token_cache_key({"app_id": "cli_xxx", "app_secret": "secret"})
    feishu_adapter._FEISHU_TENANT_TOKEN_CACHE[cache_key] = {
        "token": "stale-token",
        "expires_at": time.time() + 60,
    }

    def fake_post(*args, **kwargs):
        token_calls.append(kwargs.get("json"))
        return DummyResponse({"code": 0, "tenant_access_token": "fresh-token", "expire": 7200})

    def fake_get(url, *args, **kwargs):
        auth_headers.append(kwargs["headers"]["Authorization"])
        return DummyResponse({"code": 0, "data": {"items": [], "has_more": False}})

    source = SimpleNamespace(name="pre-refresh-source", business_config={"root_department_id": "0"})

    with patch("apps.system_mgmt.providers.adapters.feishu.requests.post", side_effect=fake_post), patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get", side_effect=fake_get
    ):
        result = FeishuUserSyncAdapter.sync_users({"app_id": "cli_xxx", "app_secret": "secret"}, "feishu", "user_sync", source=source)

    assert result.success is True
    assert len(token_calls) == 1
    assert auth_headers == ["Bearer fresh-token", "Bearer fresh-token"]


# ---------------------------------------------------------------------------
# Task 2: serializer 鈥?business_config
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_serializer_accepts_business_config_without_mirroring_legacy_columns(ready_integration_instance):
    """Supplying business_config should keep provider parameters inside business_config only."""
    serializer = UserSyncSourceSerializer(
        data={
            "name": "source-bc",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "BC Root",
            "business_config": {
                "root_department_id": "dept-99",
            },
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "all_department_id": "0",
            "items": [
                {"id": "__all__", "name": "全部部门", "parent_id": None, "children": []},
                {"id": "dept-99", "name": "Dept 99", "parent_id": "__all__", "children": []},
            ],
        },
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute", return_value=payload) as mock_execute:
        assert serializer.is_valid(), serializer.errors

    mock_execute.assert_called_once()
    validated = serializer.validated_data
    assert validated["business_config"]["root_department_id"] == "dept-99"
    assert "sync_scope" not in validated
    assert "root_department_id" not in validated


@pytest.mark.django_db
def test_user_sync_source_builds_daily_schedule_spec(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="daily-source",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Daily Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={"mode": "daily", "time": "02:15", "timezone": "Asia/Shanghai"},
    )

    assert source.build_schedule_spec() == {
        "kind": "crontab",
        "minute": "15",
        "hour": "2",
        "day_of_week": "*",
        "day_of_month": "*",
        "month_of_year": "*",
        "timezone": "Asia/Shanghai",
    }


@pytest.mark.django_db
def test_user_sync_source_builds_weekly_schedule_spec(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="weekly-source",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Weekly Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={
            "mode": "weekly",
            "time": "03:20",
            "weekdays": [1, 3, 5],
            "timezone": "Asia/Shanghai",
        },
    )

    assert source.build_schedule_spec() == {
        "kind": "crontab",
        "minute": "20",
        "hour": "3",
        "day_of_week": "1,3,5",
        "day_of_month": "*",
        "month_of_year": "*",
        "timezone": "Asia/Shanghai",
    }


@pytest.mark.django_db
def test_user_sync_source_builds_interval_hours_schedule_spec_from_midnight_alignment(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="interval-source",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Interval Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={"mode": "interval_hours", "interval_hours": 6, "timezone": "Asia/Shanghai"},
    )

    assert source.build_schedule_spec() == {
        "kind": "crontab",
        "minute": "0",
        "hour": "*/6",
        "day_of_week": "*",
        "day_of_month": "*",
        "month_of_year": "*",
        "timezone": "Asia/Shanghai",
    }


@pytest.mark.django_db
def test_serializer_rejects_legacy_schedule_payload(ready_integration_instance):
    with patch(
        "apps.system_mgmt.serializers.user_sync_source_serializer.get_user_sync_root_department_input_mode",
        return_value="manual_input",
    ):
        serializer = UserSyncSourceSerializer(
            data={
                "name": "source-invalid-schedule",
                "integration_instance": ready_integration_instance.id,
                "enabled": True,
                "root_group_name": "Invalid Schedule Root",
                "business_config": {"root_department_id": "0"},
                "field_mapping": {},
                "schedule_config": {"enabled": True, "sync_time": "25:00"},
            }
        )

        assert serializer.is_valid() is False

    assert "schedule_config" in serializer.errors

@pytest.mark.django_db
def test_serializer_accepts_weekly_schedule_config(ready_integration_instance):
    with patch(
        "apps.system_mgmt.serializers.user_sync_source_serializer.get_user_sync_root_department_input_mode",
        return_value="manual_input",
    ):
        serializer = UserSyncSourceSerializer(
            data={
                "name": "source-weekly-schedule",
                "integration_instance": ready_integration_instance.id,
                "enabled": True,
                "root_group_name": "Weekly Schedule Root",
                "business_config": {"root_department_id": "0"},
                "field_mapping": {},
                "schedule_config": {
                    "mode": "weekly",
                    "time": "02:00",
                    "weekdays": [1, 3, 5],
                    "timezone": "Asia/Shanghai",
                },
            }
        )

        assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_serializer_rejects_unknown_user_sync_field_mapping_key(ready_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "source-invalid-field-mapping-key",
            "integration_instance": ready_integration_instance.id,
            "enabled": True,
            "root_group_name": "Invalid Mapping Root",
            "business_config": {"root_department_id": "0"},
            "field_mapping": {"nickname": "name"},
            "schedule_config": {},
        }
    )

    assert serializer.is_valid() is False
    assert "field_mapping" in serializer.errors


@pytest.mark.django_db
def test_serializer_rejects_user_sync_field_mapping_not_declared_by_manifest(ready_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "source-invalid-field-mapping-value",
            "integration_instance": ready_integration_instance.id,
            "enabled": True,
            "root_group_name": "Invalid Mapping Value Root",
            "business_config": {"root_department_id": "0"},
            "field_mapping": {"username": "private_token"},
            "schedule_config": {},
        }
    )

    assert serializer.is_valid() is False
    assert "field_mapping" in serializer.errors


@pytest.mark.django_db
def test_serializer_existing_source_preview_does_not_reject_own_root_group(ready_integration_instance):
    """Serializer with instance set should not reject its own root group name on preview."""
    source = UserSyncSource.objects.create(
        name="source-p",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Preview Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )
    # Simulate the root group being created by a prior sync
    Group.objects.create(name="Preview Root", parent_id=0, sync_source=source)

    serializer = UserSyncSourceSerializer(
        instance=source,
        data={"business_config": {"root_department_id": "0"}},
        partial=True,
    )
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "all_department_id": "0",
            "items": [
                {"id": "__all__", "name": "全部部门", "parent_id": None, "children": []},
            ],
        },
    )
    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute", return_value=payload):
        assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_serializer_normalizes_all_department_selection_and_passes_department_id_type(ready_integration_instance):
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "all_department_id": "dept-all",
            "items": [
                {"id": "__all__", "name": "鍏ㄩ儴閮ㄩ棬", "parent_id": None, "children": []},
                {"id": "dept-all", "name": "Dept All", "parent_id": "__all__", "children": []},
                {"id": "dept-a", "name": "Dept A", "parent_id": "dept-all", "children": []},
            ],
        },
    )

    serializer = UserSyncSourceSerializer(
        data={
            "name": "source-all",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "All Root",
            "business_config": {
                "root_department_id": "__all__",
                "department_id_type": "department_id",
            },
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute", return_value=payload) as mock_execute:
        assert serializer.is_valid(), serializer.errors

    mock_execute.assert_called_once()
    call_kwargs = mock_execute.call_args.kwargs
    assert call_kwargs["operation"] == "list_departments"
    assert call_kwargs["business_config"]["department_id_type"] == "department_id"
    assert serializer.validated_data["business_config"]["root_department_id"] == "dept-all"


@pytest.mark.django_db
def test_serializer_rejects_stale_root_department_selection(ready_integration_instance):
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "all_department_id": "dept-all",
            "items": [
                {"id": "__all__", "name": "全部部门", "parent_id": None, "children": []},
                {"id": "dept-all", "name": "Dept All", "parent_id": "__all__", "children": []},
            ],
        },
    )

    serializer = UserSyncSourceSerializer(
        data={
            "name": "source-stale",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "Stale Root",
            "business_config": {
                "root_department_id": "stale-dept",
                "department_id_type": "department_id",
            },
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute", return_value=payload):
        assert serializer.is_valid() is False

    assert "business_config" in serializer.errors


@pytest.mark.django_db
def test_serializer_requires_root_department_selection(ready_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "source-missing-root",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "Missing Root",
            "business_config": {
                "department_id_type": "department_id",
            },
            "field_mapping": {},
            "schedule_config": {},
        }
    )

    assert serializer.is_valid() is False
    assert "business_config" in serializer.errors


def test_normalize_root_department_selection_converts_all_marker():
    payload = {"all_department_id": "dept-all"}

    assert user_sync_service_module.normalize_root_department_selection("__all__", payload) == "dept-all"


def test_flatten_department_ids_collects_nested_tree_ids():
    items = [
        {"id": "__all__", "children": [{"id": "dept-all", "children": [{"id": "dept-a", "children": []}]}]},
    ]

    assert user_sync_service_module.flatten_department_ids(items) == {"__all__", "dept-all", "dept-a"}


# ---------------------------------------------------------------------------
# Task 2: preview service
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_source(ready_integration_instance, db):
    return UserSyncSource.objects.create(
        name="source-preview",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Preview Sync Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )


@pytest.mark.django_db
def test_preview_returns_estimated_counts_without_creating_run(sync_source):
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [
                {"id": "dept-a", "parent_id": "0", "name": "Dept A"},
            ],
            "user_list": [
                {"user_id": "ou_1", "name": "User One", "email": "", "mobile": "", "department_ids": ["dept-a"]},
                {"user_id": "ou_2", "name": "User Two", "email": "", "mobile": "", "department_ids": ["dept-a"]},
            ],
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        result = preview_user_sync(sync_source)

    assert result["result"] is True
    assert result["data"]["estimated_user_count"] == 2
    assert result["data"]["estimated_group_count"] == 1
    # No UserSyncRun should be created
    assert UserSyncRun.objects.filter(source=sync_source).count() == 0


@pytest.mark.django_db
def test_preview_failure_returns_error_without_creating_run(sync_source):
    failed_result = CapabilityExecutionResult.failed_result(
        "Token request timed out",
        code="provider.timeout",
        retryable=True,
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=failed_result):
        result = preview_user_sync(sync_source)

    assert result["result"] is False
    assert "timed out" in result["message"]
    assert UserSyncRun.objects.filter(source=sync_source).count() == 0


@pytest.mark.django_db
def test_execute_user_sync_with_business_config_uses_correct_root_department(ready_integration_instance):
    """Service must read root_department_id from business_config when the legacy column differs."""
    source = UserSyncSource.objects.create(
        name="source-biz",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Biz Root",
        business_config={"root_department_id": "biz-dept"},
        field_mapping={},
        schedule_config={},
    )

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "biz-dept", "parent_id": "0", "name": "Biz Dept"}],
            "user_list": [
                {
                    "user_id": "ou_biz",
                    "name": "Biz User",
                    "email": "",
                    "mobile": "",
                    "department_ids": ["biz-dept"],
                }
            ],
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_user_sync(source.id)

    assert result["result"] is True
    run = UserSyncRun.objects.get(source=source)
    assert run.synced_user_count == 1



@pytest.mark.django_db
def test_execute_user_sync_marks_partial_when_one_user_conflicts_but_others_sync(ready_integration_instance):
    source_a = UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root A",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )
    source_b = UserSyncSource.objects.create(
        name="source-b",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root B",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    payload_a = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "dept-a", "parent_id": "0", "name": "Dept A"}],
            "user_list": [
                {
                    "user_id": "shared_user",
                    "name": "Shared User",
                    "email": "shared@example.com",
                    "mobile": "13800000001",
                    "department_ids": ["dept-a"],
                }
            ],
        },
    )
    payload_b = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "dept-b", "parent_id": "0", "name": "Dept B"}],
            "user_list": [
                {
                    "user_id": "shared_user",
                    "name": "Shared User",
                    "email": "shared@example.com",
                    "mobile": "13800000001",
                    "department_ids": ["dept-b"],
                },
                {
                    "user_id": "new_user",
                    "name": "New User",
                    "email": "new@example.com",
                    "mobile": "13800000002",
                    "department_ids": ["dept-b"],
                },
            ],
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_a):
        assert execute_user_sync(source_a.id)["result"] is True

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_b):
        result = execute_user_sync(source_b.id)

    assert result["result"] is True
    run = UserSyncRun.objects.get(source=source_b)
    assert run.status == UserSyncRunStatusChoices.PARTIAL
    assert run.synced_user_count == 1
    assert run.payload["conflict_usernames"] == ["shared_user"]
    assert User.objects.get(username="new_user", domain="domain.com").sync_source_id == source_b.id


@pytest.mark.django_db
def test_execute_user_sync_marks_failed_when_all_users_conflict(ready_integration_instance):
    source_a = UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root A",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )
    source_b = UserSyncSource.objects.create(
        name="source-b",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root B",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    payload_a = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "dept-a", "parent_id": "0", "name": "Dept A"}],
            "user_list": [
                {
                    "user_id": "shared_user",
                    "name": "Shared User",
                    "email": "shared@example.com",
                    "mobile": "13800000001",
                    "department_ids": ["dept-a"],
                }
            ],
        },
    )
    payload_b = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "dept-b", "parent_id": "0", "name": "Dept B"}],
            "user_list": [
                {
                    "user_id": "shared_user",
                    "name": "Shared User",
                    "email": "shared@example.com",
                    "mobile": "13800000001",
                    "department_ids": ["dept-b"],
                }
            ],
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_a):
        assert execute_user_sync(source_a.id)["result"] is True

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_b):
        result = execute_user_sync(source_b.id)

    assert result["result"] is True
    run = UserSyncRun.objects.get(source=source_b)
    assert run.status == UserSyncRunStatusChoices.FAILED
    assert run.synced_user_count == 0
    assert run.payload["conflict_usernames"] == ["shared_user"]
    assert "failed" in run.summary.lower()
    assert User.objects.get(username="shared_user", domain="domain.com").sync_source_id == source_a.id


@pytest.mark.django_db
def test_execute_user_sync_marks_partial_when_user_groups_point_to_another_source(ready_integration_instance):
    source_a = UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root A",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )
    source_b = UserSyncSource.objects.create(
        name="source-b",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root B",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    foreign_root = Group.objects.create(name="Root A", parent_id=0, sync_source=source_a, external_id="user-sync:a:0")
    foreign_dept = Group.objects.create(name="Dept A", parent_id=foreign_root.id, sync_source=source_a, external_id="user-sync:a:dept-a")
    User.objects.create(
        username="shared_user",
        display_name="Shared User",
        email="shared@example.com",
        phone="13800000001",
        password="",
        domain="domain.com",
        disabled=False,
        group_list=[foreign_dept.id],
        sync_source=None,
    )

    payload_b = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "dept-b", "parent_id": "0", "name": "Dept B"}],
            "user_list": [
                {
                    "user_id": "shared_user",
                    "name": "Shared User",
                    "email": "shared@example.com",
                    "mobile": "13800000001",
                    "department_ids": ["dept-b"],
                },
                {
                    "user_id": "new_user_2",
                    "name": "New User 2",
                    "email": "new2@example.com",
                    "mobile": "13800000003",
                    "department_ids": ["dept-b"],
                },
            ],
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_b):
        result = execute_user_sync(source_b.id)

    assert result["result"] is True
    run = UserSyncRun.objects.get(source=source_b)
    assert run.status == UserSyncRunStatusChoices.PARTIAL
    assert run.payload["conflict_usernames"] == ["shared_user"]
    assert User.objects.get(username="new_user_2", domain="domain.com").sync_source_id == source_b.id


@pytest.mark.django_db
def test_execute_user_sync_does_not_claim_existing_unmanaged_platform_user(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root A",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )
    manual_group = Group.objects.create(name="Manual Group", parent_id=0)
    User.objects.create(
        username="manual_user",
        display_name="Manual User",
        email="manual@example.com",
        phone="13800000005",
        password="",
        domain="domain.com",
        disabled=False,
        group_list=[manual_group.id],
        sync_source=None,
    )
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "dept-a", "parent_id": "0", "name": "Dept A"}],
            "user_list": [
                {
                    "user_id": "manual_user",
                    "name": "External Manual User",
                    "email": "external-manual@example.com",
                    "mobile": "13800000006",
                    "department_ids": ["dept-a"],
                }
            ],
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_user_sync(source.id)

    assert result["result"] is True
    user = User.objects.get(username="manual_user", domain="domain.com")
    assert user.sync_source_id is None
    assert user.group_list == [manual_group.id]
    assert user.display_name == "Manual User"
    run = UserSyncRun.objects.get(source=source)
    assert run.status == UserSyncRunStatusChoices.FAILED
    assert run.synced_user_count == 0
    assert run.payload["conflict_usernames"] == ["manual_user"]


@pytest.mark.django_db
def test_reappearing_disabled_user_is_reenabled(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root A",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "dept-a", "parent_id": "0", "name": "Dept A"}],
            "user_list": [
                {
                    "user_id": "alice",
                    "name": "Alice",
                    "email": "alice@example.com",
                    "mobile": "13800000004",
                    "department_ids": ["dept-a"],
                }
            ],
        },
    )

    root_group = Group.objects.create(name="Root A", parent_id=0, sync_source=source, external_id="user-sync:1:0")
    user = User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        phone="13800000004",
        password="",
        domain="domain.com",
        disabled=True,
        group_list=[root_group.id],
        sync_source=source,
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_user_sync(source.id)

    assert result["result"] is True
    user.refresh_from_db()
    assert user.disabled is False


@pytest.mark.django_db
def test_execute_user_sync_marks_failed_when_conflicting_user_is_created_during_bulk_create(ready_integration_instance):
    source_a = UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root A",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )
    source_b = UserSyncSource.objects.create(
        name="source-b",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root B",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    payload_b = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "dept-b", "parent_id": "0", "name": "Dept B"}],
            "user_list": [
                {
                    "user_id": "ou_shared_user",
                    "name": "Shared User",
                    "email": "shared@example.com",
                    "mobile": "13800000001",
                    "department_ids": ["dept-b"],
                }
            ],
        },
    )

    original_bulk_create = User.objects.bulk_create

    def bulk_create_with_race(objs, **kwargs):
        if not User.objects.filter(username="ou_shared_user", domain="domain.com").exists():
            User.objects.create(
                username="ou_shared_user",
                display_name="Shared User",
                email="shared@example.com",
                phone="13800000001",
                password="",
                domain="domain.com",
                disabled=False,
                group_list=[999],
                sync_source=source_a,
            )
        return original_bulk_create(objs, **kwargs)

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_b):
        with patch.object(User.objects, "bulk_create", side_effect=bulk_create_with_race):
            result = execute_user_sync(source_b.id)

    assert result["result"] is True
    run = UserSyncRun.objects.get(source=source_b)
    assert run.status == UserSyncRunStatusChoices.FAILED
    assert run.synced_user_count == 0
    assert run.payload["conflict_usernames"] == ["ou_shared_user"]
    assert Group.objects.filter(sync_source=source_b).count() >= 1


@pytest.mark.django_db
def test_execute_user_sync_marks_failed_when_existing_user_groups_belong_to_another_source(ready_integration_instance):
    source_a = UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root A",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )
    source_b = UserSyncSource.objects.create(
        name="source-b",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root B",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    root_a = Group.objects.create(name="Root A", parent_id=0, sync_source=source_a, external_id="user-sync:a:0")
    dept_a = Group.objects.create(name="Dept A", parent_id=root_a.id, sync_source=source_a, external_id="user-sync:a:dept-a")
    User.objects.create(
        username="ou_shared_user",
        display_name="Shared User",
        email="shared@example.com",
        phone="13800000001",
        password="",
        domain="domain.com",
        disabled=False,
        group_list=[dept_a.id],
        sync_source=None,
    )

    payload_b = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "dept-b", "parent_id": "0", "name": "Dept B"}],
            "user_list": [
                {
                    "user_id": "ou_shared_user",
                    "name": "Shared User",
                    "email": "shared@example.com",
                    "mobile": "13800000001",
                    "department_ids": ["dept-b"],
                }
            ],
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_b):
        result = execute_user_sync(source_b.id)

    assert result["result"] is True
    user = User.objects.get(username="ou_shared_user", domain="domain.com")
    assert user.sync_source_id is None
    assert user.group_list == [dept_a.id]

    run = UserSyncRun.objects.get(source=source_b)
    assert run.status == UserSyncRunStatusChoices.FAILED
    assert run.synced_user_count == 0
    assert run.payload["conflict_usernames"] == ["ou_shared_user"]


@pytest.mark.django_db
def test_scheduled_execution_for_disabled_source_creates_failed_run(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="source-disabled-schedule",
        integration_instance=ready_integration_instance,
        enabled=False,
        root_group_name="Disabled Schedule Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    result = execute_user_sync(source.id, trigger_mode=UserSyncTriggerModeChoices.SCHEDULE)

    assert result["result"] is False
    run = UserSyncRun.objects.get(source=source)
    assert run.trigger_mode == UserSyncTriggerModeChoices.SCHEDULE
    assert run.status == UserSyncRunStatusChoices.FAILED
    assert "disabled" in run.summary.lower()


@pytest.mark.django_db
def test_queued_sync_for_disabled_source_creates_failed_run(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="source-disabled-manual",
        integration_instance=ready_integration_instance,
        enabled=False,
        root_group_name="Disabled Manual Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )

    result = execute_user_sync(source.id)

    assert result["result"] is False
    run = UserSyncRun.objects.get(source=source)
    assert run.status == UserSyncRunStatusChoices.FAILED
    assert "disabled" in run.summary.lower()


@pytest.mark.django_db
def test_user_sync_run_allows_only_one_running_run_per_source(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="source-running-guard",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Running Guard Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )
    UserSyncRun.objects.create(source=source, status=UserSyncRunStatusChoices.RUNNING)

    with pytest.raises(IntegrityError):
        UserSyncRun.objects.create(source=source, status=UserSyncRunStatusChoices.RUNNING)


@pytest.mark.django_db
def test_user_sync_source_periodic_task_args_are_json_serialized(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="source-periodic-json",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Periodic Json Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={"mode": "daily", "time": "03:30", "timezone": "Asia/Shanghai"},
    )

    with patch.object(source, "create_periodic_task_from_spec") as mock_create:
        source.create_sync_periodic_task()

    mock_create.assert_called_once_with(
        {
            "kind": "crontab",
            "minute": "30",
            "hour": "3",
            "day_of_week": "*",
            "day_of_month": "*",
            "month_of_year": "*",
            "timezone": "Asia/Shanghai",
        },
        source.periodic_task_name(),
        f'[{source.id},"{UserSyncTriggerModeChoices.SCHEDULE}"]',
        "apps.system_mgmt.tasks.execute_user_sync_source",
    )
