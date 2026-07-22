"""CMDB 字段分组服务覆盖测试（ORM + patch search_model_info）。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md：字段分组增删改查、排序与移动。
"""

import json

import pytest

from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.services.field_group import FieldGroupService
from apps.core.exceptions.base_app_exception import BaseAppException


@pytest.fixture
def patch_model(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda model_id: {"model_id": model_id, "attrs": "[]"} if model_id != "missing" else {},
    )


# --------------------------------------------------------------------------
# create_group
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_group(patch_model):
    group = FieldGroupService.create_group("host", "基础信息", "admin")
    assert group.group_name == "基础信息"
    assert group.order == 1


@pytest.mark.django_db
def test_create_group_blank_name(patch_model):
    with pytest.raises(BaseAppException):
        FieldGroupService.create_group("host", "  ", "admin")


@pytest.mark.django_db
def test_create_group_model_missing(patch_model):
    with pytest.raises(BaseAppException):
        FieldGroupService.create_group("missing", "g", "admin")


@pytest.mark.django_db
def test_create_group_duplicate(patch_model):
    FieldGroupService.create_group("host", "重复", "admin")
    with pytest.raises(BaseAppException):
        FieldGroupService.create_group("host", "重复", "admin")


@pytest.mark.django_db
def test_create_group_order_increments(patch_model):
    FieldGroupService.create_group("host", "g1", "admin")
    g2 = FieldGroupService.create_group("host", "g2", "admin")
    assert g2.order == 2


# --------------------------------------------------------------------------
# list_groups / validate_group_exists
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_groups(patch_model):
    FieldGroupService.create_group("host", "g1", "admin")
    FieldGroupService.create_group("host", "g2", "admin")
    groups = FieldGroupService.list_groups("host")
    assert [g.group_name for g in groups] == ["g1", "g2"]


@pytest.mark.django_db
def test_validate_group_exists(patch_model):
    FieldGroupService.create_group("host", "g1", "admin")
    # 存在则不抛异常；不存在抛异常
    FieldGroupService.validate_group_exists("host", "g1")
    with pytest.raises(BaseAppException):
        FieldGroupService.validate_group_exists("host", "missing")


# --------------------------------------------------------------------------
# move_group
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_move_group_down(patch_model):
    FieldGroupService.create_group("host", "g1", "admin")
    FieldGroupService.create_group("host", "g2", "admin")
    result = FieldGroupService.move_group("host", "g1", "down")
    assert result["success"] is True
    # g1 现在 order=2
    g1 = FieldGroup.objects.get(model_id="host", group_name="g1")
    assert g1.order == 2


@pytest.mark.django_db
def test_move_group_up_boundary(patch_model):
    FieldGroupService.create_group("host", "g1", "admin")
    FieldGroupService.create_group("host", "g2", "admin")
    with pytest.raises(BaseAppException):
        FieldGroupService.move_group("host", "g1", "up")


@pytest.mark.django_db
def test_move_group_single(patch_model):
    FieldGroupService.create_group("host", "g1", "admin")
    with pytest.raises(BaseAppException):
        FieldGroupService.move_group("host", "g1", "down")


@pytest.mark.django_db
def test_move_group_not_found(patch_model):
    FieldGroupService.create_group("host", "g1", "admin")
    FieldGroupService.create_group("host", "g2", "admin")
    with pytest.raises(BaseAppException):
        FieldGroupService.move_group("host", "nope", "down")


# --------------------------------------------------------------------------
# reorder_after_delete
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_reorder_after_delete(patch_model):
    FieldGroupService.create_group("host", "g1", "admin")
    g2 = FieldGroupService.create_group("host", "g2", "admin")
    g3 = FieldGroupService.create_group("host", "g3", "admin")
    # 删除 g2 制造 order 间隙 (1,3)
    g2.delete()
    FieldGroupService.reorder_after_delete("host")
    g3.refresh_from_db()
    assert g3.order == 2


# --------------------------------------------------------------------------
# GraphClient 驱动的方法（fake_graph 桩 set_entity_properties）
# --------------------------------------------------------------------------

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
def patch_exclude(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change", lambda model_id: None
    )


@pytest.mark.django_db
def test_update_group_rename_syncs_graph(patch_model_rich, fake_graph):
    fg = fake_graph(MODULE)
    g = FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin")
    result = FieldGroupService.update_group(g, new_group_name="网络信息")
    assert result.group_name == "网络信息"
    # 改名应触发 set_entity_properties 同步图库属性
    assert any(c[0] == "set_entity_properties" for c in fg.calls)


@pytest.mark.django_db
def test_update_group_blank_name(patch_model_rich):
    g = FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin")
    with pytest.raises(BaseAppException):
        FieldGroupService.update_group(g, new_group_name="   ")


@pytest.mark.django_db
def test_update_group_duplicate_name(patch_model_rich):
    FieldGroup.objects.create(model_id="host", group_name="硬件", order=2, created_by="admin")
    g = FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin")
    with pytest.raises(BaseAppException):
        FieldGroupService.update_group(g, new_group_name="硬件")


@pytest.mark.django_db
def test_update_group_description_only(patch_model_rich):
    g = FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin")
    result = FieldGroupService.update_group(g, description="新描述", is_collapsed=True)
    assert result.description == "新描述"
    assert result.is_collapsed is True


@pytest.mark.django_db
def test_delete_group_migrates_attrs(patch_model_rich, fake_graph):
    fg = fake_graph(MODULE)
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin")
    g2 = FieldGroup.objects.create(model_id="host", group_name="硬件", order=2, created_by="admin")
    result = FieldGroupService.delete_group(g2)
    assert result["success"] is True
    # 硬件分组下有 cpu 属性 → 迁移并写回图库
    assert any(c[0] == "set_entity_properties" for c in fg.calls)
    assert not FieldGroup.objects.filter(model_id="host", group_name="硬件").exists()


@pytest.mark.django_db
def test_delete_group_last_one_forbidden(patch_model_rich):
    g = FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin")
    with pytest.raises(BaseAppException):
        FieldGroupService.delete_group(g)


@pytest.mark.django_db
def test_get_model_with_groups(patch_model_rich):
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin", attr_orders=["ip"])
    FieldGroup.objects.create(model_id="host", group_name="硬件", order=2, created_by="admin")
    model_info = {"model_id": "host", "model_name": "主机", "attrs": _ATTRS, "unique_rules": "[]"}
    data = FieldGroupService.get_model_with_groups(model_info)
    assert data["total_groups"] == 2
    assert data["total_attrs"] == 2
    net = next(g for g in data["groups"] if g["group_name"] == "网络")
    assert net["attrs_count"] == 1
    assert net["can_move_up"] is False
    assert net["can_delete"] is True


@pytest.mark.django_db
def test_batch_update_attrs_group(patch_model_rich, patch_exclude, fake_graph):
    fake_graph(MODULE)
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin", attr_orders=["ip"])
    FieldGroup.objects.create(model_id="host", group_name="硬件", order=2, created_by="admin", attr_orders=[])
    result = FieldGroupService.batch_update_attrs_group("host", [{"attr_id": "cpu", "group_name": "网络"}])
    assert result["updated_count"] == 1
    net = FieldGroup.objects.get(model_id="host", group_name="网络")
    assert "cpu" in net.attr_orders


@pytest.mark.django_db
def test_batch_update_attrs_group_attr_missing(patch_model_rich, patch_exclude, fake_graph):
    fake_graph(MODULE)
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin")
    with pytest.raises(BaseAppException):
        FieldGroupService.batch_update_attrs_group("host", [{"attr_id": "nope", "group_name": "网络"}])


@pytest.mark.django_db
def test_update_attr_group_cross_move(patch_model_rich, patch_exclude, fake_graph):
    fake_graph(MODULE)
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin", attr_orders=["ip"])
    FieldGroup.objects.create(model_id="host", group_name="硬件", order=2, created_by="admin", attr_orders=["cpu"])
    result = FieldGroupService.update_attr_group("host", "cpu", "网络", order_id=0)
    assert result["new_group"] == "网络"
    net = FieldGroup.objects.get(model_id="host", group_name="网络")
    assert net.attr_orders[0] == "cpu"
    hw = FieldGroup.objects.get(model_id="host", group_name="硬件")
    assert "cpu" not in hw.attr_orders


@pytest.mark.django_db
def test_reorder_group_attrs(patch_model_rich):
    # 网络分组下只有 ip，校验通过
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin", attr_orders=["ip"])
    result = FieldGroupService.reorder_group_attrs("host", "网络", ["ip"])
    assert result["attr_orders"] == ["ip"]


@pytest.mark.django_db
def test_reorder_group_attrs_foreign_attr(patch_model_rich):
    FieldGroup.objects.create(model_id="host", group_name="网络", order=1, created_by="admin")
    with pytest.raises(BaseAppException):
        FieldGroupService.reorder_group_attrs("host", "网络", ["cpu"])  # cpu 属于硬件


@pytest.mark.django_db
def test_reorder_group_attrs_group_missing(patch_model_rich):
    with pytest.raises(BaseAppException):
        FieldGroupService.reorder_group_attrs("host", "不存在", ["ip"])
