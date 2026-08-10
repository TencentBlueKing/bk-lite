from types import SimpleNamespace

from apps.log.services.collect_type import CollectTypeService


class FakeQuerySet:
    def __init__(self, instances):
        self.instances = instances

    def filter(self, **kwargs):
        collect_type_id = kwargs.get("collect_type_id")
        if collect_type_id:
            return FakeQuerySet([item for item in self.instances if item.collect_type_id == collect_type_id])

        name = kwargs.get("name__icontains")
        if name:
            return FakeQuerySet([item for item in self.instances if name in item.name])

        return self

    def distinct(self):
        return self

    def select_related(self, *args):
        return self

    def count(self):
        return len(self.instances)

    def __getitem__(self, value):
        return self.instances[value]


class FakeValuesListManager:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, **kwargs):
        ids = set(kwargs.get("collect_instance_id__in", []))
        return FakeValuesListQuery([row for row in self.rows if row[0] in ids])


class FakeValuesListQuery:
    def __init__(self, rows):
        self.rows = rows

    def values_list(self, *args):
        return self.rows


def test_search_instance_uses_current_page_node_lookup(monkeypatch):
    instances = [
        SimpleNamespace(
            id=f"inst-{idx}",
            name=f"instance-{idx}",
            node_id=f"node-{idx}",
            collect_type_id="ctype",
            collect_type=SimpleNamespace(name="file", collector="Vector"),
        )
        for idx in range(1, 6)
    ]
    requested_node_ids = []

    class FakeNodeMgmt:
        def get_node_names_by_ids(self, node_ids):
            requested_node_ids.extend(node_ids)
            return [{"id": node_id, "name": f"name-{node_id}"} for node_id in node_ids]

    monkeypatch.setattr(
        "apps.log.services.collect_type.CollectInstanceOrganization",
        SimpleNamespace(objects=FakeValuesListManager([("inst-3", 1), ("inst-4", 2)])),
    )
    monkeypatch.setattr(
        "apps.log.services.collect_type.CollectConfig",
        SimpleNamespace(objects=FakeValuesListManager([("inst-3", "conf-3"), ("inst-4", "conf-4")])),
    )
    monkeypatch.setattr("apps.log.services.collect_type.NodeMgmt", FakeNodeMgmt)

    result = CollectTypeService.search_instance_with_permission(
        collect_type_id=None,
        name=None,
        page=2,
        page_size=2,
        queryset=FakeQuerySet(instances),
        visible_organization_ids={1, 2},
    )

    assert requested_node_ids == ["node-3", "node-4"]
    assert result["count"] == 5
    assert [item["node_name"] for item in result["items"]] == ["name-node-3", "name-node-4"]


def test_search_instance_with_page_size_minus_one_returns_all_items(monkeypatch):
    instances = [
        SimpleNamespace(
            id=f"inst-{idx}",
            name=f"instance-{idx}",
            node_id=f"node-{idx}",
            collect_type_id="ctype",
            collect_type=SimpleNamespace(name="file", collector="Vector"),
        )
        for idx in range(1, 4)
    ]
    requested_node_ids = []

    class FakeNodeMgmt:
        def get_node_names_by_ids(self, node_ids):
            requested_node_ids.extend(node_ids)
            return [{"id": node_id, "name": f"name-{node_id}"} for node_id in node_ids]

    monkeypatch.setattr(
        "apps.log.services.collect_type.CollectInstanceOrganization",
        SimpleNamespace(objects=FakeValuesListManager([])),
    )
    monkeypatch.setattr(
        "apps.log.services.collect_type.CollectConfig",
        SimpleNamespace(objects=FakeValuesListManager([])),
    )
    monkeypatch.setattr("apps.log.services.collect_type.NodeMgmt", FakeNodeMgmt)

    result = CollectTypeService.search_instance_with_permission(
        collect_type_id=None,
        name=None,
        page=1,
        page_size=-1,
        queryset=FakeQuerySet(instances),
        visible_organization_ids={1},
    )

    assert requested_node_ids == ["node-1", "node-2", "node-3"]
    assert result["count"] == 3
    assert [item["id"] for item in result["items"]] == ["inst-1", "inst-2", "inst-3"]
