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
    "server_bmc": "harware",
    "server_bmc_cpu": "hardware_components",
    "server_bmc_memory": "hardware_components",
    "server_bmc_disk": "hardware_components",
    "server_bmc_vdisk": "hardware_components",
    "server_bmc_nic": "hardware_components",
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
