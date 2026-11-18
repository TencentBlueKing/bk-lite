"""关联快捷筛选开关：种子默认、Excel 列、导入写到已有关联、导出带回。"""

import pandas as pd
import pytest

from apps.cmdb.graph.advanced_filter import AdvancedFilterError, compile_advanced_filter, resolve_relation_filters
from apps.cmdb.graph.format_type import ParameterCollector
from apps.cmdb.model_migrate.migrete_service import ModelMigrate
from apps.cmdb.model_migrate.quick_filter import (
    QUICK_FILTER_FIELD,
    parse_quick_filter_cell,
    quick_filter_ends,
    quick_filter_from_row,
    seed_quick_filter,
)
from apps.cmdb.tests.test_migrate_display_slice import _patch_graph

MODEL_CONFIG = "apps/cmdb/support-files/model_config.xlsx"

pytestmark = pytest.mark.unit


def test_blank_and_unknown_cells_stay_off():
    assert parse_quick_filter_cell(None) is False
    assert parse_quick_filter_cell("") is False
    assert parse_quick_filter_cell("maybe") is False
    assert parse_quick_filter_cell(True) is True
    assert parse_quick_filter_cell("是") is True
    assert parse_quick_filter_cell(0) is False
    assert quick_filter_from_row({"src_model_id": "host"}) is None


def test_seed_turns_on_the_first_batch_only():
    assert seed_quick_filter("rack", "contains", "switch") is True
    assert seed_quick_filter("rack", "contains", "physcial_server") is True
    assert seed_quick_filter("server_room", "run", "rack") is True
    assert seed_quick_filter("application", "run", "host") is True
    assert seed_quick_filter("qcloud_cvm", "belong", "qcloud") is True
    assert seed_quick_filter("vmware_esxi", "group", "vmware_vc") is True
    assert seed_quick_filter("manageone_server", "belong", "manageone_cloud") is True

    assert seed_quick_filter("application", "connect", "mysql") is False
    assert seed_quick_filter("host", "run", "mysql") is False
    assert seed_quick_filter("hwcloud_subnet", "belong", "hwcloud_vpc") is False
    assert seed_quick_filter("manageone_cloud", "belong", "manageone") is False
    assert seed_quick_filter("nutanixhci_vm", "belong", "nutanixhci_host") is False
    assert seed_quick_filter("datacenter", "run", "server_room") is False


def test_model_config_quick_filter_matches_seed():
    book = pd.ExcelFile(MODEL_CONFIG)
    seen = 0
    enabled = []
    for sheet_name in book.sheet_names:
        if not sheet_name.startswith("asso-"):
            continue
        frame = pd.read_excel(book, sheet_name=sheet_name, header=1).fillna("")
        assert QUICK_FILTER_FIELD in frame.columns
        for row in frame.to_dict("records"):
            src = str(row.get("src_model_id") or "").strip()
            if not src:
                continue
            asst = str(row.get("asst_id") or "").strip()
            dst = str(row.get("dst_model_id") or "").strip()
            expected = seed_quick_filter(src, asst, dst)
            assert parse_quick_filter_cell(row.get(QUICK_FILTER_FIELD)) is expected
            seen += 1
            if expected:
                enabled.append((src, asst, dst))

    assert seen > 0
    assert ("rack", "contains", "switch") in enabled
    assert ("server_room", "run", "rack") in enabled
    assert ("application", "run", "host") in enabled
    assert ("qcloud_cvm", "belong", "qcloud") in enabled


def test_migrate_writes_quick_filter_onto_existing_edge(monkeypatch):
    cfg = {
        "models": [{"model_id": "rack"}, {"model_id": "switch"}],
        "asso-rack": [
            {
                "src_model_id": "rack",
                "dst_model_id": "switch",
                "asst_id": "contains",
                "mapping": "1:n",
                QUICK_FILTER_FIELD: True,
            }
        ],
    }
    migrator = ModelMigrate.__new__(ModelMigrate)
    migrator.model_config = cfg
    migrator.is_pre = True
    fake = _patch_graph(
        monkeypatch,
        "apps.cmdb.model_migrate.migrete_service",
        query_entity=([{"model_id": "rack", "_id": 1}, {"model_id": "switch", "_id": 2}], 2),
        batch_create_edge=[{"success": False, "message": "edge already exists"}],
        query_edge=[
            {
                "_id": 9,
                "model_asst_id": "rack_contains_switch",
                QUICK_FILTER_FIELD: False,
            }
        ],
    )

    migrator.migrate_associations()

    created = next(call for call in fake.calls if call[0] == "batch_create_edge")
    assert created[1][3][0][QUICK_FILTER_FIELD] is True
    updated = next(call for call in fake.calls if call[0] == "set_edge_properties")
    assert updated[1] == (9, {QUICK_FILTER_FIELD: True})


def test_relation_filter_matches_the_related_instance():
    associations = {
        "rack_contains_switch": {
            "src_model_id": "rack",
            "dst_model_id": "switch",
            "mapping": "1:n",
            "quick_filter": True,
        }
    }
    pinned = resolve_relation_filters(
        "switch",
        [{"model_asst_id": "rack_contains_switch", "inst_uuids": ["rack-1"]}],
        associations,
        {"switch", "rack"},
    )
    collector = ParameterCollector()
    match = compile_advanced_filter(
        "switch",
        "AND",
        [],
        label="instance",
        collector=collector,
        permission_for=None,
        base_params=[],
        pinned=pinned,
    )

    assert quick_filter_ends("rack", "switch", "1:n") == ("switch", "rack")
    assert "inst_uuid IN" in match
    assert any("rack-1" in value if isinstance(value, list) else value == "rack-1" for value in collector.get_params().values())
    with pytest.raises(AdvancedFilterError):
        resolve_relation_filters(
            "rack",
            [{"model_asst_id": "rack_contains_switch", "inst_uuids": ["rack-1"]}],
            associations,
            {"switch", "rack"},
        )


def test_migrate_without_column_leaves_existing_edge(monkeypatch):
    cfg = {
        "models": [{"model_id": "host"}],
        "asso-host": [{"src_model_id": "host", "dst_model_id": "switch", "asst_id": "connect"}],
    }
    migrator = ModelMigrate.__new__(ModelMigrate)
    migrator.model_config = cfg
    migrator.is_pre = True
    fake = _patch_graph(
        monkeypatch,
        "apps.cmdb.model_migrate.migrete_service",
        query_entity=([{"model_id": "host", "_id": 1}, {"model_id": "switch", "_id": 2}], 2),
        batch_create_edge=[{"success": True}],
    )

    migrator.migrate_associations()

    created = next(call for call in fake.calls if call[0] == "batch_create_edge")
    assert created[1][3][0][QUICK_FILTER_FIELD] is False
    assert not any(call[0] == "set_edge_properties" for call in fake.calls)
