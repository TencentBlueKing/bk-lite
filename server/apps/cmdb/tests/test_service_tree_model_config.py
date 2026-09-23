"""服务树内置模型：系统包含应用，不预置业务分组。"""

from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.unit

XLSX = Path(__file__).resolve().parents[1] / "support-files" / "model_config.xlsx"


def _rows(sheet_name):
    return pd.read_excel(XLSX, sheet_name=sheet_name, header=1).fillna("")


def test_biz_group_model_is_not_seeded():
    models = _rows("models")
    assert "biz_group" not in set(models["model_id"].astype(str))
    assert "attr-biz_group" not in pd.ExcelFile(XLSX).sheet_names
    assert "asso-biz_group" not in pd.ExcelFile(XLSX).sheet_names


def test_service_tree_associations_are_system_contains_application():
    system_assos = _rows("asso-system")[["src_model_id", "dst_model_id", "asst_id", "mapping"]].to_dict("records")
    assert {
        "src_model_id": "system",
        "dst_model_id": "application",
        "asst_id": "contains",
        "mapping": "1:n",
    } in system_assos
    assert not any(row.get("dst_model_id") == "biz_group" for row in system_assos)

    application_assos = _rows("asso-application")[["src_model_id", "dst_model_id", "asst_id", "mapping"]].to_dict("records")
    assert {
        "src_model_id": "application",
        "dst_model_id": "host",
        "asst_id": "run",
        "mapping": "n:n",
    } in application_assos
