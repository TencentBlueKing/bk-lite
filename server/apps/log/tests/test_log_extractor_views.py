import json
import threading

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models import CollectInstance, CollectInstanceOrganization, CollectType, LogExtractor, SystemVectorConfigState
from apps.log.services.log_extractor import preview_runtime
from apps.log.views.extractor import LogExtractorViewSet
from apps.system_mgmt.models.operation_log import OperationLog
from apps.system_mgmt.models.user import Group


@pytest.fixture
def collect_instance(db):
    collect_type = CollectType.objects.create(name="file", collector="Vector", icon="", attrs=[])
    instance = CollectInstance.objects.create(id="instance-1", name="instance", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance=instance, organization=1)
    return instance


def _allow_current_team(mocker):
    Group.objects.get_or_create(id=1, defaults={"name": "extractor-team"})
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )


def _allow_view_permission(mocker, collect_instance):
    mocker.patch(
        "apps.log.views.extractor.get_permissions_rules",
        return_value={
            "data": {
                str(collect_instance.collect_type_id): {
                    "instance": [{"id": collect_instance.id, "permission": ["View"]}],
                }
            }
        },
    )


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_create_rule_saves_resource_and_marks_one_global_generation(authenticated_user, collect_instance, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=("is_superuser",))
    _allow_current_team(mocker)
    task = mocker.patch("apps.log.services.log_extractor.publication._publication_task")
    request = APIRequestFactory().post(
        "/api/v1/log/log_extractors/",
        {
            "name": "copy status",
            "collect_instance": collect_instance.id,
            "extractor_type": "copy",
            "source_field": "http.status",
            "target_field": "parsed.status",
            "condition": {},
            "config": {},
            "delete_source": False,
        },
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"post": "create"})(request)

    assert response.status_code == 201
    assert LogExtractor.objects.get().sort_order == 0
    state = SystemVectorConfigState.objects.get()
    assert state.desired_generation == 1
    assert response.data["publication"]["desired_generation"] == 1
    task.return_value.delay.assert_called_once_with(1)
    summary = OperationLog.objects.get(action_type="create", app="log").summary
    assert "instance=instance-1" in summary
    assert f"rule={LogExtractor.objects.get().pk}" in summary
    assert "generation=1" in summary


@pytest.mark.integration
@pytest.mark.django_db
def test_view_user_cannot_create_rule(authenticated_user, collect_instance, mocker):
    _allow_current_team(mocker)
    _allow_view_permission(mocker, collect_instance)
    request = APIRequestFactory().post(
        "/api/v1/log/log_extractors/",
        {"collect_instance": collect_instance.id},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"post": "create"})(request)

    assert response.status_code == 403
    assert not LogExtractor.objects.exists()


@pytest.mark.integration
@pytest.mark.django_db
def test_view_user_can_list_rules_in_current_team(authenticated_user, collect_instance, mocker):
    _allow_current_team(mocker)
    LogExtractor.objects.create(
        name="visible",
        collect_instance=collect_instance,
        extractor_type="copy",
        source_field="message",
        target_field="parsed.message",
        condition={},
        config={},
        delete_source=False,
        sort_order=0,
    )
    _allow_view_permission(mocker, collect_instance)
    request = APIRequestFactory().get("/api/v1/log/log_extractors/", {"collect_instance": collect_instance.id})
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert [item["name"] for item in response.data["items"]] == ["visible"]


@pytest.mark.integration
@pytest.mark.django_db
def test_instance_outside_current_team_is_hidden(authenticated_user, collect_instance, mocker):
    collect_instance.collectinstanceorganization_set.all().delete()
    CollectInstanceOrganization.objects.create(collect_instance=collect_instance, organization=2)
    _allow_current_team(mocker)
    request = APIRequestFactory().get("/api/v1/log/log_extractors/", {"collect_instance": collect_instance.id})
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.django_db
def test_view_user_gets_bounded_error_for_catastrophic_regex_preview(authenticated_user, collect_instance, mocker, monkeypatch):
    _allow_current_team(mocker)
    LogExtractor.objects.create(
        name="stored catastrophic rule",
        collect_instance=collect_instance,
        extractor_type="regex_replace",
        source_field="message",
        target_field="result",
        condition={},
        config={"pattern": "(a+)+$", "replacement": "masked"},
        delete_source=False,
        sort_order=0,
    )
    _allow_view_permission(mocker, collect_instance)
    monkeypatch.setattr(preview_runtime, "REGEX_PREVIEW_TIMEOUT_SECONDS", 0.1)
    request = APIRequestFactory().post(
        "/api/v1/log/log_extractors/preview/",
        {
            "collect_instance": collect_instance.id,
            "event": {"message": "a" * 27 + "!"},
            "draft": {
                "extractor_type": "copy",
                "source_field": "message",
                "target_field": "copy",
                "condition": {},
                "config": {},
                "delete_source": False,
            },
        },
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"post": "preview"})(request)

    assert response.status_code == 400
    assert response.data == {
        "detail": "正则预览执行超时",
        "data": {"error_code": "log_extractor_preview_timeout"},
    }
    assert json.loads(response.render().content)["data"] == {"error_code": "log_extractor_preview_timeout"}


@pytest.mark.integration
@pytest.mark.django_db
def test_regex_preview_capacity_exhaustion_returns_retryable_status(authenticated_user, collect_instance, mocker, monkeypatch):
    _allow_current_team(mocker)
    _allow_view_permission(mocker, collect_instance)
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(preview_runtime, "_REGEX_PREVIEW_SLOTS", slots)
    request = APIRequestFactory().post(
        "/api/v1/log/log_extractors/preview/",
        {
            "collect_instance": collect_instance.id,
            "event": {"message": "aaaa"},
            "draft": {
                "extractor_type": "regex_replace",
                "source_field": "message",
                "target_field": "result",
                "condition": {},
                "config": {"pattern": "a+$", "replacement": "masked"},
                "delete_source": False,
            },
        },
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"post": "preview"})(request)

    assert response.status_code == 429
    assert response["Retry-After"] == "1"
    assert response.data == {"detail": "正则预览并发已达上限，请稍后重试"}
    slots.release()


@pytest.mark.integration
@pytest.mark.django_db
def test_regex_preview_oversized_field_returns_structured_400(authenticated_user, collect_instance, mocker, monkeypatch):
    _allow_current_team(mocker)
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=("is_superuser",))
    monkeypatch.setattr(preview_runtime, "REGEX_PREVIEW_MAX_FIELD_BYTES", 3)
    request = APIRequestFactory().post(
        "/api/v1/log/log_extractors/preview/",
        {
            "collect_instance": collect_instance.id,
            "event": {"message": "aaaa"},
            "draft": {
                "extractor_type": "regex_replace",
                "source_field": "message",
                "target_field": "result",
                "condition": {},
                "config": {"pattern": "a+$", "replacement": "masked"},
                "delete_source": False,
            },
        },
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"post": "preview"})(request)

    assert response.status_code == 400
    assert response.data == {
        "detail": "正则预览字段大小超过上限",
        "data": {"error_code": "log_extractor_preview_too_large"},
    }
    assert json.loads(response.render().content)["data"] == {"error_code": "log_extractor_preview_too_large"}


@pytest.fixture
def syslog_type(db):
    return CollectType.objects.create(name="syslog", collector="Vector", icon="", attrs=[])


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_create_type_rule_saves_without_instance(authenticated_user, syslog_type, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=("is_superuser",))
    _allow_current_team(mocker)
    task = mocker.patch("apps.log.services.log_extractor.publication._publication_task")
    request = APIRequestFactory().post(
        "/api/v1/log/log_extractors/",
        {
            "name": "copy syslog",
            "collect_type": "syslog",
            "extractor_type": "copy",
            "source_field": "message",
            "target_field": "parsed.message",
            "condition": {},
            "config": {},
            "delete_source": False,
        },
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"post": "create"})(request)

    assert response.status_code == 201
    rule = LogExtractor.objects.get()
    assert rule.collect_instance_id is None
    assert rule.collect_type_id == syslog_type.id
    assert response.data["resource"]["collect_type"] == "syslog"
    assert response.data["resource"]["collect_instance"] is None
    task.return_value.delay.assert_called_once_with(1)


@pytest.mark.integration
@pytest.mark.django_db
def test_type_rule_write_requires_configure_permission(authenticated_user, syslog_type, mocker):
    _allow_current_team(mocker)
    authenticated_user.permission = {"log": {"integration_configure-View"}}
    request = APIRequestFactory().post(
        "/api/v1/log/log_extractors/",
        {"collect_type": "syslog", "name": "denied", "extractor_type": "copy", "source_field": "message", "target_field": "parsed.message"},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"post": "create"})(request)

    assert response.status_code == 403
    assert not LogExtractor.objects.exists()


@pytest.mark.integration
@pytest.mark.django_db
def test_type_rule_list_allows_configure_view(authenticated_user, syslog_type, mocker):
    _allow_current_team(mocker)
    authenticated_user.permission = {"log": {"integration_configure-View"}}
    LogExtractor.objects.create(
        name="visible",
        collect_type=syslog_type,
        extractor_type="copy",
        source_field="message",
        target_field="parsed.message",
        condition={},
        config={},
        delete_source=False,
        sort_order=0,
    )
    request = APIRequestFactory().get("/api/v1/log/log_extractors/", {"collect_type": "syslog"})
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert [item["name"] for item in response.data["items"]] == ["visible"]
    assert response.data["can_operate"] is False


@pytest.mark.integration
@pytest.mark.django_db
def test_type_rule_list_allows_integration_list_view(authenticated_user, syslog_type, mocker):
    _allow_current_team(mocker)
    authenticated_user.permission = {"log": {"integration_list-View"}}
    LogExtractor.objects.create(
        name="visible",
        collect_type=syslog_type,
        extractor_type="copy",
        source_field="message",
        target_field="parsed.message",
        condition={},
        config={},
        delete_source=False,
        sort_order=0,
    )
    request = APIRequestFactory().get("/api/v1/log/log_extractors/", {"collect_type": "syslog"})
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert [item["name"] for item in response.data["items"]] == ["visible"]
    assert response.data["can_operate"] is False


@pytest.mark.integration
@pytest.mark.django_db
def test_type_rule_list_can_operate_with_configure_add(authenticated_user, syslog_type, mocker):
    _allow_current_team(mocker)
    authenticated_user.permission = {"log": {"integration_configure-View", "integration_configure-Add"}}
    request = APIRequestFactory().get("/api/v1/log/log_extractors/", {"collect_type": "syslog"})
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert response.data["can_operate"] is True


@pytest.mark.integration
@pytest.mark.django_db
def test_create_rejects_mixed_or_missing_scope(authenticated_user, collect_instance, syslog_type, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=("is_superuser",))
    _allow_current_team(mocker)
    factory = APIRequestFactory()

    missing = factory.post(
        "/api/v1/log/log_extractors/",
        {"name": "missing", "extractor_type": "copy", "source_field": "message", "target_field": "parsed.message"},
        format="json",
    )
    missing.COOKIES["current_team"] = "1"
    force_authenticate(missing, user=authenticated_user)
    missing_response = LogExtractorViewSet.as_view({"post": "create"})(missing)
    assert missing_response.status_code == 400

    mixed = factory.post(
        "/api/v1/log/log_extractors/",
        {
            "name": "mixed",
            "collect_instance": collect_instance.id,
            "collect_type": "syslog",
            "extractor_type": "copy",
            "source_field": "message",
            "target_field": "parsed.message",
        },
        format="json",
    )
    mixed.COOKIES["current_team"] = "1"
    force_authenticate(mixed, user=authenticated_user)
    mixed_response = LogExtractorViewSet.as_view({"post": "create"})(mixed)
    assert mixed_response.status_code == 400
    assert not LogExtractor.objects.exists()


@pytest.mark.integration
@pytest.mark.django_db
def test_type_rule_write_without_current_team_is_denied(authenticated_user, syslog_type, mocker):
    authenticated_user.permission = {"log": {"integration_configure-Add"}}
    request = APIRequestFactory().post(
        "/api/v1/log/log_extractors/",
        {"collect_type": "syslog", "name": "denied", "extractor_type": "copy", "source_field": "message", "target_field": "parsed.message"},
        format="json",
    )
    force_authenticate(request, user=authenticated_user)

    response = LogExtractorViewSet.as_view({"post": "create"})(request)

    assert response.status_code == 403
    assert not LogExtractor.objects.exists()
