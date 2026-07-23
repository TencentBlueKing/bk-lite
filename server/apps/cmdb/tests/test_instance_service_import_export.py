"""CMDB InstanceManage 导入/导出/关联约束/下载模板覆盖测试。

对照 specs/capabilities/legacy-prd-cmdb-资产.md：实例导入/支持编辑导入、模板下载、实例导出、check_asso_mapping
四种 mapping 分支、_query_instance_map_by_ids 边界。
"""

import io
import json

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
        lambda mid: [],
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
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr_v2", lambda mid: attrs
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: {"model_id": mid, "model_name": "主机"},
    )
    # Import 内部会调 GraphClient（在 utils.Import 模块）；用 patch 跳过
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.Import.import_inst_list",
        lambda self, fs: [{"data": {"_id": 1, "model_id": "host", "inst_name": "h1"}, "success": True}],
    )
    monkeypatch.setattr(
        "apps.cmdb.utils.Import.Import.get_model_asso_map", lambda self: {}
    )
    # InstanceManage 自己的 GraphClient（查 exist_items）
    fake_graph(MODULE, query_entity=([], 0))

    stream = _make_excel("host", [
        {"name": "实例名(必填)", "type": "字符串", "attr_id": "inst_name"},
    ], [["h1"]])
    result = InstanceManage.inst_import("host", stream, "admin")
    assert result[0]["success"] is True


# --------------------------------------------------------------------------
# inst_export
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_inst_export(monkeypatch, fake_graph):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr_v2",
        lambda mid: [
            {"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称", "is_required": True},
        ],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_search", lambda mid: []
    )
    fake_graph(MODULE, query_entity=([{"_id": 1, "inst_name": "h1", "organization": [1]}], 1))
    stream = InstanceManage.inst_export("host", ids=[1], permissions_map={1: {"inst_names": []}})
    data = stream.read()
    assert data[:2] == b"PK"


@pytest.mark.django_db
def test_inst_export_no_ids(monkeypatch, fake_graph):
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr_v2",
        lambda mid: [{"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称"}],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.model_association_search", lambda mid: []
    )
    fake_graph(MODULE, query_entity=([], 0))
    stream = InstanceManage.inst_export("host", ids=[], permissions_map={})
    data = stream.read()
    assert data[:2] == b"PK"
