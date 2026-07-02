import pandas as pd
import pytest


MODEL_CONFIG = "apps/cmdb/support-files/model_config.xlsx"


REMAINING_MODEL_CLASSES = [('tonglinkq', 'middleware'), ('tonggtp', 'middleware'), ('ihs', 'middleware'), ('cics', 'middleware'), ('ibm_storwize', 'harware'), ('ibm_ds', 'harware'), ('emc_symmetrix', 'harware'), ('hds_vsp', 'harware'), ('macrosan', 'harware'), ('pure_array', 'harware'), ('netapp_cluster', 'harware'), ('oraclezfs', 'harware'), ('infinidat', 'harware'), ('tape_library', 'harware'), ('brocade_fc', 'network_device'), ('cisco_fc', 'network_device'), ('f5', 'network_device'), ('informix', 'database'), ('sybase', 'database'), ('couchbase', 'database'), ('mycat', 'database'), ('sap_hana', 'database'), ('iris', 'database'), ('aix', 'host_manage'), ('hpux', 'host_manage'), ('hmc', 'harware'), ('hdfs', 'middleware'), ('yarn', 'middleware'), ('storm', 'middleware'), ('ambari', 'middleware'), ('redis_sentinel', 'database'), ('bes', 'middleware'), ('apusic', 'middleware'), ('inforsuite_as', 'middleware'), ('gbase8s', 'database'), ('oscar', 'database'), ('security_device', 'network_device'), ('domestic_linux', 'host_manage'), ('tongrds', 'database'), ('tdsql', 'database'), ('zstack', 'zstack'), ('h3c_cas', 'h3c_cas'), ('xsky', 'harware')]


def test_remaining_models_exist_in_model_config():
    models = pd.read_excel(MODEL_CONFIG, sheet_name="models", header=1)
    target_ids = [item[0] for item in REMAINING_MODEL_CLASSES]
    target_models = models[models["model_id"].isin(target_ids)]
    assert not target_models["model_id"].duplicated().any()
    by_id = target_models.set_index("model_id").to_dict("index")

    for model_id, classification_id in REMAINING_MODEL_CLASSES:
        assert by_id[model_id]["classification_id"] == classification_id
        assert by_id[model_id]["icn"].strip()


@pytest.mark.parametrize("model_id", [item[0] for item in REMAINING_MODEL_CLASSES])
def test_remaining_model_attr_sheet_exists(model_id):
    xl = pd.ExcelFile(MODEL_CONFIG)
    assert f"attr-{model_id}" in xl.sheet_names
