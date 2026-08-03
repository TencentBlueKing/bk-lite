"""CMDB ModelManage 图驱动方法覆盖测试（fake_graph）。

对照 specs/capabilities/legacy-prd-cmdb-模型管理.md：模型创建、模型关联增删查、自动关联规则查询、
模型排序、模型是否存在关联/实例校验、显示字段处理。
"""

import pytest

from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException

MODULE = "apps.cmdb.services.model"


@pytest.fixture
def patch_side_effects(monkeypatch):
    monkeypatch.setattr(f"{MODULE}.create_change_record", lambda **k: None)
    monkeypatch.setattr(
        "apps.cmdb.display_field.ExcludeFieldsCache.update_on_model_change", lambda model_id: None
    )


# --------------------------------------------------------------------------
# create_model
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_model(fake_graph, patch_side_effects, monkeypatch):
    monkeypatch.setattr(
        f"{MODULE}.ClassificationManage.search_model_classification_info", lambda cid: {"_id": 50}
    )

    def _create_entity(label, data, check, exist):
        return {"_id": 9, "model_id": data["model_id"], "model_name": data["model_name"], "classification_id": data["classification_id"]}

    fake_graph(MODULE, query_entity=([], 0), create_entity=_create_entity, create_edge={"_id": 1})
    result = ModelManage.create_model(
        {"model_id": "host", "model_name": "主机", "classification_id": "net"}, username="admin"
    )
    assert result["model_id"] == "host"
    # 默认分组已建
    from apps.cmdb.models.field_group import FieldGroup

    assert FieldGroup.objects.filter(model_id="host", group_name="default").exists()


# --------------------------------------------------------------------------
# model_association_create / delete / info_search / search
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_model_association_create(fake_graph):
    fake_graph(MODULE, create_edge={"_id": 10, "model_asst_id": "a_b_c"})
    edge = ModelManage.model_association_create(src_id=1, dst_id=2, model_asst_id="a_b_c")
    assert edge["_id"] == 10


@pytest.mark.django_db
def test_model_association_create_duplicate(fake_graph):
    def _raise(*a, **k):
        raise BaseAppException("edge already exists")

    fake_graph(MODULE, create_edge=_raise)
    with pytest.raises(BaseAppException) as exc:
        ModelManage.model_association_create(src_id=1, dst_id=2)
    assert "repetition" in exc.value.message


@pytest.mark.django_db
def test_model_association_delete(fake_graph, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_rule_auto_relation_full_sync",
        lambda ids: None,
    )
    fg = fake_graph(MODULE, query_edge_by_id={"model_asst_id": "a_b_c"})
    ModelManage.model_association_delete(5)
    assert any(c[0] == "delete_edge" for c in fg.calls)


@pytest.mark.django_db
def test_model_association_info_search_found(fake_graph):
    fake_graph(MODULE, query_edge=[{"_id": 1, "model_asst_id": "a_b_c"}])
    out = ModelManage.model_association_info_search("a_b_c")
    assert out["model_asst_id"] == "a_b_c"


@pytest.mark.django_db
def test_model_association_info_search_missing(fake_graph):
    fake_graph(MODULE, query_edge=[])
    assert ModelManage.model_association_info_search("a_b_c") == {}


@pytest.mark.django_db
def test_model_association_search(fake_graph):
    fake_graph(MODULE, query_edge=[{"_id": 1}, {"_id": 2}])
    out = ModelManage.model_association_search("host")
    assert len(out) == 2


# --------------------------------------------------------------------------
# get_model_auto_relation_rules
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_model_auto_relation_rules_empty(fake_graph):
    # 关联无 auto_relation_rule 字段 → 空结果
    fake_graph(MODULE, query_edge=[{"_id": 1, "model_asst_id": "a_b_c"}])
    assert ModelManage.get_model_auto_relation_rules("host") == []


# --------------------------------------------------------------------------
# check_model_exist_association / check_model_exist_inst
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_check_model_exist_association_raises(fake_graph):
    fake_graph(MODULE, query_edge=[{"_id": 1}])
    with pytest.raises(BaseAppException):
        ModelManage.check_model_exist_association("host")


@pytest.mark.django_db
def test_check_model_exist_association_ok(fake_graph):
    fake_graph(MODULE, query_edge=[])
    # 不抛 → 表示无关联
    assert ModelManage.check_model_exist_association("host") is None


@pytest.mark.django_db
def test_check_model_exist_inst_raises(fake_graph):
    fake_graph(MODULE, query_entity=([], 3))
    with pytest.raises(BaseAppException):
        ModelManage.check_model_exist_inst("host")


@pytest.mark.django_db
def test_check_model_exist_inst_ok(fake_graph):
    fake_graph(MODULE, query_entity=([], 0))
    assert ModelManage.check_model_exist_inst("host") is None


# --------------------------------------------------------------------------
# get_max_order_id / update_model_orders
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_max_order_id_empty(fake_graph):
    fake_graph(MODULE, query_entity=([], 0))
    assert ModelManage.get_max_order_id("net") == 0


@pytest.mark.django_db
def test_get_max_order_id_value(fake_graph):
    fake_graph(MODULE, query_entity=([{"_id": 1, "order_id": 7}], 1))
    assert ModelManage.get_max_order_id("net") == 7


@pytest.mark.django_db
def test_update_model_orders(fake_graph):
    fg = fake_graph(MODULE, query_entity=([{"_id": 1, "model_id": "host"}], 1))
    assert ModelManage.update_model_orders([{"model_id": "host", "order_id": 3}]) is True
    assert any(c[0] == "set_entity_properties" for c in fg.calls)


@pytest.mark.django_db
def test_update_model_orders_model_missing(fake_graph):
    fake_graph(MODULE, query_entity=([], 0))  # count=0 → skip
    assert ModelManage.update_model_orders([{"model_id": "absent", "order_id": 3}]) is True


# --------------------------------------------------------------------------
# _add_display_field_to_attrs / _remove_display_field_from_attrs（纯逻辑）
# --------------------------------------------------------------------------


def test_add_display_field_to_attrs():
    attrs = [{"attr_id": "org", "attr_type": "organization"}]
    ModelManage._add_display_field_to_attrs(attrs, attrs[0], "host", is_pre=True)
    # 应追加 org_display 字段
    assert any(a.get("attr_id") == "org_display" for a in attrs)


def test_remove_display_field_from_attrs():
    attrs = [
        {"attr_id": "org", "attr_type": "organization"},
        {"attr_id": "org_display", "is_display_field": True},
    ]
    new_attrs, removed = ModelManage._remove_display_field_from_attrs(attrs, "org")
    assert removed is True
    assert all(a.get("attr_id") != "org_display" for a in new_attrs)


# --------------------------------------------------------------------------
# update_model_attr / delete_model_attr / update_enum_instances_display
# --------------------------------------------------------------------------

import json  # noqa: E402


def _echo_set_entity(label, ids, properties, *a, **k):
    return [{"_id": ids[0], "model_id": "host", "model_name": "主机", "attrs": properties["attrs"]}]


_ATTRS_JSON = json.dumps(
    [
        {"attr_id": "name", "attr_type": "str", "attr_name": "名称", "is_required": True,
         "editable": True, "option": [], "user_prompt": ""},
    ]
)

_SYSTEM_ATTRS_JSON = json.dumps(
    [
        {"attr_id": "organization", "attr_type": "organization", "attr_name": "所属组织", "is_required": True,
         "editable": True, "option": [], "user_prompt": "实例所属的组织", "attr_group": "default", "is_pre": True},
    ]
)


@pytest.mark.django_db
def test_update_model_attr_ok(fake_graph, patch_side_effects, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.guard_attr_change_against_unique_rules", lambda *a, **k: None)
    fake_graph(
        MODULE,
        query_entity=([{"_id": 1, "model_id": "host", "model_name": "主机", "attrs": _ATTRS_JSON}], 1),
        set_entity_properties=_echo_set_entity,
    )
    attr_info = {
        "attr_id": "name", "attr_type": "str", "attr_name": "名称2", "is_required": True,
        "editable": True, "option": [], "user_prompt": "提示", "attr_group": "default",
    }
    result = ModelManage.update_model_attr("host", attr_info)
    assert result["attr_name"] == "名称2"


@pytest.mark.django_db
def test_update_model_attr_model_missing(fake_graph):
    fake_graph(MODULE, query_entity=([], 0))
    with pytest.raises(BaseAppException):
        ModelManage.update_model_attr("host", {"attr_id": "name"})


@pytest.mark.django_db
def test_update_model_attr_attr_missing(fake_graph):
    fake_graph(MODULE, query_entity=([{"_id": 1, "model_id": "host", "attrs": "[]"}], 1))
    with pytest.raises(BaseAppException):
        ModelManage.update_model_attr("host", {"attr_id": "ghost"})


@pytest.mark.django_db
def test_update_model_attr_rejects_organization(fake_graph, patch_side_effects, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.guard_attr_change_against_unique_rules", lambda *a, **k: None)
    fg = fake_graph(
        MODULE,
        query_entity=([{"_id": 1, "model_id": "host", "model_name": "主机", "attrs": _SYSTEM_ATTRS_JSON}], 1),
        set_entity_properties=_echo_set_entity,
    )
    attr_info = {
        "attr_id": "organization", "attr_type": "organization", "attr_name": "组织",
        "is_required": False, "editable": False, "option": [], "user_prompt": "",
        "attr_group": "default",
    }
    with pytest.raises(BaseAppException) as exc:
        ModelManage.update_model_attr("host", attr_info)
    assert "organization" in exc.value.message
    assert not any(c[0] == "set_entity_properties" for c in fg.calls)


@pytest.mark.django_db
def test_delete_model_attr_ok(fake_graph, patch_side_effects, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.guard_attr_change_against_unique_rules", lambda *a, **k: None)
    fg = fake_graph(
        MODULE,
        query_entity=([{"_id": 1, "model_id": "host", "model_name": "主机", "attrs": _ATTRS_JSON}], 1),
        set_entity_properties=_echo_set_entity,
    )
    result = ModelManage.delete_model_attr("host", "name")
    assert all(a["attr_id"] != "name" for a in result)
    assert any(c[0] == "remove_entitys_properties" for c in fg.calls)


@pytest.mark.django_db
def test_delete_model_attr_model_missing(fake_graph, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.guard_attr_change_against_unique_rules", lambda *a, **k: None)
    fake_graph(MODULE, query_entity=([], 0))
    with pytest.raises(BaseAppException):
        ModelManage.delete_model_attr("host", "name")


@pytest.mark.django_db
def test_delete_model_attr_rejects_organization(fake_graph, patch_side_effects, monkeypatch):
    monkeypatch.setattr(f"{MODULE}.guard_attr_change_against_unique_rules", lambda *a, **k: None)
    fg = fake_graph(
        MODULE,
        query_entity=([{"_id": 1, "model_id": "host", "model_name": "主机", "attrs": _SYSTEM_ATTRS_JSON}], 1),
        set_entity_properties=_echo_set_entity,
    )
    with pytest.raises(BaseAppException) as exc:
        ModelManage.delete_model_attr("host", "organization")
    assert "organization" in exc.value.message
    assert not any(c[0] == "set_entity_properties" for c in fg.calls)
    assert not any(c[0] == "remove_entitys_properties" for c in fg.calls)


@pytest.mark.django_db
def test_update_enum_instances_display(fake_graph):
    fg = fake_graph(
        MODULE,
        query_entity=(
            [
                {"_id": 1, "status": "1"},
                {"_id": 2},
                {"_id": 3, "status": None},
                {"_id": 4, "status": ""},
                {"_id": 5, "status": []},
            ],
            5,
        ),
    )
    count = ModelManage.update_enum_instances_display("host", "status", [{"id": "1", "name": "运行"}])
    # 只有实例 1 含 status → 更新 1 个
    assert count == 1
    update_call = next(c for c in fg.calls if c[0] == "batch_update_node_property_values")
    assert update_call[1] == (
        "instance",
        "status_display",
        [{"id": 1, "value": "运行"}],
    )


def test_update_enum_instances_display_backend_failure_is_non_blocking(fake_graph):
    def _raise(*args, **kwargs):
        raise RuntimeError("graph unavailable")

    fake_graph(
        MODULE,
        query_entity=([{"_id": 1, "status": "1"}, {"_id": 2, "status": "2"}], 2),
        batch_update_node_property_values=_raise,
    )

    count = ModelManage.update_enum_instances_display(
        "host",
        "status",
        [{"id": "1", "name": "运行"}, {"id": "2", "name": "停止"}],
    )

    assert count == 0


def test_update_enum_instances_display_batches_1000_values_once(fake_graph):
    instances = [{"_id": index, "status": "1" if index % 2 else ["2", "1"]} for index in range(1, 1001)]
    fg = fake_graph(
        MODULE,
        query_entity=_paged_query_entity(instances),
    )

    count = ModelManage.update_enum_instances_display(
        "host",
        "status",
        [{"id": "1", "name": "运行"}, {"id": "2", "name": "停止"}],
    )

    assert count == 1000
    update_calls = [call for call in fg.calls if call[0] in {"batch_update_node_properties", "batch_update_node_property_values"}]
    assert len(update_calls) == 1
    assert update_calls[0][0] == "batch_update_node_property_values"
    assert update_calls[0][1] == (
        "instance",
        "status_display",
        [
            {
                "id": index,
                "value": "运行" if index % 2 else "停止, 运行",
            }
            for index in range(1, 1001)
        ],
    )


def _paged_query_entity(instances, delete_after_first=False):
    call_count = 0

    def _query(label, params, page=None, **kwargs):
        nonlocal call_count
        call_count += 1
        last_id = next(
            (item["value"] for item in params if item["type"] == "id>"),
            None,
        )
        candidates = [
            instance
            for instance in instances
            if last_id is None or instance["_id"] > last_id
        ]
        start = page["skip"]
        end = start + page["limit"]
        result = candidates[start:end]
        if delete_after_first and call_count == 1:
            instances[:] = [instance for instance in instances if instance["_id"] != 1]
        return result, None

    return _query


def test_update_enum_instances_display_pages_without_unbounded_graph_writes(
    fake_graph,
):
    instances = [{"_id": 1}]
    instances.extend({"_id": index, "status": "1"} for index in range(2, 1003))
    fg = fake_graph(
        MODULE,
        query_entity=_paged_query_entity(instances),
    )

    count = ModelManage.update_enum_instances_display(
        "host",
        "status",
        [{"id": "1", "name": "运行"}],
    )

    assert count == 1001
    update_calls = [call for call in fg.calls if call[0] == "batch_update_node_property_values"]
    assert [len(call[1][2]) for call in update_calls] == [1000, 1]
    query_calls = [call for call in fg.calls if call[0] == "query_entity"]
    assert len(query_calls) == 2
    assert query_calls[0][2] == {
        "page": {"skip": 0, "limit": 1000},
        "include_count": False,
    }
    assert query_calls[1][1][1][-1] == {
        "field": "id",
        "type": "id>",
        "value": 1000,
    }


def test_update_enum_instances_display_keyset_does_not_skip_after_delete(
    fake_graph,
):
    instances = [{"_id": index, "status": "1"} for index in range(1, 1002)]
    fg = fake_graph(
        MODULE,
        query_entity=_paged_query_entity(instances, delete_after_first=True),
    )

    count = ModelManage.update_enum_instances_display(
        "host",
        "status",
        [{"id": "1", "name": "运行"}],
    )

    assert count == 1001
    update_calls = [call for call in fg.calls if call[0] == "batch_update_node_property_values"]
    assert [len(call[1][2]) for call in update_calls] == [1000, 1]
    assert update_calls[-1][1][2] == [{"id": 1001, "value": "运行"}]


def test_rebuild_file_instances_display_backfills_stem(fake_graph):
    # 实例 1 有附件但无 _display（历史数据）；实例 2 无附件值
    instances = [{"_id": 1, "doc": [{"name": "report.pdf"}]}, {"_id": 2}]
    fg = fake_graph(
        MODULE,
        query_entity=_paged_query_entity(instances),
    )
    count = ModelManage.rebuild_file_instances_display("host", "doc")
    # 只有实例 1 含 doc → 回填 1 个
    assert count == 1
    update_calls = [
        c for c in fg.calls if c[0] == "batch_update_node_property_values"
    ]
    assert len(update_calls) == 1
    # 写入的是文件名词干（去扩展名），而非原始元数据 JSON
    assert update_calls[0][1] == (
        "instance",
        "doc_display",
        [{"id": 1, "value": "report"}],
    )


def test_rebuild_file_instances_display_batches_1000_distinct_values_once(
    fake_graph,
):
    instances = [{"_id": 1}]
    instances.extend(
        {"_id": index, "doc": [{"name": f"report-{index}.pdf"}]}
        for index in range(2, 1002)
    )
    instances.append({"_id": 1002, "doc": []})
    fg = fake_graph(
        MODULE,
        query_entity=_paged_query_entity(instances),
    )

    count = ModelManage.rebuild_file_instances_display("host", "doc")

    assert count == 1000
    update_calls = [
        call
        for call in fg.calls
        if call[0] == "batch_update_node_property_values"
    ]
    assert len(update_calls) == 1
    assert update_calls[0][1][0:2] == ("instance", "doc_display")
    assert update_calls[0][1][2] == [
        {"id": index, "value": f"report-{index}"}
        for index in range(2, 1002)
    ]
    assert not any(
        call[0] == "batch_update_node_properties" for call in fg.calls
    )


def test_rebuild_file_instances_display_pages_without_unbounded_graph_writes(
    fake_graph,
):
    instances = [
        {"_id": index, "doc": [{"name": f"report-{index}.pdf"}]}
        for index in range(1, 1002)
    ]
    fg = fake_graph(
        MODULE,
        query_entity=_paged_query_entity(instances),
    )

    count = ModelManage.rebuild_file_instances_display("host", "doc")

    assert count == 1001
    update_calls = [
        call
        for call in fg.calls
        if call[0] == "batch_update_node_property_values"
    ]
    assert [len(call[1][2]) for call in update_calls] == [1000, 1]


def test_rebuild_file_instances_display_keyset_does_not_skip_after_delete(
    fake_graph,
):
    instances = [
        {"_id": index, "doc": [{"name": f"report-{index}.pdf"}]}
        for index in range(1, 1002)
    ]
    fg = fake_graph(
        MODULE,
        query_entity=_paged_query_entity(instances, delete_after_first=True),
    )

    count = ModelManage.rebuild_file_instances_display("host", "doc")

    assert count == 1001
    update_calls = [
        call
        for call in fg.calls
        if call[0] == "batch_update_node_property_values"
    ]
    assert [len(call[1][2]) for call in update_calls] == [1000, 1]
    assert update_calls[-1][1][2] == [{"id": 1001, "value": "report-1001"}]


def test_rebuild_file_instances_display_no_instances(fake_graph):
    fg = fake_graph(MODULE, query_entity=_paged_query_entity([]))
    count = ModelManage.rebuild_file_instances_display("host", "doc")
    assert count == 0
    assert not any(
        c[0] in {"batch_update_node_properties", "batch_update_node_property_values"}
        for c in fg.calls
    )


def test_rebuild_file_instances_display_backend_failure_is_non_blocking(
    fake_graph,
):
    def _raise(*args, **kwargs):
        raise RuntimeError("graph unavailable")

    fake_graph(
        MODULE,
        query_entity=_paged_query_entity(
            [
                {"_id": 1, "doc": [{"name": "report.pdf"}]},
                {"_id": 2, "doc": [{"name": "photo.png"}]},
            ]
        ),
        batch_update_node_property_values=_raise,
    )

    assert ModelManage.rebuild_file_instances_display("host", "doc") == 0
