import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.models import CollectConfig, CollectInstance, CollectType
from apps.log.services.collect_type import CollectTypeService
from apps.log.views.collect_config import CollectConfigViewSet, CollectInstanceViewSet
from apps.log.views.k8s_collect import K8sCollectViewSet


@pytest.fixture(autouse=True)
def patch_task1_organization_scope(monkeypatch):
    from apps.core.utils.current_team_scope import SystemMgmt

    monkeypatch.setattr(
        SystemMgmt,
        "get_authorized_groups_scoped",
        Mock(return_value={"result": True, "data": [1]}),
    )
    monkeypatch.setattr(
        SystemMgmt,
        "get_assignable_groups",
        Mock(return_value={"result": True, "data": [1, 2]}),
    )


class FakeQuerySet(list):
    def filter(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def values(self, *args):
        return self

    def select_related(self, *args):
        return self

    def prefetch_related(self, *args):
        return self

    def delete(self):
        self.deleted = True


class FakeOrganizations(list):
    def all(self):
        return self


class FakeFirstResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


def make_request(data):
    return SimpleNamespace(
        user=SimpleNamespace(username="alice", domain="default"),
        data=data,
        COOKIES={"current_team": "1", "include_children": "0"},
    )


def make_instance(instance_id="inst-1", collect_type_id=7, organizations=None):
    return SimpleNamespace(
        id=instance_id,
        collect_type_id=collect_type_id,
        collectinstanceorganization_set=FakeOrganizations([SimpleNamespace(organization=org) for org in organizations or [1]]),
    )


def test_remove_collect_instance_requires_operate_permission(monkeypatch):
    instance = make_instance(organizations=[2])
    from apps.log.views import collect_config

    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {}, "team": [1]}),
    )
    node_mgmt = Mock()
    monkeypatch.setattr(collect_config, "NodeMgmt", node_mgmt)

    response = CollectInstanceViewSet().remove_collect_instance(make_request({"instance_ids": [instance.id]}))

    assert response.status_code == 403
    node_mgmt.assert_not_called()


@pytest.mark.django_db
def test_remove_collect_instance_allows_authorized_org_scope(monkeypatch):
    instance = make_instance()
    config_qs = FakeQuerySet([])
    instance_delete_qs = FakeQuerySet([])
    from apps.log.views import collect_config

    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(side_effect=[FakeQuerySet([instance]), instance_delete_qs]),
    )
    monkeypatch.setattr(collect_config.CollectConfig.objects, "filter", Mock(return_value=config_qs))
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {"all": {"team": [1]}}, "team": [1]}),
    )

    response = CollectInstanceViewSet().remove_collect_instance(make_request({"instance_ids": [instance.id]}))

    assert response.status_code == 200
    assert getattr(config_qs, "deleted", False)
    assert getattr(instance_delete_qs, "deleted", False)


@pytest.mark.django_db
def test_remove_collect_instance_allows_instance_level_operate_permission(monkeypatch):
    instance = make_instance()
    config_qs = FakeQuerySet([])
    instance_delete_qs = FakeQuerySet([])
    from apps.log.views import collect_config

    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(side_effect=[FakeQuerySet([instance]), instance_delete_qs]),
    )
    monkeypatch.setattr(collect_config.CollectConfig.objects, "filter", Mock(return_value=config_qs))
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [{"id": instance.id, "permission": ["Operate"]}],
                    }
                },
                "team": [1],
            }
        ),
    )

    response = CollectInstanceViewSet().remove_collect_instance(make_request({"instance_ids": [instance.id]}))

    assert response.status_code == 200
    assert getattr(config_qs, "deleted", False)
    assert getattr(instance_delete_qs, "deleted", False)


def test_get_config_content_requires_view_permission(monkeypatch):
    instance = make_instance(organizations=[2])
    config = SimpleNamespace(id="cfg-1", collect_instance_id=instance.id, collect_instance=instance)
    from apps.log.views import collect_config

    monkeypatch.setattr(
        collect_config.CollectConfig.objects,
        "filter",
        Mock(return_value=FakeQuerySet([config])),
    )
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {}, "team": [1]}),
    )
    node_mgmt = Mock()
    monkeypatch.setattr(collect_config, "NodeMgmt", node_mgmt)

    response = CollectConfigViewSet().get_config_content(make_request({"ids": [config.id]}))

    assert response.status_code == 403
    node_mgmt.assert_not_called()


def test_get_config_content_allows_instance_level_view_permission(monkeypatch):
    instance = make_instance()
    config = SimpleNamespace(id="cfg-1", collect_instance_id=instance.id, collect_instance=instance, file_type="yaml", is_child=False)
    from apps.log.views import collect_config

    monkeypatch.setattr(
        collect_config.CollectConfig.objects,
        "filter",
        Mock(return_value=FakeQuerySet([config])),
    )
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [{"id": instance.id, "permission": ["View"]}],
                    }
                },
                "team": [1],
            }
        ),
    )
    node_mgmt = Mock()
    node_mgmt.return_value.get_configs_by_ids.return_value = [{"config_template": "key: value"}]
    monkeypatch.setattr(collect_config, "NodeMgmt", node_mgmt)

    response = CollectConfigViewSet().get_config_content(make_request({"ids": [config.id]}))

    assert response.status_code == 200
    node_mgmt.return_value.get_configs_by_ids.assert_called_once_with([config.id])


@pytest.mark.django_db
def test_remove_collect_instance_allows_merged_duplicate_instance_permissions(monkeypatch):
    instance = make_instance()
    config_qs = FakeQuerySet([])
    instance_delete_qs = FakeQuerySet([])
    from apps.log.views import collect_config

    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(side_effect=[FakeQuerySet([instance]), instance_delete_qs]),
    )
    monkeypatch.setattr(collect_config.CollectConfig.objects, "filter", Mock(return_value=config_qs))
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [
                            {"id": instance.id, "permission": ["View"]},
                            {"id": instance.id, "permission": ["Operate"]},
                        ],
                    }
                },
                "team": [1],
            }
        ),
    )

    response = CollectInstanceViewSet().remove_collect_instance(make_request({"instance_ids": [instance.id]}))

    assert response.status_code == 200
    assert getattr(config_qs, "deleted", False)
    assert getattr(instance_delete_qs, "deleted", False)


def test_set_organizations_rejects_target_org_outside_authorized_scope(monkeypatch):
    instance = make_instance()
    from apps.log.views import collect_config

    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {"all": {"team": [2]}}, "team": [1]}),
    )
    set_orgs = Mock()
    monkeypatch.setattr(collect_config.CollectTypeService, "set_instances_organizations", set_orgs)

    response = CollectInstanceViewSet().set_organizations(make_request({"instance_ids": [instance.id], "organizations": [3]}))

    assert response.status_code == 403
    set_orgs.assert_not_called()


def test_batch_create_rejects_target_org_outside_authorized_scope(monkeypatch):
    from apps.log.views import collect_config

    batch_create = Mock()
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {"all": {"team": [2]}}, "team": [1]}),
    )
    monkeypatch.setattr(collect_config.CollectTypeService, "batch_create_collect_configs", batch_create)

    response = CollectInstanceViewSet().batch_create(make_request({"collect_type_id": 7, "instances": [{"group_ids": [3]}]}))

    assert response.status_code == 403
    batch_create.assert_not_called()


def test_batch_create_allows_authorized_target_org_scope(monkeypatch):
    from apps.log.views import collect_config

    batch_create = Mock()
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {"all": {"team": [2]}}, "team": [1]}),
    )
    monkeypatch.setattr(collect_config.CollectTypeService, "batch_create_collect_configs", batch_create)

    payload = {"collect_type_id": 7, "instances": [{"group_ids": [2]}]}
    response = CollectInstanceViewSet().batch_create(make_request(payload))

    assert response.status_code == 200
    batch_create.assert_called_once_with(payload)


def test_search_all_collect_types_respects_admin_scope_from_permission_data(monkeypatch):
    instance = make_instance(organizations=[1])
    from apps.log.views import collect_config

    search_result = {"count": 1, "items": [{"id": instance.id}]}
    collect_instance_filter = Mock(return_value=FakeQuerySet([instance]))
    service_search = Mock(return_value=search_result)

    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {"all": {"team": [1]}}, "team": [1]}),
    )
    monkeypatch.setattr(collect_config.CollectInstance.objects, "filter", collect_instance_filter)
    monkeypatch.setattr(collect_config.CollectTypeService, "search_instance_with_permission", service_search)

    response = CollectInstanceViewSet().search(make_request({"page": 1, "page_size": 10}))

    assert response.status_code == 200
    collect_instance_filter.assert_called_once_with(collectinstanceorganization__organization__in=[1])
    payload = json.loads(response.content)
    assert payload["data"]["items"][0]["permission"] == ["View", "Operate"]


def test_search_all_collect_types_excludes_current_team_scope_for_restricted_type(monkeypatch):
    instance = make_instance(organizations=[1])
    from apps.log.views import collect_config

    collect_instance_filter = Mock(return_value=FakeQuerySet([instance]))
    service_search = Mock(return_value={"count": 0, "items": []})

    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "team": [2],
                    }
                },
                "team": [1],
            }
        ),
    )
    monkeypatch.setattr(collect_config.CollectInstance.objects, "filter", collect_instance_filter)
    monkeypatch.setattr(collect_config.CollectTypeService, "search_instance_with_permission", service_search)

    response = CollectInstanceViewSet().search(make_request({"page": 1, "page_size": 10}))

    assert response.status_code == 200
    collect_instance_filter.assert_called_once()
    filter_expression = collect_instance_filter.call_args.args[0]
    assert "('collectinstanceorganization__organization__in', [2])" in str(filter_expression)
    assert "('collectinstanceorganization__organization__in', [1])" in str(filter_expression)
    payload = json.loads(response.content)
    assert payload["data"] == {"count": 0, "items": []}


def test_search_all_collect_types_falls_back_to_current_team_for_unscoped_type(monkeypatch):
    instance = make_instance(organizations=[1])
    from apps.log.views import collect_config

    search_result = {
        "count": 1,
        "items": [{"id": instance.id, "organization": [1], "collect_type_id": instance.collect_type_id}],
    }

    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {"999": {"team": [2]}}, "team": [1]}),
    )
    monkeypatch.setattr(collect_config.CollectInstance.objects, "filter", Mock(return_value=FakeQuerySet([instance])))
    monkeypatch.setattr(collect_config.CollectTypeService, "search_instance_with_permission", Mock(return_value=search_result))

    response = CollectInstanceViewSet().search(make_request({"page": 1, "page_size": 10}))

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["data"]["count"] == 1
    assert payload["data"]["items"][0]["permission"] == ["View", "Operate"]


def test_search_rejects_page_size_above_limit():
    response = CollectInstanceViewSet().search(make_request({"page": 1, "page_size": 501}))

    assert response.status_code == 400


def test_search_allows_page_size_minus_one_for_full_result():
    assert CollectInstanceViewSet._normalize_page_params({"page": 1, "page_size": -1}) == (1, -1)


def test_search_single_collect_type_merges_duplicate_instance_permissions(monkeypatch):
    instance = make_instance()
    from apps.log.views import collect_config

    search_result = {"count": 1, "items": [{"id": instance.id}]}
    permission_queryset = FakeQuerySet([instance])

    monkeypatch.setattr(
        collect_config,
        "get_permission_rules",
        Mock(
            return_value={
                "team": [1],
                "instance": [
                    {"id": instance.id, "permission": ["View"]},
                    {"id": instance.id, "permission": ["Operate"]},
                ],
            }
        ),
    )
    monkeypatch.setattr(
        "apps.core.utils.current_team_scope.permission_filter",
        Mock(return_value=permission_queryset),
    )
    monkeypatch.setattr(
        collect_config.CollectTypeService,
        "search_instance_with_permission",
        Mock(return_value=search_result),
    )

    response = CollectInstanceViewSet().search(make_request({"collect_type_id": str(instance.collect_type_id), "page": 1, "page_size": 10}))

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["data"]["items"][0]["permission"] == ["View", "Operate"]


def test_instance_update_requires_operate_permission(monkeypatch):
    instance = make_instance(organizations=[2])
    from apps.log.views import collect_config

    update_instance = Mock()
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {}, "team": [1]}),
    )
    monkeypatch.setattr(collect_config.CollectTypeService, "update_instance", update_instance)

    response = CollectInstanceViewSet().instance_update(make_request({"instance_id": instance.id, "name": "updated", "organizations": [2]}))

    assert response.status_code == 403
    update_instance.assert_not_called()


def test_instance_update_rejects_target_org_outside_authorized_scope(monkeypatch):
    instance = make_instance()
    from apps.log.views import collect_config

    update_instance = Mock()
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [{"id": instance.id, "permission": ["Operate"]}],
                    },
                    "all": {"team": [2]},
                },
                "team": [1],
            }
        ),
    )
    monkeypatch.setattr(collect_config.CollectTypeService, "update_instance", update_instance)

    response = CollectInstanceViewSet().instance_update(make_request({"instance_id": instance.id, "name": "updated", "organizations": [3]}))

    assert response.status_code == 403
    update_instance.assert_not_called()


def test_instance_update_rejects_sibling_source_before_side_effect(monkeypatch):
    instance = make_instance(organizations=[2])
    from apps.log.views import collect_config

    update_instance = Mock()
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [{"id": instance.id, "permission": ["Operate"]}],
                    }
                },
                "team": [1, 2],
            }
        ),
    )
    monkeypatch.setattr(collect_config.CollectTypeService, "update_instance", update_instance)

    response = CollectInstanceViewSet().instance_update(
        make_request(
            {
                "instance_id": instance.id,
                "name": "updated",
                "organizations": [1],
            }
        )
    )

    assert response.status_code == 403
    update_instance.assert_not_called()


def test_instance_update_allows_assignable_sibling_target(monkeypatch):
    instance = make_instance(organizations=[1])
    from apps.log.views import collect_config

    update_instance = Mock()
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [{"id": instance.id, "permission": ["Operate"]}],
                    }
                },
                "team": [1],
            }
        ),
    )
    monkeypatch.setattr(collect_config.CollectTypeService, "update_instance", update_instance)

    response = CollectInstanceViewSet().instance_update(
        make_request(
            {
                "instance_id": instance.id,
                "name": "updated",
                "organizations": [2],
            }
        )
    )

    assert response.status_code == 200
    update_instance.assert_called_once_with(instance.id, "updated", [2])


def test_instance_update_rejects_explicit_empty_organizations(monkeypatch):
    instance = make_instance(organizations=[1])
    from apps.log.views import collect_config

    update_instance = Mock()
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [{"id": instance.id, "permission": ["Operate"]}],
                    }
                },
                "team": [1],
            }
        ),
    )
    monkeypatch.setattr(collect_config.CollectTypeService, "update_instance", update_instance)

    response = CollectInstanceViewSet().instance_update(
        make_request(
            {
                "instance_id": instance.id,
                "name": "updated",
                "organizations": [],
            }
        )
    )

    assert response.status_code == 403
    update_instance.assert_not_called()


def test_instance_update_without_organizations_preserves_existing_binding(monkeypatch):
    instance = make_instance(organizations=[1])
    from apps.log.views import collect_config

    update_instance = Mock()
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [{"id": instance.id, "permission": ["Operate"]}],
                    }
                },
                "team": [1],
            }
        ),
    )
    monkeypatch.setattr(collect_config.CollectTypeService, "update_instance", update_instance)

    response = CollectInstanceViewSet().instance_update(make_request({"instance_id": instance.id, "name": "updated"}))

    assert response.status_code == 200
    update_instance.assert_called_once_with(instance.id, "updated", None)


def test_update_instance_collect_config_requires_operate_permission(monkeypatch):
    instance = make_instance(organizations=[2])
    from apps.log.views import collect_config

    update_config = Mock()
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {}, "team": [1]}),
    )
    monkeypatch.setattr(collect_config.CollectTypeService, "update_instance_config_v2", update_config)

    response = CollectConfigViewSet().update_instance_collect_config(
        make_request(
            {
                "instance_id": instance.id,
                "collect_type_id": instance.collect_type_id,
                "child": None,
                "base": None,
            }
        )
    )

    assert response.status_code == 403
    update_config.assert_not_called()


def test_update_instance_collect_config_allows_authorized_instance(monkeypatch):
    instance = make_instance()
    base_config = SimpleNamespace(
        id="config-base",
        collect_instance_id=instance.id,
        collect_instance=instance,
        is_child=False,
    )
    from apps.log.views import collect_config

    update_config = Mock()
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [{"id": instance.id, "permission": ["Operate"]}],
                    }
                },
                "team": [1],
            }
        ),
    )
    monkeypatch.setattr(
        collect_config.CollectConfig.objects,
        "filter",
        Mock(return_value=FakeQuerySet([base_config])),
    )
    monkeypatch.setattr(collect_config.CollectTypeService, "update_instance_config_v2", update_config)

    payload = {
        "instance_id": instance.id,
        "collect_type_id": instance.collect_type_id,
        "child": None,
        "base": {"id": base_config.id, "content": "key: value"},
    }
    response = CollectConfigViewSet().update_instance_collect_config(make_request(payload))

    assert response.status_code == 200
    update_config.assert_called_once_with(
        None,
        {"id": base_config.id, "content": "key: value"},
        instance.id,
        instance.collect_type_id,
    )


@pytest.mark.django_db
def test_update_instance_collect_config_rejects_foreign_config_batch_before_side_effect(
    monkeypatch,
):
    collect_type = CollectType.objects.create(
        name="idor-type",
        collector="Filebeat",
        icon="",
    )
    own_instance = CollectInstance.objects.create(
        id="idor-own",
        name="own",
        collect_type=collect_type,
    )
    foreign_instance = CollectInstance.objects.create(
        id="idor-foreign",
        name="foreign",
        collect_type=collect_type,
    )
    own_config = CollectConfig.objects.create(
        id="idor-own-child",
        collect_instance=own_instance,
        file_type="toml",
        is_child=True,
    )
    foreign_config = CollectConfig.objects.create(
        id="idor-foreign-base",
        collect_instance=foreign_instance,
        file_type="yaml",
        is_child=False,
    )
    update_config = Mock()
    monkeypatch.setattr(
        CollectInstanceViewSet,
        "_authorize_instances",
        Mock(return_value=([own_instance], None)),
    )
    monkeypatch.setattr(
        CollectTypeService,
        "update_instance_config_v2",
        update_config,
    )

    response = CollectConfigViewSet().update_instance_collect_config(
        make_request(
            {
                "instance_id": own_instance.id,
                "collect_type_id": collect_type.id,
                "child": {"id": own_config.id, "content": {"key": "value"}},
                "base": {"id": foreign_config.id, "content": {"key": "value"}},
            }
        )
    )

    assert response.status_code == 403
    update_config.assert_not_called()
    assert CollectConfig.objects.filter(
        id=foreign_config.id,
        collect_instance=foreign_instance,
        is_child=False,
    ).exists()


@pytest.mark.django_db
def test_update_instance_collect_config_rejects_invalid_config_role_before_side_effect(
    monkeypatch,
):
    collect_type = CollectType.objects.create(
        name="role-type",
        collector="Filebeat",
        icon="",
    )
    instance = CollectInstance.objects.create(
        id="role-instance",
        name="role instance",
        collect_type=collect_type,
    )
    base_config = CollectConfig.objects.create(
        id="role-base",
        collect_instance=instance,
        file_type="yaml",
        is_child=False,
    )
    update_config = Mock()
    monkeypatch.setattr(
        CollectInstanceViewSet,
        "_authorize_instances",
        Mock(return_value=([instance], None)),
    )
    monkeypatch.setattr(
        CollectTypeService,
        "update_instance_config_v2",
        update_config,
    )

    response = CollectConfigViewSet().update_instance_collect_config(
        make_request(
            {
                "instance_id": instance.id,
                "collect_type_id": collect_type.id,
                "child": {"id": base_config.id, "content": {"key": "value"}},
                "base": None,
            }
        )
    )

    assert response.status_code == 400
    update_config.assert_not_called()


def test_k8s_create_instance_rejects_target_org_outside_authorized_scope(monkeypatch):
    from apps.log.views import collect_config, k8s_collect

    create_instance = Mock()
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {}, "team": [1]}),
    )
    monkeypatch.setattr(k8s_collect.K8sLogCollectService, "create_k8s_collect_instance", create_instance)

    payload = {"collect_type_id": 7, "name": "demo", "organizations": [3]}
    response = K8sCollectViewSet().create_instance(make_request(payload))

    assert response.status_code == 403
    create_instance.assert_not_called()


def test_k8s_create_instance_requires_organizations(monkeypatch):
    from apps.log.views import k8s_collect

    create_instance = Mock()
    monkeypatch.setattr(k8s_collect.K8sLogCollectService, "create_k8s_collect_instance", create_instance)

    response = K8sCollectViewSet().create_instance(make_request({"collect_type_id": 7, "name": "demo", "organizations": []}))

    assert response.status_code == 400
    create_instance.assert_not_called()


def test_k8s_create_instance_rejects_invalid_organization(monkeypatch):
    from apps.log.views import collect_config, k8s_collect

    create_instance = Mock()
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {"all": {"team": [2]}}, "team": [1]}),
    )
    monkeypatch.setattr(k8s_collect.K8sLogCollectService, "create_k8s_collect_instance", create_instance)

    payload = {"collect_type_id": 7, "name": "demo", "organizations": [2, "bad"]}
    response = K8sCollectViewSet().create_instance(make_request(payload))

    assert response.status_code == 400
    create_instance.assert_not_called()


def test_k8s_create_instance_allows_authorized_target_org_scope(monkeypatch):
    from apps.log.views import collect_config, k8s_collect

    create_instance = Mock(return_value={"instance_id": "k8s-demo"})
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {"all": {"team": [2]}}, "team": [1]}),
    )
    monkeypatch.setattr(k8s_collect.K8sLogCollectService, "create_k8s_collect_instance", create_instance)

    payload = {"collect_type_id": 7, "name": "demo", "organizations": [2]}
    response = K8sCollectViewSet().create_instance(make_request(payload))

    assert response.status_code == 200
    create_instance.assert_called_once_with(payload)


def test_k8s_generate_install_command_requires_operate_permission(monkeypatch):
    instance = make_instance(organizations=[2])
    from apps.log.views import collect_config, k8s_collect

    generate_install_command = Mock()
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {}, "team": [1]}),
    )
    monkeypatch.setattr(k8s_collect.K8sLogCollectService, "generate_install_command", generate_install_command)

    payload = {"instance_id": instance.id, "cloud_region_id": 1}
    response = K8sCollectViewSet().generate_install_command(make_request(payload))

    assert response.status_code == 403
    generate_install_command.assert_not_called()


def test_k8s_generate_install_command_allows_authorized_instance(monkeypatch):
    instance = make_instance()
    from apps.log.views import collect_config, k8s_collect

    generate_install_command = Mock(return_value="kubectl apply")
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [{"id": instance.id, "permission": ["Operate"]}],
                    }
                },
                "team": [1],
            }
        ),
    )
    monkeypatch.setattr(k8s_collect.K8sLogCollectService, "generate_install_command", generate_install_command)

    payload = {
        "instance_id": instance.id,
        "cloud_region_id": 1,
        "runtime_profile": "standard",
        "host_log_path": "/var/log/pods",
        "docker_container_log_path": "/var/lib/docker/containers",
    }
    response = K8sCollectViewSet().generate_install_command(make_request(payload))

    assert response.status_code == 200
    generate_install_command.assert_called_once_with(
        instance.id,
        1,
        "standard",
        "/var/log/pods",
        "/var/lib/docker/containers",
    )


def test_k8s_check_collect_status_requires_view_permission(monkeypatch):
    instance = make_instance(organizations=[2])
    from apps.log.views import collect_config, k8s_collect

    check_collect_status = Mock()
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {}, "team": [1]}),
    )
    monkeypatch.setattr(k8s_collect.K8sLogCollectService, "check_collect_status", check_collect_status)

    response = K8sCollectViewSet().check_collect_status(make_request({"instance_id": instance.id}))

    assert response.status_code == 403
    check_collect_status.assert_not_called()


def test_k8s_check_collect_status_allows_instance_level_view_permission(monkeypatch):
    instance = make_instance()
    from apps.log.views import collect_config, k8s_collect

    check_collect_status = Mock(return_value=True)
    monkeypatch.setattr(
        collect_config.CollectInstance.objects,
        "filter",
        Mock(return_value=FakeQuerySet([instance])),
    )
    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "instance": [{"id": instance.id, "permission": ["View"]}],
                    }
                },
                "team": [1],
            }
        ),
    )
    monkeypatch.setattr(k8s_collect.K8sLogCollectService, "check_collect_status", check_collect_status)

    response = K8sCollectViewSet().check_collect_status(make_request({"instance_id": instance.id}))

    assert response.status_code == 200
    check_collect_status.assert_called_once_with(instance.id)
