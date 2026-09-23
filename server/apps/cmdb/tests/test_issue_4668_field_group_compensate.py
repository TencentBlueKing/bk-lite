"""Issue 4668：字段分组跨存储写入失败时必须补偿回滚。

batch_update_attrs_group / update_attr_group 先写 FalkorDB attrs，再刷新缓存，
再 FieldGroup.save attr_orders。SQL 失败时图与 SQL 必须回到操作前快照。
"""

import json

import pytest

from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.services.field_group import FieldGroupService
from apps.core.exceptions.base_app_exception import BaseAppException

MODULE = "apps.cmdb.services.field_group"

_ATTRS = json.dumps(
    [
        {"attr_id": "ip", "attr_group": "网络", "attr_name": "IP"},
        {"attr_id": "cpu", "attr_group": "硬件", "attr_name": "CPU"},
    ]
)


@pytest.fixture
def patch_model_rich(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda model_id: {"model_id": model_id, "model_name": "主机", "_id": 1, "attrs": _ATTRS},
    )


@pytest.fixture
def invalidate_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.invalidate_model_attrs",
        lambda model_id: calls.append(model_id),
    )
    return calls


def _written_attrs(fake):
    writes = [c for c in fake.calls if c[0] == "set_entity_properties"]
    return [json.loads(c[1][2]["attrs"]) for c in writes]


def _attr_group(attrs, attr_id):
    return next(item["attr_group"] for item in attrs if item["attr_id"] == attr_id)


def _seed_groups():
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin", attr_orders=["ip"])
    FieldGroup.objects.create(model_id="host", group_name="硬件", order=2, created_by="admin", attr_orders=["cpu"])


def _fail_when_saving_new_attr_orders(monkeypatch):
    """只拦截跨组移动后的新 attr_orders，补偿回写原快照仍可 save。"""
    original_save = FieldGroup.save

    def boom_save(self, *args, **kwargs):
        orders = self.attr_orders or []
        if getattr(self, "group_name", None) == "网络" and "cpu" in orders:
            raise RuntimeError("forced sql fail")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(FieldGroup, "save", boom_save)


@pytest.mark.django_db
def test_batch_update_sql_fail_restores_graph_and_attr_orders(patch_model_rich, invalidate_calls, fake_graph, monkeypatch):
    fake = fake_graph(MODULE)
    _seed_groups()
    _fail_when_saving_new_attr_orders(monkeypatch)

    with pytest.raises(RuntimeError, match="forced sql fail"):
        FieldGroupService.batch_update_attrs_group(
            "host",
            [
                {"attr_id": "cpu", "group_name": "网络"},
                {"attr_id": "ip", "group_name": "硬件"},
            ],
        )

    writes = _written_attrs(fake)
    assert writes, "图写入应发生"
    assert _attr_group(writes[0], "cpu") == "网络"
    assert _attr_group(writes[0], "ip") == "硬件"
    assert len(writes) >= 2, "SQL 失败后必须回写图快照"
    assert _attr_group(writes[-1], "cpu") == "硬件"
    assert _attr_group(writes[-1], "ip") == "网络"

    net = FieldGroup.objects.get(model_id="host", group_name="网络")
    hw = FieldGroup.objects.get(model_id="host", group_name="硬件")
    assert net.attr_orders == ["ip"]
    assert hw.attr_orders == ["cpu"]
    assert "host" in invalidate_calls


@pytest.mark.django_db
def test_update_attr_group_sql_fail_restores_graph_and_attr_orders(patch_model_rich, invalidate_calls, fake_graph, monkeypatch):
    fake = fake_graph(MODULE)
    _seed_groups()
    _fail_when_saving_new_attr_orders(monkeypatch)

    with pytest.raises(RuntimeError, match="forced sql fail"):
        FieldGroupService.update_attr_group("host", "cpu", "网络", order_id=0)

    writes = _written_attrs(fake)
    assert writes, "图写入应发生"
    assert _attr_group(writes[0], "cpu") == "网络"
    assert len(writes) >= 2, "旧分组 save 成功、新分组 save 失败后必须回写图快照"
    assert _attr_group(writes[-1], "cpu") == "硬件"

    net = FieldGroup.objects.get(model_id="host", group_name="网络")
    hw = FieldGroup.objects.get(model_id="host", group_name="硬件")
    assert net.attr_orders == ["ip"]
    assert hw.attr_orders == ["cpu"]
    assert "host" in invalidate_calls


@pytest.mark.django_db
def test_batch_update_success_keeps_graph_and_sql_consistent(patch_model_rich, invalidate_calls, fake_graph):
    fake = fake_graph(MODULE)
    _seed_groups()

    result = FieldGroupService.batch_update_attrs_group("host", [{"attr_id": "cpu", "group_name": "网络"}])

    assert result["updated_count"] == 1
    writes = _written_attrs(fake)
    assert len(writes) == 1
    assert _attr_group(writes[0], "cpu") == "网络"
    net = FieldGroup.objects.get(model_id="host", group_name="网络")
    assert net.attr_orders == ["ip", "cpu"]
    assert invalidate_calls == ["host"]


@pytest.mark.django_db
def test_update_attr_group_success_keeps_graph_and_sql_consistent(patch_model_rich, invalidate_calls, fake_graph):
    fake = fake_graph(MODULE)
    _seed_groups()

    result = FieldGroupService.update_attr_group("host", "cpu", "网络", order_id=0)

    assert result["new_group"] == "网络"
    writes = _written_attrs(fake)
    assert len(writes) == 1
    assert _attr_group(writes[0], "cpu") == "网络"
    net = FieldGroup.objects.get(model_id="host", group_name="网络")
    hw = FieldGroup.objects.get(model_id="host", group_name="硬件")
    assert net.attr_orders[0] == "cpu"
    assert "cpu" not in hw.attr_orders
    assert invalidate_calls == ["host"]


@pytest.mark.django_db
def test_batch_update_missing_attr_fails_before_graph(patch_model_rich, fake_graph):
    fake = fake_graph(MODULE)
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin")

    with pytest.raises(BaseAppException, match="字段'nope'不存在"):
        FieldGroupService.batch_update_attrs_group("host", [{"attr_id": "nope", "group_name": "网络"}])

    assert not any(c[0] == "set_entity_properties" for c in fake.calls)


@pytest.mark.django_db
def test_update_attr_group_missing_attr_fails_before_graph(patch_model_rich, fake_graph):
    fake = fake_graph(MODULE)
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin")

    with pytest.raises(BaseAppException, match="字段'nope'不存在"):
        FieldGroupService.update_attr_group("host", "nope", "网络")

    assert not any(c[0] == "set_entity_properties" for c in fake.calls)


@pytest.mark.django_db
def test_compensate_fail_mentions_incomplete_rollback(patch_model_rich, invalidate_calls, fake_graph, monkeypatch):
    write_count = {"n": 0}

    def flaky_set(*args, **kwargs):
        write_count["n"] += 1
        if write_count["n"] >= 2:
            raise RuntimeError("graph restore fail")
        return {}

    fake = fake_graph(MODULE, set_entity_properties=flaky_set)
    _seed_groups()

    def boom_save(self, *args, **kwargs):
        raise RuntimeError("forced sql fail")

    monkeypatch.setattr(FieldGroup, "save", boom_save)

    with pytest.raises(BaseAppException, match="回滚可能未完成"):
        FieldGroupService.batch_update_attrs_group("host", [{"attr_id": "cpu", "group_name": "网络"}])

    assert write_count["n"] >= 2
    assert fake.calls
