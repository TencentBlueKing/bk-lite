import time
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError
from django.utils import timezone

from apps.system_mgmt.models import (
    Group,
    IntegrationInstance,
    User,
    UserSyncRun,
    UserSyncRunStatusChoices,
    UserSyncSource,
    UserSyncTriggerModeChoices,
)
from apps.system_mgmt.providers.adapters import feishu as feishu_adapter
from apps.system_mgmt.providers.adapters.feishu import FeishuUserSyncAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.serializers.user_sync_source_serializer import UserSyncSourceSerializer
from apps.system_mgmt.services import user_sync_service as user_sync_service_module
from apps.system_mgmt.services.user_sync_service import (
    _apply_user_sync_payload,
    _sync_groups,
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


@pytest.fixture
def password_init_source_factory(ready_integration_instance):
    def factory(mode=None):
        platform_config = {"password_init": {"mode": mode, "email_channel_id": 7}} if mode else {}
        if mode == "none":
            platform_config = {"password_init": {"mode": mode}}
        return UserSyncSource.objects.create(
            name=f"password-init-{mode or 'legacy'}",
            integration_instance=ready_integration_instance,
            enabled=True,
            root_group_name=f"Password Init {mode or 'Legacy'}",
            business_config={"root_department_id": "0"},
            platform_config=platform_config,
            field_mapping={},
            schedule_config={},
        )

    return factory


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

    # 预先创建 source_a 的同名 user(模拟 race condition:外部已占用)
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

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_b):
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


@pytest.mark.django_db
def test_new_random_user_initializes_password(password_init_source_factory):
    source = password_init_source_factory("random")
    with patch(
        "apps.system_mgmt.services.password_init_service.init_password_for_user",
        return_value={"status": "ok", "reason": None, "raw_password": None},
    ) as init_mock:
        _apply_user_sync_payload(
            source,
            {"user_list": [{"user_id": "alice", "name": "Alice", "email": "alice@example.com"}], "group_list": []},
        )

    init_mock.assert_called_once()
    assert init_mock.call_args[0][1] == "random"


@pytest.mark.django_db
def test_existing_user_skips_password_initialization(password_init_source_factory):
    source = password_init_source_factory("random")
    User.objects.create(username="alice", display_name="Alice", email="alice@example.com", domain="domain.com", group_list=[], sync_source=source)

    with patch("apps.system_mgmt.services.password_init_service.init_password_for_user") as init_mock:
        _apply_user_sync_payload(source, {"user_list": [{"user_id": "alice", "name": "Alice", "email": "a@b.c"}], "group_list": []})

    init_mock.assert_not_called()


@pytest.mark.django_db
def test_none_mode_does_not_enqueue_initial_password_email(password_init_source_factory):
    source = password_init_source_factory("none")
    with patch("apps.system_mgmt.services.password_init_service.send_initial_password_email.delay") as delay:
        _apply_user_sync_payload(
            source,
            {"user_list": [{"user_id": "alice-none", "name": "Alice", "email": "a@b.c"}], "group_list": []},
        )

    delay.assert_not_called()
    assert User.objects.get(username="alice-none", domain="domain.com").temporary_pwd is False


@pytest.mark.django_db
def test_legacy_source_skips_password_initialization(password_init_source_factory):
    source = password_init_source_factory()
    with patch("apps.system_mgmt.services.password_init_service.init_password_for_user") as init_mock:
        _apply_user_sync_payload(
            source,
            {"user_list": [{"user_id": "alice-legacy", "name": "Alice", "email": "a@b.c"}], "group_list": []},
        )

    init_mock.assert_not_called()


@pytest.mark.django_db
def test_password_initialization_failure_creates_non_login_user(password_init_source_factory):
    source = password_init_source_factory("random")
    with patch(
        "apps.system_mgmt.services.password_init_service.init_password_for_user",
        return_value={"status": "failed", "reason": "weak_password", "raw_password": None},
    ):
        _apply_user_sync_payload(source, {"user_list": [{"user_id": "alice", "name": "Alice", "email": "a@b.c"}], "group_list": []})

    assert User.objects.get(username="alice", domain="domain.com").password.startswith("!UNSET_PASSWORD:")


@pytest.mark.django_db
def test_password_initialization_preview_does_not_create_users(password_init_source_factory):
    source = password_init_source_factory("random")
    payload = CapabilityExecutionResult.success_result("ok", payload={"group_list": [], "user_list": []})
    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload), patch(
        "apps.system_mgmt.services.password_init_service.init_password_for_user"
    ) as init_mock:
        result = preview_user_sync(source)

    assert result["result"] is True
    assert User.objects.count() == 0
    init_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 超长外部字段防溢出(AD 场景:组织 id 为 LDAP DN,中文 OU 的 DN 轻易超过
# Group.external_id / Group.name 等 varchar(100) 上限,曾导致整轮同步
# StringDataRightTruncation 崩溃)
# ---------------------------------------------------------------------------


def _long_department_dn(rdn_label: str) -> str:
    """构造一个超过 100 字符的 LDAP DN(模拟 AD 组织)。"""
    return f"OU={rdn_label},OU=" + "部" * 60 + ",OU=某集团中国,DC=example,DC=com"


def test_scoped_external_id_fits_group_field_and_stays_deterministic():
    external_id_max_length = Group._meta.get_field("external_id").max_length

    assert user_sync_service_module._scoped_external_id(1, "dept-a") == "user-sync:1:dept-a"

    long_dn_a = _long_department_dn("研发中心")
    long_dn_b = _long_department_dn("行政中心")
    assert len(f"user-sync:1:{long_dn_a}") > external_id_max_length

    scoped_a = user_sync_service_module._scoped_external_id(1, long_dn_a)
    assert len(scoped_a) <= external_id_max_length
    assert scoped_a.startswith("user-sync:1:")
    # 同一外部 ID 每轮同步必须生成相同值,否则每轮都会删除重建组
    assert scoped_a == user_sync_service_module._scoped_external_id(1, long_dn_a)
    # 不同外部 ID 压缩后不能互相碰撞,不同 source 之间也要隔离
    assert scoped_a != user_sync_service_module._scoped_external_id(1, long_dn_b)
    assert scoped_a != user_sync_service_module._scoped_external_id(2, long_dn_a)


@pytest.mark.django_db
def test_execute_user_sync_survives_overlong_group_and_user_fields(ready_integration_instance):
    root_dn = _long_department_dn("根组织")
    parent_dn = _long_department_dn("华南分公司")
    child_dn = _long_department_dn("华南分公司二级事业部")
    source = UserSyncSource.objects.create(
        name="source-ad-long-dn",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="AD Long Root",
        business_config={"root_department_id": root_dn},
        field_mapping={},
        schedule_config={},
    )

    overlong_username = "u" * 130
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [
                {"id": parent_dn, "parent_id": root_dn, "name": "部" * 120},
                {"id": child_dn, "parent_id": parent_dn, "name": "二级事业部"},
            ],
            "user_list": [
                {
                    "user_id": overlong_username,
                    "name": "名" * 150,
                    "email": "user1@example.com",
                    "mobile": "1" * 40,
                    "department_ids": [child_dn],
                }
            ],
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        first_result = execute_user_sync(source.id)

    assert first_result["result"] is True, first_result["message"]

    external_id_max_length = Group._meta.get_field("external_id").max_length
    name_max_length = Group._meta.get_field("name").max_length

    root_group = Group.objects.get(parent_id=0, name="AD Long Root")
    assert len(root_group.external_id) <= external_id_max_length

    parent_group = Group.objects.get(parent_id=root_group.id, sync_source=source)
    assert len(parent_group.external_id) <= external_id_max_length
    assert parent_group.name == "部" * name_max_length

    child_group = Group.objects.get(parent_id=parent_group.id, sync_source=source)
    assert child_group.name == "二级事业部"
    assert len(child_group.external_id) <= external_id_max_length

    user = User.objects.get(username=overlong_username[: User._meta.get_field("username").max_length])
    assert user.display_name == "名" * User._meta.get_field("display_name").max_length
    assert user.phone == "1" * User._meta.get_field("phone").max_length
    assert user.group_list == [child_group.id]

    # 再次同步必须幂等:组不重建、不残留重复,用户不翻倍
    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        second_result = execute_user_sync(source.id)

    assert second_result["result"] is True, second_result["message"]
    assert Group.objects.filter(sync_source=source).count() == 3
    assert Group.objects.get(parent_id=root_group.id, sync_source=source).id == parent_group.id
    assert User.objects.filter(username__startswith="u").count() == 1


# ---------------------------------------------------------------------------
# Task 3: 同步进度展示相关测试
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_batch_size_adapts_to_total():
    """批次大小公式:min(50, max(1, total // 20)),total=0 走 1。"""
    from apps.system_mgmt.services.user_sync_service import _get_batch_size

    assert _get_batch_size(0) == 1
    assert _get_batch_size(1) == 1
    assert _get_batch_size(10) == 1   # 10 // 20 = 0 → max(1, 0) = 1
    assert _get_batch_size(20) == 1   # 20 // 20 = 1
    assert _get_batch_size(100) == 5  # 100 // 20 = 5
    assert _get_batch_size(200) == 10
    assert _get_batch_size(1000) == 50
    assert _get_batch_size(2000) == 50
    assert _get_batch_size(20000) == 50


@pytest.mark.django_db
def test_execute_user_sync_snapshots_password_init_mode(ready_integration_instance):
    """不同 password_init 模式下,RUNNING run 创建时 payload.password_init_mode 立即 snapshot。"""
    from apps.system_mgmt.services.user_sync_service import _get_batch_size

    # 验证 _get_batch_size 已经导入(避免 lint 错误)
    assert _get_batch_size(0) == 1

    # 模式 none
    source_none = UserSyncSource.objects.create(
        name="snapshot-none",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Snapshot None",
        business_config={"root_department_id": "0"},
        platform_config={"password_init": {"mode": "none"}},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )
    payload_empty = CapabilityExecutionResult.success_result(
        "ok", payload={"group_list": [], "user_list": []}
    )
    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_empty):
        result_none = execute_user_sync(source_none.id)
    assert result_none["result"] is True
    run_none = UserSyncRun.objects.get(source=source_none)
    assert run_none.payload.get("password_init_mode") == "none"

    # 模式 uniform
    source_uniform = UserSyncSource.objects.create(
        name="snapshot-uniform",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Snapshot Uniform",
        business_config={"root_department_id": "0"},
        platform_config={"password_init": {"mode": "uniform", "email_channel_id": 7}},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )
    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_empty):
        result_uniform = execute_user_sync(source_uniform.id)
    assert result_uniform["result"] is True
    run_uniform = UserSyncRun.objects.get(source=source_uniform)
    assert run_uniform.payload.get("password_init_mode") == "uniform"

    # 模式 random
    source_random = UserSyncSource.objects.create(
        name="snapshot-random",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Snapshot Random",
        business_config={"root_department_id": "0"},
        platform_config={"password_init": {"mode": "random", "email_channel_id": 7}},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )
    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_empty):
        result_random = execute_user_sync(source_random.id)
    assert result_random["result"] is True
    run_random = UserSyncRun.objects.get(source=source_random)
    assert run_random.payload.get("password_init_mode") == "random"


@pytest.mark.django_db
def test_apply_user_sync_writes_phase_progress_at_batch_boundary(ready_integration_instance):
    """200 用户时 batch_size=10,phase_progress.sync_users 至少被写 20 次。

    同时验证 phase_progress.fetch_directory / sync_groups / reconcile / finalize
    都按预期写入了对应 entry。
    """
    source = UserSyncSource.objects.create(
        name="progress-200",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Progress 200",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )

    user_list = [
        {"user_id": f"u{i:03d}", "name": f"User{i}", "email": f"u{i}@x.com",
         "department_ids": ["0"]}
        for i in range(200)
    ]
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [],
            "user_list": user_list,
        },
    )

    progress_writes = {"sync_users": 0}
    original_write_progress = user_sync_service_module._write_phase_progress

    def counting_write_progress(run_id, phase, current, total, status, counters=None):
        if phase == "sync_users":
            progress_writes["sync_users"] += 1
        return original_write_progress(run_id, phase, current=current, total=total, status=status, counters=counters)

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload), \
         patch("apps.system_mgmt.services.user_sync_service._write_phase_progress", side_effect=counting_write_progress):
        result = execute_user_sync(source.id)

    assert result["result"] is True
    # 200 用户 batch_size=10 → 20 个 batch → sync_users 至少被写 20 次(可能更多,因 reconcile 后还会再写一次)
    assert progress_writes["sync_users"] >= 20

    run = UserSyncRun.objects.get(source=source)
    phase_progress = run.payload.get("phase_progress") or {}
    assert phase_progress.get("fetch_directory", {}).get("status") == "finish"
    assert phase_progress.get("fetch_directory", {}).get("completed_at")
    assert phase_progress.get("sync_groups", {}).get("status") == "finish"
    assert phase_progress.get("sync_groups", {}).get("completed_at")
    assert phase_progress.get("sync_users", {}).get("status") == "finish"
    assert phase_progress.get("sync_users", {}).get("completed_at")
    assert phase_progress.get("sync_users", {}).get("current") == 200
    assert phase_progress.get("sync_users", {}).get("total") == 200
    assert phase_progress.get("reconcile", {}).get("status") == "finish"
    assert phase_progress.get("reconcile", {}).get("completed_at")
    # password_init 模式未配置,不应写 finalize
    assert "finalize" not in phase_progress
    # counters 应包含 new_users 计数(per-phase:phase_progress.sync_users.counters)
    sync_phase = run.payload.get("phase_progress", {}).get("sync_users", {})
    counters = sync_phase.get("counters") or {}
    assert counters.get("new_users") == 200
    assert counters.get("updated_users") == 0
    assert counters.get("conflict_users") == 0


@pytest.mark.django_db
def test_batch_sync_does_not_disable_later_batch_users(ready_integration_instance):
    """单批失败前已 commit 的用户,不会被错误禁用(全量对账只在所有 batch 成功后执行)。

    模拟:总 25 用户,batch_size=10 → 3 批。第 2 批抛 RuntimeError(整批失败)。
    - 第 1 批 10 用户应被创建
    - 第 2 批失败抛出,run.status=FAILED
    - 第 3 批**不会执行**(异常已抛出)
    - reconcile 阶段**不会执行**
    - 因此第 1 批的 10 用户保持 enabled=True(不被禁用)
    """
    source = UserSyncSource.objects.create(
        name="batch-fail",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Batch Fail",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )

    user_list = [
        {"user_id": f"u{i:03d}", "name": f"User{i}", "email": f"u{i}@x.com",
         "department_ids": ["0"]}
        for i in range(500)
    ]
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={"group_list": [], "user_list": user_list},
    )

    # 拦截 _process_user_batch,让第 2 批(索引 1)抛 RuntimeError 模拟整批失败
    real_process = user_sync_service_module._process_user_batch
    call_count = {"n": 0}

    def failing_process(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated batch 2 failure")
        return real_process(*args, **kwargs)

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload), \
         patch("apps.system_mgmt.services.user_sync_service._process_user_batch", side_effect=failing_process):
        result = execute_user_sync(source.id)

    assert result["result"] is False
    run = UserSyncRun.objects.get(source=source)
    assert run.status == UserSyncRunStatusChoices.FAILED
    # phase_progress.sync_users 应为 error
    phase_progress = run.payload.get("phase_progress") or {}
    assert phase_progress.get("sync_users", {}).get("status") == "error"
    # phase_error 已记录
    assert run.payload.get("phase_error", {}).get("phase") == "sync_users"

    # 第 1 批(u000~u024)应被成功创建(500 用户,batch_size=25)
    created_usernames = list(
        User.objects.filter(domain="domain.com", sync_source=source).values_list("username", flat=True)
    )
    # 第 1 批 25 个用户都被创建
    for i in range(25):
        assert f"u{i:03d}" in created_usernames, f"u{i:03d} 应在第 1 批被创建"
    # 第 3 批(u050~u499)**不应**被处理
    assert "u050" not in created_usernames
    assert "u499" not in created_usernames
    # reconcile 阶段不应执行 - 第 1 批的 25 个用户不应被 disable(因为 reconcile 未跑)
    first_batch_users = User.objects.filter(
        username__in=[f"u{i:03d}" for i in range(25)],
        domain="domain.com",
    )
    for user in first_batch_users:
        assert user.disabled is False, f"u{user.username} 不应被 disable,reconcile 阶段未跑"


@pytest.mark.django_db
def test_run_payload_mutations_preserve_all_writers(ready_integration_instance):
    """交错模拟进度、密码初始化、邮件状态写入,断言阶段、保险库和邮件状态均未丢失。"""
    source = UserSyncSource.objects.create(
        name="concurrent-writers",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Concurrent Writers",
        business_config={"root_department_id": "0"},
        platform_config={"password_init": {"mode": "random", "email_channel_id": 7}},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )

    user_list = [
        {"user_id": f"u{i}", "name": f"User{i}", "email": f"u{i}@x.com",
         "department_ids": ["0"]}
        for i in range(5)
    ]
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [],
            "user_list": user_list,
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_user_sync(source.id)

    assert result["result"] is True
    run = UserSyncRun.objects.get(source=source)
    payload = run.payload

    # 阶段进度应完整
    assert payload.get("phase_progress", {}).get("fetch_directory", {}).get("status") == "finish"
    assert payload.get("phase_progress", {}).get("sync_groups", {}).get("status") == "finish"
    assert payload.get("phase_progress", {}).get("sync_users", {}).get("status") == "finish"
    assert payload.get("phase_progress", {}).get("reconcile", {}).get("status") == "finish"
    # mode=random → finalize 应被写入
    assert payload.get("phase_progress", {}).get("finalize", {}).get("status") == "finish"

    # password_vault / email_status / email_dispatch 应被保留(由 _process_user_batch 内的 password_init_service 写入)
    assert "password_vault" in payload
    assert len(payload["password_vault"]) == 5
    assert "email_status" in payload
    assert payload["email_status"].get("total") == 5
    assert "email_dispatch" in payload

    # counters 应正确(per-phase)
    sync_counters = payload.get("phase_progress", {}).get("sync_users", {}).get("counters") or {}
    assert sync_counters.get("new_users") == 5
    reconcile_counters = payload.get("phase_progress", {}).get("reconcile", {}).get("counters") or {}
    assert reconcile_counters.get("disabled_users") == 0

    # password_init_mode snapshot
    assert payload.get("password_init_mode") == "random"


@pytest.mark.django_db
def test_failed_run_preserves_phase_progress_payload(ready_integration_instance):
    """失败场景:phase_progress / phase_error 不被终态保存覆盖,request_id 写入。

    模拟 provider 失败分支(刚进入 execute_user_sync 就失败),
    验证:
    - phase_progress.fetch_directory = error
    - phase_error 顶层块存在
    - 终态 status=FAILED,summary=语言无关错误码,request_id 已写入
    - phase_error 不持久化原始异常文本
    """
    source = UserSyncSource.objects.create(
        name="fail-preserve",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Fail Preserve",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )

    # provider 调用失败,返回 CapabilityExecutionResult.failed_result
    # summary 故意带敏感信息,验证其不会进入运行记录 payload。
    sensitive_summary = "POST https://internal.api/users?app_secret=plain-secret failed with stack trace: line 42 SQL select * from secret_table"
    failed_payload = CapabilityExecutionResult.failed_result(
        sensitive_summary, code="provider.request_failed"
    )
    failed_payload.request_id = "req-test-123"

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=failed_payload):
        result = execute_user_sync(source.id)

    assert result["result"] is False
    assert result["message"] == "provider_fetch_failed"

    run = UserSyncRun.objects.get(source=source)
    assert run.status == UserSyncRunStatusChoices.FAILED
    # phase_progress.fetch_directory.status = error
    assert run.payload.get("phase_progress", {}).get("fetch_directory", {}).get("status") == "error"
    # phase_error 顶层块存在
    assert run.payload.get("phase_error", {}).get("phase") == "fetch_directory"
    assert run.payload["phase_error"]["error_code"] == "provider_fetch_failed"
    assert "error_message" not in run.payload["phase_error"]
    # request_id 已写入 payload(在终态保存的 payload_overrides 中)
    assert run.payload.get("request_id") == "req-test-123"
    # run.request_id 字段也写入
    assert run.request_id == "req-test-123"


@pytest.mark.django_db
def test_to_safe_error_code_classifies_errors_without_retaining_exception_text():
    """阶段错误只持久化语言无关错误码，绝不衍生或保留异常原文。"""
    from apps.system_mgmt.services.user_sync_service import _to_safe_error_code

    # 凭据类:password / app_secret / token
    assert _to_safe_error_code(Exception("connection failed: password=hunter2-secret")) == "sync_failed"
    assert _to_safe_error_code(Exception("invalid app_secret=plain-secret-value")) == "sync_failed"
    assert _to_safe_error_code(Exception("auth failed token=abc.def.ghi")) == "sync_failed"

    # URL 查询参数
    assert _to_safe_error_code(Exception("GET https://api.example.com/users?token=secret123&id=42")) == "sync_failed"

    # 堆栈
    assert _to_safe_error_code(Exception("Traceback (most recent call last):\n  File '/var/secret/path/x.py', line 1\n    secret_func()")) == "sync_failed"

    # 已知异常类型的标准化文案
    from django.db.utils import IntegrityError
    assert _to_safe_error_code(IntegrityError("duplicate key value violates unique constraint")) == "data_conflict"

    assert _to_safe_error_code(Exception("")) == "sync_failed"


@pytest.mark.django_db
def test_sync_users_empty_user_list_writes_finish(ready_integration_instance):
    """user_list 为空时,sync_users 阶段直接写 finish(0/0),不进入 batch 循环。"""
    source = UserSyncSource.objects.create(
        name="empty-users",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Empty Users",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )

    # group_list 为空,避免 parent_id="0" 自指引发的 walk 递归
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={"group_list": [], "user_list": []},
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_user_sync(source.id)

    assert result["result"] is True
    run = UserSyncRun.objects.get(source=source)
    sync_users_phase = run.payload.get("phase_progress", {}).get("sync_users", {})
    assert sync_users_phase.get("status") == "finish"
    assert sync_users_phase.get("current") == 0
    assert sync_users_phase.get("total") == 0
    # reconcile 也应执行
    assert run.payload.get("phase_progress", {}).get("reconcile", {}).get("status") == "finish"


@pytest.mark.django_db
def test_per_phase_counters_split_between_sync_users_and_reconcile(ready_integration_instance):
    """per-phase counters 拆分:同步用户只含 new/updated/conflict,对账只含 disabled_users + deleted_group_count。

    场景:3 个用户已存在(将被 reconcile disable),5 个新用户(将被 sync_users 新建)
    → 终态 phase_progress.sync_users.counters 应只有 new/updated/conflict 三个字段
    → phase_progress.reconcile.counters 应只有 disabled_users + deleted_group_count
    """
    source = UserSyncSource.objects.create(
        name="per-phase-counters",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Per Phase Counters",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )

    # 先创建 3 个"老用户"(属于该 source),供 reconcile 标记为 stale
    legacy_domain = "domain.com"
    for i in range(3):
        User.objects.create(
            user_id=str(uuid.uuid4()),
            username=f"legacy_{i}",
            display_name=f"Legacy {i}",
            email=f"legacy_{i}@x.com",
            password=make_password(""),
            domain=legacy_domain,
            disabled=False,
            group_list=[],
            sync_source=source,
        )

    # 外部清单:5 个新用户(全部不在历史遗留名单里)
    user_list = [
        {"user_id": f"u{i}", "name": f"User{i}", "email": f"u{i}@x.com",
         "department_ids": ["0"]}
        for i in range(5)
    ]
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={"group_list": [], "user_list": user_list},
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_user_sync(source.id)

    assert result["result"] is True
    run = UserSyncRun.objects.get(source=source)
    phase_progress = run.payload.get("phase_progress") or {}

    # 1. 同步用户阶段 counters 只含本阶段字段
    sync_users_counters = phase_progress.get("sync_users", {}).get("counters") or {}
    assert set(sync_users_counters.keys()) == {"new_users", "updated_users", "conflict_users"}, \
        f"sync_users phase counters 应只含这 3 个字段,实际: {sync_users_counters.keys()}"
    assert sync_users_counters["new_users"] == 5
    assert sync_users_counters["updated_users"] == 0
    assert sync_users_counters["conflict_users"] == 0
    # 关键断言:sync_users 阶段不能有 disabled_users
    assert "disabled_users" not in sync_users_counters, \
        "disabled_users 是对账阶段指标,不应在 sync_users 阶段出现"

    # 2. 对账阶段 counters 只含本阶段字段
    reconcile_counters = phase_progress.get("reconcile", {}).get("counters") or {}
    assert set(reconcile_counters.keys()) == {"disabled_users", "deleted_group_count"}, \
        f"reconcile phase counters 应只含这 2 个字段,实际: {reconcile_counters.keys()}"
    assert reconcile_counters["disabled_users"] == 3, \
        f"应 disable 3 个 legacy 用户,实际 disable {reconcile_counters['disabled_users']}"
    assert reconcile_counters["deleted_group_count"] == 0
    # 关键断言:reconcile 阶段不能有 new_users/updated_users
    assert "new_users" not in reconcile_counters
    assert "updated_users" not in reconcile_counters


@pytest.mark.django_db
def test_reconcile_clears_dangling_group_list_before_deleting_groups(ready_integration_instance):
    """reconcile 删 Group 之前必须先清掉所有活跃用户 group_list 里的悬挂引用。

    场景:3 个 Group(1 active + 2 stale),2 个活跃用户的 group_list 引用
    包含将被删的 Group id。reconcile 后 Group 行被删,但 User.group_list
    不应保留对已删 Group.id 的引用。
    """
    source = UserSyncSource.objects.create(
        name="dangling-groups",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Dangling Root",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )

    legacy_domain = "domain.com"
    # 预创建根组,获取它的 id(后续预创建的子组用此 id 作为 parent_id,
    # 让 _sync_groups 正确复用预创建组,而不是再创建新的)
    root_group = Group.objects.create(
        name="Dangling Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    # 创建 3 个子组:1 active(外部清单里,会被 _sync_groups 复用) + 2 stale(将被删)
    active_group = Group.objects.create(
        name="Active Group",
        parent_id=root_group.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:active",
    )
    stale_group_1 = Group.objects.create(
        name="Stale Group 1",
        parent_id=root_group.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:stale1",
    )
    stale_group_2 = Group.objects.create(
        name="Stale Group 2",
        parent_id=root_group.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:stale2",
    )

    # 3 个活跃用户,group_list 引用不同组合
    user_mixed = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="alice",
        display_name="Alice",
        email="alice@x.com",
        password=make_password(""),
        domain=legacy_domain,
        disabled=False,
        group_list=[active_group.id, stale_group_1.id],
        sync_source=source,
    )
    user_stale_only = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="bob",
        display_name="Bob",
        email="bob@x.com",
        password=make_password(""),
        domain=legacy_domain,
        disabled=False,
        group_list=[stale_group_1.id, stale_group_2.id],
        sync_source=source,
    )
    user_clean = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="carol",
        display_name="Carol",
        email="carol@x.com",
        password=make_password(""),
        domain=legacy_domain,
        disabled=False,
        group_list=[active_group.id],
        sync_source=source,
    )
    # 1 个空 group_list 的活跃用户(被外部清单包含),验证 sync_users 会写入
    # active_group_id,reconcile 不会影响(无悬挂引用)
    user_empty = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="dave",
        display_name="Dave",
        email="dave@x.com",
        password=make_password(""),
        domain=legacy_domain,
        disabled=False,
        group_list=[],
        sync_source=source,
    )

    # 外部清单:alice / carol / dave(都还属于 source),bob 算 stale(被 disable)
    user_list = [
        {"user_id": "alice", "name": "Alice", "email": "alice@x.com", "department_ids": ["active"]},
        {"user_id": "carol", "name": "Carol", "email": "carol@x.com", "department_ids": ["active"]},
        {"user_id": "dave", "name": "Dave", "email": "dave@x.com", "department_ids": ["active"]},
    ]
    # group_list 反映 active_group(外部 dept "active" → local group)
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "group_list": [{"id": "active", "parent_id": "0", "name": "Active"}],
            "user_list": user_list,
        },
    )

    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_user_sync(source.id)

    assert result["result"] is True

    # 刷新所有用户对象(数据库已变更)
    user_mixed.refresh_from_db()
    user_stale_only.refresh_from_db()
    user_clean.refresh_from_db()
    user_empty.refresh_from_db()

    # 1. bob 是 stale,被 disable + group_list=[]
    assert user_stale_only.disabled is True
    assert user_stale_only.group_list == []

    # 2. alice 仍 active,group_list 里的 stale_group_1 被清除,只留 active_group
    assert user_mixed.disabled is False
    assert user_mixed.group_list == [active_group.id]
    assert stale_group_1.id not in user_mixed.group_list

    # 3. carol 一直只有 active_group,无变化
    assert user_clean.disabled is False
    assert user_clean.group_list == [active_group.id]

    # 4. dave 是活跃用户,sync_users 把空 group_list 设为 active_group_id,
    #    没有悬挂引用,reconcile 不动
    assert user_empty.disabled is False
    assert user_empty.group_list == [active_group.id]

    # 5. stale groups 只能在全部用户同步后的 reconcile 阶段删除
    assert not Group.objects.filter(id=stale_group_1.id).exists()
    assert not Group.objects.filter(id=stale_group_2.id).exists()

    # 6. active group 仍在
    assert Group.objects.filter(id=active_group.id).exists()

    # 7. reconcile 记录最终对账状态
    run = UserSyncRun.objects.get(source=source)
    reconcile_phase = run.payload.get("phase_progress", {}).get("reconcile", {})
    assert reconcile_phase.get("counters", {}).get("disabled_users") == 1  # bob


@pytest.mark.django_db
def test_finalize_only_written_for_password_init_modes(ready_integration_instance):
    """finalize 阶段仅当 password_init_mode ∈ {uniform, random} 时写入。"""
    # mode=none → 不写 finalize
    source_none = UserSyncSource.objects.create(
        name="finalize-none",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Finalize None",
        business_config={"root_department_id": "0"},
        platform_config={"password_init": {"mode": "none"}},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )
    payload_empty = CapabilityExecutionResult.success_result(
        "ok", payload={"group_list": [], "user_list": []}
    )
    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_empty):
        execute_user_sync(source_none.id)
    run_none = UserSyncRun.objects.get(source=source_none)
    assert "finalize" not in (run_none.payload.get("phase_progress") or {})

    # mode=uniform 但没有新用户 → 邮件未入队,finalize 必须 skipped
    source_uniform = UserSyncSource.objects.create(
        name="finalize-uniform",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Finalize Uniform",
        business_config={"root_department_id": "0"},
        platform_config={"password_init": {"mode": "uniform", "email_channel_id": 7}},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )
    with patch("apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute", return_value=payload_empty):
        execute_user_sync(source_uniform.id)
    run_uniform = UserSyncRun.objects.get(source=source_uniform)
    finalize_phase = run_uniform.payload.get("phase_progress", {}).get("finalize", {})
    assert finalize_phase.get("status") == "skipped"
    assert finalize_phase.get("skip_reason") == "no_new_users"


@pytest.mark.django_db
def test_sync_groups_keeps_stale_groups_until_reconcile(ready_integration_instance):
    """组织 upsert 阶段不能提前删除 stale 组织。"""
    source = UserSyncSource.objects.create(
        name="defer-stale-group-removal",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Deferred Root",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )
    root = Group.objects.create(
        name="Deferred Root",
        parent_id=0,
        sync_source=source,
        external_id=f"user-sync:{source.id}:0",
    )
    stale_group = Group.objects.create(
        name="Stale",
        parent_id=root.id,
        sync_source=source,
        external_id=f"user-sync:{source.id}:stale",
    )

    group_counters = {}
    _sync_groups(
        source,
        [{"id": "active", "parent_id": "0", "name": "Active"}],
        root,
        "0",
        group_counters,
    )

    assert Group.objects.filter(id=stale_group.id).exists()
    assert group_counters == {"created_groups": 1, "updated_groups": 0}

    second_group_counters = {}
    _sync_groups(
        source,
        [{"id": "active", "parent_id": "0", "name": "Active"}],
        root,
        "0",
        second_group_counters,
    )
    assert second_group_counters == {"created_groups": 0, "updated_groups": 0}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("failed_helper", "expected_phase"),
    [
        ("_sync_groups", "sync_groups"),
        ("_reconcile_synced_directory", "reconcile"),
    ],
)
def test_non_batch_stage_failure_marks_corresponding_phase(
    ready_integration_instance, failed_helper, expected_phase
):
    """组织同步和全量对账失败也必须标记具体阶段,而非只写 run=FAILED。"""
    source = UserSyncSource.objects.create(
        name=f"failure-phase-{expected_phase}",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name=f"Failure {expected_phase}",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )
    result = CapabilityExecutionResult.success_result(
        "ok", payload={"group_list": [], "user_list": []}
    )
    with patch(
        "apps.system_mgmt.services.user_sync_service.RuntimeApplicationService.execute",
        return_value=result,
    ), patch(
        f"apps.system_mgmt.services.user_sync_service.{failed_helper}",
        side_effect=RuntimeError("simulated stage failure"),
    ):
        response = execute_user_sync(source.id)

    run = UserSyncRun.objects.get(source=source)
    assert response["result"] is False
    assert run.status == UserSyncRunStatusChoices.FAILED
    assert run.payload["phase_progress"][expected_phase]["status"] == "error"
    assert run.payload["phase_error"]["phase"] == expected_phase
