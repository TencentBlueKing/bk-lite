import json
from types import SimpleNamespace

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelDetailSerializer, CollectModelSerializer
from apps.cmdb.views.collect import CollectModelViewSet

RESULT_PAYLOAD_FIELDS = {
    "collect_data",
    "collect_digest",
    "format_data",
    "topology_snapshot",
}


def _request(*, query_params=None):
    return SimpleNamespace(
        user=SimpleNamespace(group_list=[]),
        COOKIES={},
        query_params=query_params or {},
    )


def _retrieve(task, user, monkeypatch, *, include_result_data=None):
    monkeypatch.setattr(
        CollectModelViewSet,
        "get_queryset_by_permission",
        lambda self, request, queryset, permission_key=None: queryset,
    )
    path = f"/cmdb/api/collect/{task.id}/"
    if include_result_data is not None:
        path = f"{path}?include_result_data={include_result_data}"
    request = APIRequestFactory().get(path)
    force_authenticate(request, user=user)
    return CollectModelViewSet.as_view({"get": "retrieve"})(request, pk=task.id)


@pytest.mark.django_db
def test_collect_model_detail_serializer_bounds_default_payload_and_keeps_masked_credential(monkeypatch):
    large_value = "x" * 256_000
    instance = CollectModels(
        model_id="host",
        driver_type="job",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "encrypted"}],
        collect_data={"items": large_value},
        collect_digest={"items": large_value},
        format_data={"items": large_value},
        topology_snapshot={"items": large_value},
    )
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.get_collect_model_passwords",
        lambda collect_model_id, driver_type=None: ["password"],
    )
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )

    request = _request()
    legacy_data = CollectModelSerializer(instance=instance, context={"request": request}).data
    detail_data = CollectModelDetailSerializer(instance=instance, context={"request": request}).data

    assert RESULT_PAYLOAD_FIELDS.isdisjoint(detail_data)
    assert detail_data["credential"] == [{"credential_id": "cred-1", "username": "admin", "password": "******"}]
    assert len(json.dumps(legacy_data)) > len(json.dumps(detail_data)) + 1_000_000


@pytest.mark.django_db
def test_collect_model_retrieve_defaults_to_bounded_payload(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    task = CollectModels.objects.create(
        name="bounded-detail",
        task_type="host",
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        collect_data={"items": "x" * 4096},
        collect_digest={"items": "x" * 4096},
        format_data={"items": "x" * 4096},
        topology_snapshot={"items": "x" * 4096},
    )

    response = _retrieve(task, authenticated_user, monkeypatch)

    assert response.status_code == 200
    assert RESULT_PAYLOAD_FIELDS.isdisjoint(response.data)


@pytest.mark.django_db
def test_collect_model_retrieve_keeps_legacy_result_payload_behind_explicit_switch(
    authenticated_user,
    monkeypatch,
):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    task = CollectModels.objects.create(
        name="legacy-detail",
        task_type="host",
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        collect_data={"items": [1]},
        collect_digest={"items": [2]},
        format_data={"items": [3]},
        topology_snapshot={"items": [4]},
    )

    response = _retrieve(task, authenticated_user, monkeypatch, include_result_data="true")

    assert response.status_code == 200
    assert RESULT_PAYLOAD_FIELDS.issubset(response.data)


@pytest.mark.parametrize(
    ("query_params", "expected_serializer"),
    [
        ({}, CollectModelDetailSerializer),
        ({"include_result_data": "false"}, CollectModelDetailSerializer),
        ({"include_result_data": "1"}, CollectModelSerializer),
        ({"include_result_data": "true"}, CollectModelSerializer),
    ],
)
def test_collect_model_retrieve_routes_legacy_result_fields_only_when_explicitly_requested(
    query_params,
    expected_serializer,
):
    view = CollectModelViewSet()
    view.action = "retrieve"
    view.request = _request(query_params=query_params)

    assert view.get_serializer_class() is expected_serializer


def test_collect_model_retrieve_defers_result_columns_unless_legacy_payload_is_requested(monkeypatch):
    monkeypatch.setattr(
        CollectModelViewSet,
        "get_queryset_by_permission",
        lambda self, request, queryset, permission_key=None: queryset,
    )
    view = CollectModelViewSet()
    view.action = "retrieve"
    view.request = _request()

    deferred_fields, is_deferred = view.get_queryset().query.deferred_loading

    assert is_deferred is True
    assert RESULT_PAYLOAD_FIELDS.issubset(deferred_fields)

    view.request = _request(query_params={"include_result_data": "true"})
    legacy_deferred_fields, _ = view.get_queryset().query.deferred_loading
    assert RESULT_PAYLOAD_FIELDS.isdisjoint(legacy_deferred_fields)
