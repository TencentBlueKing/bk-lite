"""业务分组内置模型与服务树关联种子。"""

from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.unit

XLSX = Path(__file__).resolve().parents[1] / "support-files" / "model_config.xlsx"


def _rows(sheet_name):
    return pd.read_excel(XLSX, sheet_name=sheet_name, header=1).fillna("")


def test_biz_group_model_is_seeded_under_application_topology():
    models = _rows("models").set_index("model_id")
    assert models.loc["biz_group", "model_name"] == "业务分组"
    assert models.loc["biz_group", "classification_id"] == "business_manage"
    assert models.loc["biz_group", "app_topo_layer"] == "none"
    assert models.loc["biz_group", "icn"] == "cc-set_集群"


def test_biz_group_has_name_and_organization_only():
    attrs = set(_rows("attr-biz_group")["attr_id"])
    assert attrs == {"inst_name", "organization"}
    required = _rows("attr-biz_group").set_index("attr_id")
    assert bool(required.loc["inst_name", "is_only"]) is True
    assert bool(required.loc["inst_name", "is_required"]) is True
    assert bool(required.loc["organization", "is_required"]) is True


def test_service_tree_associations_are_one_to_n_contains():
    system_assos = _rows("asso-system")[["src_model_id", "dst_model_id", "asst_id", "mapping"]].to_dict("records")
    assert {
        "src_model_id": "system",
        "dst_model_id": "application",
        "asst_id": "contains",
        "mapping": "1:n",
    } in system_assos
    assert {
        "src_model_id": "system",
        "dst_model_id": "biz_group",
        "asst_id": "contains",
        "mapping": "1:n",
    } in system_assos

    group_assos = _rows("asso-biz_group")[["src_model_id", "dst_model_id", "asst_id", "mapping"]].to_dict("records")
    assert {
        "src_model_id": "biz_group",
        "dst_model_id": "biz_group",
        "asst_id": "contains",
        "mapping": "1:n",
    } in group_assos
    assert {
        "src_model_id": "biz_group",
        "dst_model_id": "application",
        "asst_id": "contains",
        "mapping": "1:n",
    } in group_assos

    application_assos = _rows("asso-application")[["src_model_id", "dst_model_id", "asst_id", "mapping"]].to_dict("records")
    assert {
        "src_model_id": "application",
        "dst_model_id": "host",
        "asst_id": "run",
        "mapping": "n:n",
    } in application_assos
