"""Issue #3375：导入唯一性候选不得按 model_id 无上界全表加载。"""

import io
from types import SimpleNamespace

import openpyxl
import pytest

from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.utils.Import import Import
from apps.core.exceptions.base_app_exception import BaseAppException

MODULE = "apps.cmdb.services.instance"
IMPORT_MODULE = "apps.cmdb.utils.Import"
EXISTING = {"_id": 7, "inst_name": "h1", "serial": "SN-1", "model_id": "host", "port": 22}


def _make_excel(model_id, attrs_rows, data_rows):
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = model_id
    sheet.append([a["name"] for a in attrs_rows])
    sheet.append([a["type"] for a in attrs_rows])
    sheet.append([a["attr_id"] for a in attrs_rows])
    for row in data_rows:
        sheet.append(row)
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


def _query_params(call):
    name, args, kwargs = call
    if name != "query_entity":
        return None
    if len(args) >= 2:
        return args[1]
    return kwargs.get("params")


def _is_model_id_only(params):
    if not params:
        return False
    return [item.get("field") for item in params] == ["model_id"]


def _has_unique_or_name_condition(params):
    if not params:
        return False
    return any(item.get("field") != "model_id" for item in params)


def _install_shared_graph(monkeypatch, fake_graph, **returns):
    fake = fake_graph(MODULE, **returns)
    monkeypatch.setattr(f"{IMPORT_MODULE}.GraphClient", lambda *a, **k: fake)
    return fake


def _patch_import_deps(monkeypatch, attrs, unique_rules=None):
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr_v2", lambda mid: attrs)
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        lambda mid: {"model_id": mid, "model_name": "主机"},
    )
    monkeypatch.setattr(Import, "get_model_asso_map", lambda self: {})
    monkeypatch.setattr(
        f"{IMPORT_MODULE}.build_unique_rule_context",
        lambda mid: SimpleNamespace(unique_rules=unique_rules or [], attrs_by_id={}),
    )
    monkeypatch.setattr(f"{MODULE}.batch_create_change_record", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_instance_auto_relation_reconcile",
        lambda ids: None,
    )


def _query_entity_only_when_bound(label, params, **kwargs):
    if _is_model_id_only(params):
        return ([], 0)
    if _has_unique_or_name_condition(params):
        return ([EXISTING], 1)
    return ([], 0)


def _query_entity_by_inst_names(inst_names, model_id=None):
    names = set(inst_names or [])
    if "h1" in names:
        return [EXISTING]
    if "s1" in names:
        return [{"_id": 8, "inst_name": "s1", "model_id": model_id or "sw"}]
    return []


@pytest.mark.django_db
def test_inst_import_queries_unique_or_name_not_model_id_only(monkeypatch, fake_graph):
    attrs = [
        {"attr_id": "inst_name", "attr_name": "名称", "attr_type": "str", "is_required": True, "is_only": True},
        {"attr_id": "serial", "attr_name": "序列号", "attr_type": "str", "is_only": True},
    ]
    _patch_import_deps(monkeypatch, attrs)
    captured = {}

    def capture_save(self, inst_list):
        captured["exist_items"] = list(self.exist_items)
        captured["inst_list"] = inst_list
        return [{"success": True, "data": {**inst_list[0], "_id": 1}}]

    monkeypatch.setattr(Import, "inst_list_save", capture_save)
    fake = _install_shared_graph(
        monkeypatch,
        fake_graph,
        query_entity=_query_entity_only_when_bound,
        query_entity_by_inst_names=_query_entity_by_inst_names,
    )

    stream = _make_excel(
        "host",
        [
            {"name": "实例名(必填)", "type": "字符串", "attr_id": "inst_name"},
            {"name": "序列号", "type": "字符串", "attr_id": "serial"},
        ],
        [["h1", "SN-1"]],
    )
    InstanceManage.inst_import("host", stream, "admin")

    query_params = [params for params in (_query_params(call) for call in fake.calls) if params is not None]
    assert query_params, "导入应查询已有实例候选"
    assert not any(_is_model_id_only(params) for params in query_params)
    assert any(_has_unique_or_name_condition(params) for params in query_params)
    assert any(item.get("_id") == 7 for item in captured["exist_items"])


@pytest.mark.django_db
def test_inst_import_support_edit_loads_candidates_after_parse(monkeypatch, fake_graph):
    attrs = [
        {"attr_id": "inst_name", "attr_name": "名称", "attr_type": "str", "is_required": True, "is_only": True},
    ]
    _patch_import_deps(monkeypatch, attrs)
    captured = {}

    def capture_update(self, inst_list):
        captured["exist_items"] = list(self.exist_items)
        return (
            [{"success": True, "data": {**inst_list[0], "_id": 1, "model_id": "host"}}],
            [],
        )

    monkeypatch.setattr(Import, "inst_list_update", capture_update)
    fake = _install_shared_graph(
        monkeypatch,
        fake_graph,
        query_entity=_query_entity_only_when_bound,
        query_entity_by_inst_names=_query_entity_by_inst_names,
    )

    stream = _make_excel(
        "host",
        [{"name": "实例名(必填)", "type": "字符串", "attr_id": "inst_name"}],
        [["h1"]],
    )
    InstanceManage().inst_import_support_edit("host", stream, "admin")

    query_params = [params for params in (_query_params(call) for call in fake.calls) if params is not None]
    assert not any(_is_model_id_only(params) for params in query_params)
    assert any(_has_unique_or_name_condition(params) for params in query_params)
    assert any(item.get("_id") == 7 for item in captured["exist_items"])


@pytest.mark.django_db
def test_format_import_asso_data_queries_inst_names_from_file(monkeypatch, fake_graph):
    obj = Import.__new__(Import)
    obj.model_id = "host"
    obj.inst_name_id_map = {}
    obj.inst_id_name_map = {}
    obj.model_asso_map = {
        "host_conn_sw": {
            "asst_id": "conn",
            "src_model_id": "host",
            "dst_model_id": "sw",
            "model_asst_id": "host_conn_sw",
        }
    }
    fake = _install_shared_graph(
        monkeypatch,
        fake_graph,
        query_entity=_query_entity_only_when_bound,
        query_entity_by_inst_names=_query_entity_by_inst_names,
    )

    obj.format_import_asso_data({"host_conn_sw": {"h1": ["s1"]}})

    name_calls = [call for call in fake.calls if call[0] == "query_entity_by_inst_names"]
    assert name_calls, "关联映射应按文件中的 inst_name 查询"
    queried_names = set()
    for _, args, kwargs in name_calls:
        names = args[0] if args else kwargs.get("inst_names") or []
        queried_names.update(names)
    assert {"h1", "s1"} <= queried_names
    assert not any(_is_model_id_only(params) for params in (_query_params(call) for call in fake.calls) if params)
    assert obj.inst_name_id_map["host"]["h1"] == 7
    assert obj.inst_name_id_map["sw"]["s1"] == 8


@pytest.mark.django_db
def test_query_import_exist_items_uses_chunked_in_and_joint_rule(fake_graph):
    fake = fake_graph(
        MODULE,
        query_entity=_query_entity_only_when_bound,
        query_entity_by_inst_names=_query_entity_by_inst_names,
    )
    items = [
        {"inst_name": "h1", "serial": "SN-1", "ip_addr": "10.0.0.1", "cloud": 1, "port": 22},
        {"inst_name": "h2", "serial": "SN-2", "ip_addr": "10.0.0.2", "cloud": 2, "port": 23},
    ]
    check_attr_map = {
        "is_only": {"serial": "序列号", "port": "端口"},
        "unique_rules": [SimpleNamespace(field_ids=["ip_addr", "cloud"])],
    }

    rows = InstanceManage._query_import_exist_items(fake, "host", items, check_attr_map)

    query_params = [params for params in (_query_params(call) for call in fake.calls) if params is not None]
    assert query_params
    assert not any(_is_model_id_only(params) for params in query_params)
    assert any(item.get("field") == "serial" and item.get("type") == "str[]" for params in query_params for item in params)
    assert any(item.get("field") == "port" and item.get("type") == "int[]" for params in query_params for item in params)
    assert any(
        {item.get("field") for item in params} >= {"model_id", "ip_addr", "cloud"} for params in query_params
    )
    assert any(call[0] == "query_entity_by_inst_names" for call in fake.calls)
    assert any(item.get("_id") == 7 for item in rows)


@pytest.mark.django_db
def test_query_import_exist_items_rejects_over_5000_candidates(fake_graph):
    overflow = [{"_id": index, "inst_name": f"h{index}"} for index in range(5001)]

    def query_entity(label, params, **kwargs):
        if _is_model_id_only(params):
            return ([], 0)
        return (overflow, len(overflow))

    fake = fake_graph(MODULE, query_entity=query_entity, query_entity_by_inst_names=lambda *a, **k: [])
    check_attr_map = {"is_only": {"serial": "序列号"}, "unique_rules": []}

    with pytest.raises(BaseAppException, match="5000"):
        InstanceManage._query_import_exist_items(
            fake,
            "host",
            [{"inst_name": "h1", "serial": "SN-1"}],
            check_attr_map,
        )
