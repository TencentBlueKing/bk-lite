import json
from types import SimpleNamespace
from unittest.mock import Mock

from apps.log.views.collect_config import CollectConfigViewSet, CollectInstanceViewSet


class FakeQuerySet(list):
    def distinct(self):
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
        collectinstanceorganization_set=FakeOrganizations([SimpleNamespace(organization=org) for org in organizations or [2]]),
    )


def test_remove_collect_instance_requires_operate_permission(monkeypatch):
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
        Mock(return_value={"data": {}, "team": [1]}),
    )
    node_mgmt = Mock()
    monkeypatch.setattr(collect_config, "NodeMgmt", node_mgmt)

    response = CollectInstanceViewSet().remove_collect_instance(make_request({"instance_ids": [instance.id]}))

    assert response.status_code == 403
    node_mgmt.assert_not_called()


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
        Mock(return_value={"data": {"all": {"team": [2]}}, "team": [1]}),
    )

    response = CollectInstanceViewSet().remove_collect_instance(make_request({"instance_ids": [instance.id]}))

    assert response.status_code == 200
    assert getattr(config_qs, "deleted", False)
    assert getattr(instance_delete_qs, "deleted", False)


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
    instance = make_instance()
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
    instance = make_instance(organizations=[2])
    from apps.log.views import collect_config

    search_result = {"count": 1, "items": [{"id": instance.id}]}
    collect_instance_filter = Mock(return_value=FakeQuerySet([instance]))
    service_search = Mock(return_value=search_result)

    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(return_value={"data": {"all": {"team": [2]}}, "team": [1]}),
    )
    monkeypatch.setattr(collect_config.CollectInstance.objects, "filter", collect_instance_filter)
    monkeypatch.setattr(collect_config.CollectTypeService, "search_instance_with_permission", service_search)

    response = CollectInstanceViewSet().search(make_request({"page": 1, "page_size": 10}))

    assert response.status_code == 200
    collect_instance_filter.assert_called_once_with(collectinstanceorganization__organization__in={2})
    payload = json.loads(response.content)
    assert payload["data"]["items"][0]["permission"] == ["View", "Operate"]


def test_search_all_collect_types_uses_database_scope_before_pagination(monkeypatch):
    instance = make_instance(organizations=[2])
    from apps.log.views import collect_config

    search_result = {
        "count": 1,
        "items": [
            {
                "id": instance.id,
                "collect_type_id": instance.collect_type_id,
                "organization": [2],
            }
        ],
    }
    collect_instance_filter = Mock(return_value=FakeQuerySet([instance]))
    service_search = Mock(return_value=search_result)

    monkeypatch.setattr(
        collect_config,
        "get_permissions_rules",
        Mock(
            return_value={
                "data": {
                    str(instance.collect_type_id): {
                        "team": [2],
                        "instance": [{"id": instance.id, "permission": ["View"]}],
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
    service_search.assert_called_once()
    payload = json.loads(response.content)
    assert payload["data"]["items"][0]["permission"] == ["View"]


def test_search_rejects_unbounded_page_size():
    response = CollectInstanceViewSet().search(make_request({"page": 1, "page_size": 100000}))

    assert response.status_code == 400


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
    monkeypatch.setattr(collect_config, "permission_filter", Mock(return_value=permission_queryset))
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


def test_update_instance_collect_config_requires_operate_permission(monkeypatch):
    instance = make_instance()
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
    monkeypatch.setattr(collect_config.CollectTypeService, "update_instance_config_v2", update_config)

    payload = {
        "instance_id": instance.id,
        "collect_type_id": instance.collect_type_id,
        "child": None,
        "base": {"content": "key: value"},
    }
    response = CollectConfigViewSet().update_instance_collect_config(make_request(payload))

    assert response.status_code == 200
    update_config.assert_called_once_with(None, {"content": "key: value"}, instance.id, instance.collect_type_id)
