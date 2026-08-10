import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models import CollectInstance, CollectInstanceOrganization, CollectType, LogExtractor, SystemVectorConfigState
from apps.log.views.extractor import LogExtractorViewSet
from apps.system_mgmt.models.operation_log import OperationLog


@pytest.fixture
def collect_instance(db):
    collect_type = CollectType.objects.create(name="file", collector="Vector", icon="", attrs=[])
    instance = CollectInstance.objects.create(id="instance-1", name="instance", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance=instance, organization=1)
    return instance


def _allow_current_team(mocker):
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
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
