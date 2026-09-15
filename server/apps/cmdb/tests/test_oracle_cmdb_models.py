import pandas as pd

from apps.cmdb.collection.plugins.community.protocol.oracle import OracleCollectionPlugin
from apps.cmdb.services.app_topo_layer import default_app_topo_layer

MODEL_CONFIG = "apps/cmdb/support-files/model_config.xlsx"


def test_oracle_child_models_are_database_app_service():
    models = pd.read_excel(MODEL_CONFIG, sheet_name="models", header=1)
    by_id = models.set_index("model_id")
    for model_id in ("oracle", "oracle_instance", "oracle_pdb"):
        assert by_id.loc[model_id, "classification_id"] == "database"
        assert by_id.loc[model_id, "app_topo_layer"] == "appService"
        assert default_app_topo_layer(model_id) == "appService"


def test_oracle_child_associations_belong_to_parent():
    instance_asso = pd.read_excel(MODEL_CONFIG, sheet_name="asso-oracle_instance", header=1)
    pdb_asso = pd.read_excel(MODEL_CONFIG, sheet_name="asso-oracle_pdb", header=1)
    assert (instance_asso["src_model_id"] == "oracle_instance").any()
    assert (instance_asso["dst_model_id"] == "oracle").any()
    assert (instance_asso["asst_id"] == "belong").any()
    assert (pdb_asso["src_model_id"] == "oracle_pdb").any()
    assert (pdb_asso["dst_model_id"] == "oracle").any()


def test_oracle_parent_keeps_access_point_fields():
    attrs = pd.read_excel(MODEL_CONFIG, sheet_name="attr-oracle", header=1)
    attr_ids = set(attrs["attr_id"])
    assert {"ip_addr", "port", "sid", "service_name", "db_unique_name", "collect_scope", "cluster_type"} <= attr_ids


def test_oracle_plugin_maps_three_models():
    assert OracleCollectionPlugin.supported_model_id == "oracle"
    assert set(OracleCollectionPlugin.metric_names) == {
        "oracle_info_gauge",
        "oracle_instance_info_gauge",
        "oracle_pdb_info_gauge",
    }
    assert set(OracleCollectionPlugin.field_mappings) == {"oracle", "oracle_instance", "oracle_pdb"}
    assert OracleCollectionPlugin.field_mapping["inst_name"] is OracleCollectionPlugin.set_oracle_inst_name
    assert OracleCollectionPlugin.field_mappings["oracle"]["inst_name"] is OracleCollectionPlugin.set_oracle_inst_name


def test_oracle_plugin_format_metrics_maps_children_and_skips_empty_pdb():
    from types import SimpleNamespace

    collect_inst = SimpleNamespace(id=1, model_id="oracle", instances=[{"inst_name": "orcl_unique"}])
    plugin = OracleCollectionPlugin("orcl_unique", 1, 1, collect_inst=collect_inst)
    assert set(plugin.model_field_mapping) == {"oracle", "oracle_instance", "oracle_pdb"}
    plugin.collection_metrics_dict = {
        "oracle_info_gauge": [{"inst_name": "orcl_unique", "ip_addr": "10.0.0.1", "collect_status": "success"}],
        "oracle_instance_info_gauge": [
            {
                "inst_name": "orcl_unique-orcl",
                "sid": "orcl",
                "db_unique_name": "orcl_unique",
                "parent_inst_name": "10.0.0.1-oracle",
                "collect_status": "success",
            }
        ],
        "oracle_pdb_info_gauge": [{"collect_status": "success", "bk_obj_id": "oracle_pdb"}],
    }
    plugin.format_metrics()
    assert plugin.result["oracle"][0]["inst_name"] == "10.0.0.1-oracle"
    assert plugin.result["oracle_instance"][0]["sid"] == "orcl"
    assert plugin.result["oracle_instance"][0]["assos"][0]["inst_name"] == "10.0.0.1-oracle"
    assert plugin.result["oracle_pdb"] == []
