import pandas as pd

MODEL_CONFIG = "apps/cmdb/support-files/model_config.xlsx"


EXPECTED_MODELS = {
    "nacos": "middleware",
    "nacos_node": "middleware",
    "nacos_namespace": "middleware",
    "nacos_service": "middleware",
    "ibmmq": "middleware",
    "ibmmq_channel": "middleware",
    "ibmmq_listener": "middleware",
    "ibmmq_localqueue": "middleware",
    "ibmmq_remotequeue": "middleware",
    "oceanbase": "database",
    "oceanbase_zone": "database",
    "oceanbase_server": "database",
    "oceanbase_tenant": "database",
    "highgo": "database",
}

REMOVED_MODELS = {
    "server_bmc",
    "server_bmc_cpu",
    "server_bmc_memory",
    "server_bmc_disk",
    "server_bmc_vdisk",
    "server_bmc_nic",
}


def test_batch1_models_have_expected_classifications():
    models = pd.read_excel(MODEL_CONFIG, sheet_name="models", header=1)
    by_id = models.set_index("model_id")["classification_id"].to_dict()

    for model_id, classification_id in EXPECTED_MODELS.items():
        assert by_id[model_id] == classification_id


def test_batch1_models_use_existing_icons():
    models = pd.read_excel(MODEL_CONFIG, sheet_name="models", header=1)
    by_id = models.set_index("model_id")["icn"].to_dict()

    for model_id in EXPECTED_MODELS:
        assert isinstance(by_id[model_id], str)
        assert by_id[model_id].strip()


def test_bmc_models_are_removed():
    models = pd.read_excel(MODEL_CONFIG, sheet_name="models", header=1)
    present = set(models["model_id"].dropna().astype(str))
    assert present.isdisjoint(REMOVED_MODELS)
    assert "tape_library" in present

    xl = pd.ExcelFile(MODEL_CONFIG)
    leftover_sheets = [
        f"{prefix}{model_id}" for model_id in REMOVED_MODELS for prefix in ("attr-", "asso-") if f"{prefix}{model_id}" in xl.sheet_names
    ]
    assert leftover_sheets == []
    assert "attr-tape_library" in xl.sheet_names
