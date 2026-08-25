"""深信服 SCP/HCI 模型配置契约。"""

from pathlib import Path

import pandas as pd

MODEL_CONFIG = Path("apps/cmdb/support-files/model_config.xlsx")
SANGFOR_CLASSIFICATION_ID = "sangforscp"


def _rows(sheet_name):
    return pd.read_excel(MODEL_CONFIG, sheet_name=sheet_name, header=1).fillna("")


def test_sangfor_models_are_registered_under_one_platform_classification():
    classifications = _rows("classifications").set_index("classification_id")
    models = _rows("models").set_index("model_id")

    assert classifications.loc[SANGFOR_CLASSIFICATION_ID, "classification_name"] == "深信服平台"
    assert {
        model_id: (
            models.loc[model_id, "model_name"],
            models.loc[model_id, "classification_id"],
        )
        for model_id in (
            "sangforscp",
            "sangforscp_host",
            "sangforscp_vm",
            "sangforhci",
            "sangforhci_vm",
        )
    } == {
        "sangforscp": ("SCP云平台", SANGFOR_CLASSIFICATION_ID),
        "sangforscp_host": ("SCP平台主机", SANGFOR_CLASSIFICATION_ID),
        "sangforscp_vm": ("SCP平台虚拟机", SANGFOR_CLASSIFICATION_ID),
        "sangforhci": ("HCI平台", SANGFOR_CLASSIFICATION_ID),
        "sangforhci_vm": ("HCI虚拟机", SANGFOR_CLASSIFICATION_ID),
    }
    assert "sangforhci_host" not in models.index
    assert "sangforhci_storage" not in models.index


def test_sangfor_root_targets_and_associations_are_declared():
    workbook = pd.ExcelFile(MODEL_CONFIG)
    hci_root_attrs = set(_rows("attr-sangforhci")["attr_id"])

    assert {"endpoint", "tag"} <= hci_root_attrs
    assert "asso-sangforscp_host" in workbook.sheet_names
    assert _rows("asso-sangforscp_host")[["src_model_id", "dst_model_id", "asst_id", "mapping"]].to_dict("records")[0] == {
        "src_model_id": "sangforscp_host",
        "dst_model_id": "sangforscp",
        "asst_id": "belong",
        "mapping": "n:1",
    }
    assert _rows("asso-sangforscp_vm")[["src_model_id", "dst_model_id", "asst_id", "mapping"]].to_dict("records")[0] == {
        "src_model_id": "sangforscp_vm",
        "dst_model_id": "sangforscp_host",
        "asst_id": "belong",
        "mapping": "n:1",
    }
    assert _rows("asso-sangforhci_vm")[["src_model_id", "dst_model_id", "asst_id", "mapping"]].to_dict("records")[0] == {
        "src_model_id": "sangforhci_vm",
        "dst_model_id": "sangforhci",
        "asst_id": "belong",
        "mapping": "n:1",
    }
