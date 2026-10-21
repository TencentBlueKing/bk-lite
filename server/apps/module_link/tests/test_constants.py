from apps.cmdb.constants.monitor_link import CMDB_MODEL_TO_MONITOR_OBJECT
from apps.module_link.constants import builtin_model_id, builtin_object_name, is_builtin_mapped_model, is_platform_tree_model


def test_platform_tree_models_are_skipped():
    assert is_platform_tree_model("k8s_cluster") is True
    assert is_platform_tree_model("k8s_pod") is True
    assert is_platform_tree_model("vmware_vc") is True
    assert is_platform_tree_model("aliyun_account") is True
    assert is_platform_tree_model("qcloud") is True
    assert is_platform_tree_model("host") is False
    assert is_platform_tree_model("weblogic") is False
    assert is_platform_tree_model("biz") is False


def test_builtin_mapping_unchanged_for_host():
    assert CMDB_MODEL_TO_MONITOR_OBJECT["host"] == "Host"
    assert builtin_object_name("host") == "Host"
    assert is_builtin_mapped_model("host") is True
    assert is_builtin_mapped_model("weblogic") is False
    assert "weblogic" not in CMDB_MODEL_TO_MONITOR_OBJECT


def test_builtin_model_id_does_not_default_unknown_to_host():
    assert builtin_model_id("Host") == "host"
    assert builtin_model_id("Weblogic") is None
    assert builtin_model_id("") is None
