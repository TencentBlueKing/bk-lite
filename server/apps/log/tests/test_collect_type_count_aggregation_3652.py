import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models import (
    CollectInstance,
    CollectInstanceOrganization,
    CollectType,
)
from apps.log.models.policy import Policy, PolicyOrganization
from apps.log.views import collect_config
from apps.log.views.collect_config import CollectTypeViewSet


class _LanguageLoader:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, key):
        return ""


def _create_policy(name, collect_type, organization):
    policy = Policy.objects.create(name=name, collect_type=collect_type)
    if organization is not None:
        PolicyOrganization.objects.create(policy=policy, organization=organization)
    return policy


def _create_instance(instance_id, collect_type, organization):
    instance = CollectInstance.objects.create(
        id=instance_id,
        name=instance_id,
        collect_type=collect_type,
    )
    if organization is not None:
        CollectInstanceOrganization.objects.create(
            collect_instance=instance,
            organization=organization,
        )
    return instance


@pytest.mark.django_db
def test_collect_type_counts_use_permission_aware_aggregate_queries(
    authenticated_user,
    django_assert_num_queries,
    monkeypatch,
):
    collect_type_a = CollectType.objects.create(
        name="type-a",
        collector="Vector",
        icon="a",
    )
    collect_type_b = CollectType.objects.create(
        name="type-b",
        collector="Vector",
        icon="b",
    )

    explicit_policy = _create_policy("explicit", collect_type_a, None)
    _create_policy("team", collect_type_a, 2)
    blocked_fallback_policy = _create_policy(
        "blocked-fallback",
        collect_type_a,
        1,
    )
    _create_policy("fallback", collect_type_b, 1)
    _create_policy("admin", collect_type_b, 9)
    _create_policy("blocked", collect_type_b, 8)

    explicit_instance = _create_instance("explicit", collect_type_a, None)
    _create_instance("team", collect_type_a, 2)
    _create_instance("blocked-fallback", collect_type_a, 1)
    _create_instance("fallback", collect_type_b, 1)
    _create_instance("admin", collect_type_b, 9)
    _create_instance("blocked", collect_type_b, 8)

    def get_permissions_rules(user, current_team, app_name, permission_key, **kwargs):
        if permission_key == "policy":
            instance_permissions = [
                {"id": explicit_policy.id, "permission": ["View"]},
                {
                    "id": f"0{blocked_fallback_policy.id}",
                    "permission": ["View"],
                },
            ]
        else:
            instance_permissions = [
                {"id": explicit_instance.id, "permission": ["View"]}
            ]
        return {
            "data": {
                "all": {"team": [{"id": 9}, {"id": "8"}]},
                str(collect_type_a.id): {
                    "instance": instance_permissions,
                    "team": [{"id": 2}, {"id": "1"}],
                },
            },
            "team": [1],
        }

    monkeypatch.setattr(collect_config, "LanguageLoader", _LanguageLoader)
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        get_permissions_rules,
    )

    request = APIRequestFactory().get(
        "/log/collect_types/",
        {
            "add_policy_count": "true",
            "add_instance_count": "true",
        },
        HTTP_COOKIE="current_team=1",
    )
    force_authenticate(request, user=authenticated_user)

    # One query loads collect types and one aggregate query serves each count.
    with django_assert_num_queries(3):
        response = CollectTypeViewSet.as_view({"get": "list"})(request)

    data = {
        item["name"]: (item["policy_count"], item["instance_count"])
        for item in json.loads(response.content)["data"]
    }
    assert data == {"type-a": (2, 2), "type-b": (2, 2)}
