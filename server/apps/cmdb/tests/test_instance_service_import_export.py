"""CMDB InstanceManage 导入/导出/关联约束/下载模板覆盖测试。

对照 specs/capabilities/legacy-prd-cmdb-资产.md：实例导入/支持编辑导入、模板下载、实例导出、check_asso_mapping
四种 mapping 分支、_query_instance_map_by_ids 边界。
"""

import io

import openpyxl
import pytest

from apps.cmdb.services.instance import InstanceManage
from apps.core.exceptions.base_app_exception import BaseAppException

MODULE = "apps.cmdb.services.instance"


@pytest.fixture
def patch_side_effects(monkeypatch):
    monkeypatch.setattr(f"{MODULE}.create_change_record", lambda *a, **k: None)
    monkeypatch.setattr(f"{MODULE}.batch_create_change_record", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile",
        lambda ids: None,
    )


def _make_excel(model_id, attrs_rows, data_rows):
    """构造导入用的 Excel（3 行表头 + 数据）。"""
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = model_id
    names = [a["name"] for a in attrs_rows]
    types = [a["type"] for a in attrs_rows]
    ids = [a["attr_id"] for a in attrs_rows]
    sheet.append(names)
    sheet.append(types)
    sheet.append(ids)
    for r in data_rows:
        sheet.append(r)
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


# --------------------------------------------------------------------------
# check_asso_mapping
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_check_asso_mapping_not_found(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search",
        lambda mid: {},
    )
    with pytest.raises(BaseAppException):
        InstanceManage.check_asso_mapping({"model_asst_id": "x"})


@pytest.mark.django_db
def test_check_asso_mapping_nn(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search",
        lambda mid: {"mapping": "n:n"},
    )
    # n:n 直接返回 None，不抛
    assert InstanceManage.check_asso_mapping({"model_asst_id": "x", "src_inst_id": 1, "dst_inst_id": 2}) is None


@pytest.mark.django_db
def test_check_asso_mapping_1n_existing(monkeypatch, fake_graph):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search",
        lambda mid: {"mapping": "1:n"},
    )
    fake_graph(MODULE, query_edge=[{"_id": 1}])  # 已存在边
    with pytest.raises(BaseAppException):
        InstanceManage.check_asso_mapping({"model_asst_id": "x", "src_inst_id": 1, "dst_inst_id": 2})


@pytest.mark.django_db
def test_check_asso_mapping_1n_ok(monkeypatch, fake_graph):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search",
        lambda mid: {"mapping": "1:n"},
    )
    fg = fake_graph(MODULE, query_edge=[])
    InstanceManage.check_asso_mapping({"model_asst_id": "x", "src_inst_id": 1, "dst_inst_id": 2})
    # 至少应做了一次 query_edge 查询
    assert any(c[0] == "query_edge" for c in fg.calls)


@pytest.mark.django_db
def test_check_asso_mapping_n1_existing(monkeypatch, fake_graph):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search",
        lambda mid: {"mapping": "n:1"},
    )
    fake_graph(MODULE, query_edge=[{"_id": 1}])
    with pytest.raises(BaseAppException):
        InstanceManage.check_asso_mapping({"model_asst_id": "x", "src_inst_id": 1, "dst_inst_id": 2})


@pytest.mark.django_db
def test_check_asso_mapping_11_ok(monkeypatch, fake_graph):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search",
        lambda mid: {"mapping": "1:1"},
    )
    fg = fake_graph(MODULE, query_edge=[])
    InstanceManage.check_asso_mapping({"model_asst_id": "x", "src_inst_id": 1, "dst_inst_id": 2})
    # 至少应做了一次 query_edge 查询
    assert any(c[0] == "query_edge" for c in fg.calls)


@pytest.mark.django_db
def test_check_asso_mapping_invalid_mapping(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_info_search",
        lambda mid: {"mapping": "weird"},
    )
    with pytest.raises(BaseAppException):
        InstanceManage.check_asso_mapping({"model_asst_id": "x", "src_inst_id": 1, "dst_inst_id": 2})


# --------------------------------------------------------------------------
# _query_instance_map_by_ids
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_query_instance_map_by_ids_empty():
    assert InstanceManage._query_instance_map_by_ids(set()) == {}


@pytest.mark.django_db
def test_query_instance_map_by_ids(fake_graph):
    fake_graph(MODULE, query_entity=([{"_id": 1, "inst_name": "h1"}, {"_id": "bad"}], 2))
    out = InstanceManage._query_instance_map_by_ids({1, 2})
    assert out[1]["inst_name"] == "h1"


# --------------------------------------------------------------------------
# download_import_template
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_download_import_template(monkeypatch, fake_graph):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr_v2",
        lambda mid: [
            {"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称", "is_required": True},
        ],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_search",
        lambda mid, **kwargs: [],
    )
    stream = InstanceManage.download_import_template("host")
    data = stream.read()
    assert data[:2] == b"PK"


# --------------------------------------------------------------------------
# inst_import
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_inst_import(monkeypatch, fake_graph, patch_side_effects):
    attrs = [
        {"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称", "is_required": True},
    ]
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr_v2", lambda mid: attrs)
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: {"model_id": mid, "model_name": "主机"},
    )
    # Import 内部会调 GraphClient（在 utils.Import 模块）；用 patch 跳过
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.Import.import_inst_list",
        lambda self, fs: [{"data": {"_id": 1, "model_id": "host", "inst_name": "h1"}, "success": True}],
    )
    monkeypatch.setattr("apps.cmdb.utils.Import.Import.get_model_asso_map", lambda self: {})
    # InstanceManage 自己的 GraphClient（查 exist_items）
    fake_graph(MODULE, query_entity=([], 0))

    stream = _make_excel(
        "host",
        [
            {"name": "实例名(必填)", "type": "字符串", "attr_id": "inst_name"},
        ],
        [["h1"]],
    )
    result = InstanceManage.inst_import("host", stream, "admin")
    assert result[0]["success"] is True


# --------------------------------------------------------------------------
# inst_export
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_inst_export(monkeypatch, fake_graph):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr_v2",
        lambda mid, **kwargs: [
            {"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称", "is_required": True},
        ],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_search",
        lambda mid, **kwargs: [],
    )
    fake_graph(MODULE, query_entity=([{"_id": 1, "inst_name": "h1", "organization": [1]}], 1))
    stream = InstanceManage.inst_export("host", ids=[1], permissions_map={1: {"inst_names": []}})
    data = stream.read()
    assert data[:2] == b"PK"


@pytest.mark.django_db
def test_inst_export_no_ids(monkeypatch, fake_graph):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr_v2",
        lambda mid, **kwargs: [{"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_search",
        lambda mid, **kwargs: [],
    )
    fake_graph(MODULE, query_entity=([], 0))
    stream = InstanceManage.inst_export("host", ids=[], permissions_map={})
    data = stream.read()
    assert data[:2] == b"PK"


def test_partial_import_still_records_successful_changes(monkeypatch, fake_graph):
    from types import SimpleNamespace
    from unittest.mock import Mock

    fake_graph(MODULE, query_entity=([], 0))
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr_v2", lambda _: [])
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_info", lambda _: {"model_name": "主机"})
    successful = {"success": True, "data": {"_id": 9, "model_id": "host", "inst_name": "one"}}
    importer = SimpleNamespace(
        validation_errors=["第 5 行无效"], inst_list=[{}, {}], import_inst_list_support_edit=lambda *a, **k: ([successful], [], [])
    )
    monkeypatch.setattr(f"{MODULE}.Import", lambda *a: importer)
    audit = Mock()
    reconcile = Mock()
    monkeypatch.setattr(f"{MODULE}.batch_create_change_record", audit)
    monkeypatch.setattr("apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile", reconcile)
    result = InstanceManage().inst_import_support_edit("host", io.BytesIO(), "admin")
    assert not result["success"]
    assert audit.call_args_list[0].args[2][0]["inst_id"] == 9
    reconcile.assert_called_once_with([9])


def test_async_relation_creation_never_falls_back_to_model_wide_edge_query(monkeypatch, fake_graph):
    from apps.cmdb.services.model import ModelManage

    source = {"_id": 1, "model_id": "host", "inst_uuid": "123e4567-e89b-42d3-a456-426614174000"}
    target = {"_id": 2, "model_id": "app", "inst_uuid": "123e4567-e89b-42d3-a456-426614174001"}
    monkeypatch.setattr(InstanceManage, "query_entity_by_uuid", lambda uuid: source if uuid == source["inst_uuid"] else target)
    monkeypatch.setattr(ModelManage, "model_association_info_search", lambda key: {"mapping": "n:n", "asst_id": "belong"})
    monkeypatch.setattr(InstanceManage, "instance_association_by_asso_id", lambda _: {"src": source, "dst": target})
    monkeypatch.setattr(f"{MODULE}.create_change_record_by_asso", lambda *a, **k: None)
    graph = fake_graph(MODULE, query_edge=[], create_edge={"_id": 3})
    InstanceManage.instance_association_create_by_uuid(
        src_inst_uuid=source["inst_uuid"], dst_inst_uuid=target["inst_uuid"], model_asst_id="host_belong_app", operator="admin", bounded_lookup=True
    )
    queries = [args[1] for name, args, kwargs in graph.calls if name == "query_edge"]
    assert len(queries) == 1
    assert {item["field"] for item in queries[0]} == {"model_asst_id", "src_inst_uuid", "dst_inst_uuid"}


def test_async_relation_repeat_is_idempotent_without_graph_write(monkeypatch, fake_graph):
    src = "123e4567-e89b-42d3-a456-426614174000"
    dst = "123e4567-e89b-42d3-a456-426614174001"
    monkeypatch.setattr(InstanceManage, "query_entity_by_uuid", lambda uuid: {"_id": 1, "inst_uuid": uuid, "model_id": "host"})
    graph = fake_graph(MODULE, query_edge=[{"_id": 3}])
    result = InstanceManage.instance_association_create_by_uuid(
        src_inst_uuid=src, dst_inst_uuid=dst, model_asst_id="host_belong_host", operator="admin", bounded_lookup=True, allow_existing=True
    )
    assert result == {"already_exists": True}
    assert not [call for call in graph.calls if call[0] == "create_edge"]
