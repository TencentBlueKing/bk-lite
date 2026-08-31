"""应用拓扑层级取值与默认映射。"""

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException


def test_default_app_topo_layer_matches_builtin_identity():
    from apps.cmdb.services.app_topo_layer import default_app_topo_layer

    assert default_app_topo_layer("system") == "system"
    assert default_app_topo_layer("application") == "service"
    assert default_app_topo_layer("host") == "host"
    assert default_app_topo_layer("vmware_vm") == "host"
    assert default_app_topo_layer("aliyun_ecs") == "host"
    assert default_app_topo_layer("azure_vm") == "host"
    assert default_app_topo_layer("h3c_cas_vm") == "host"
    assert default_app_topo_layer("mysql") == "appService"
    assert default_app_topo_layer("nginx") == "appService"
    assert default_app_topo_layer("oceanbase") == "appService"
    assert default_app_topo_layer("nacos") == "appService"
    assert default_app_topo_layer("aliyun_mysql") == "appService"
    assert default_app_topo_layer("physcial_server") == "infrastructure"
    assert default_app_topo_layer("switch") == "infrastructure"
    assert default_app_topo_layer("rack") == "infrastructure"
    assert default_app_topo_layer("server_room") == "infrastructure"
    assert default_app_topo_layer("k8s_cluster") == "none"
    assert default_app_topo_layer("custom_biz") == "none"


def test_default_app_topo_layer_uses_classification_when_given():
    from apps.cmdb.services.app_topo_layer import default_app_topo_layer

    assert default_app_topo_layer("unknown_db", "database") == "appService"
    assert default_app_topo_layer("unknown_mw", "middleware") == "appService"
    assert default_app_topo_layer("unknown_hw", "harware") == "infrastructure"
    assert default_app_topo_layer("unknown_other", "k8s") == "none"


def test_normalize_app_topo_layer_accepts_keys_and_chinese_labels():
    from apps.cmdb.services.app_topo_layer import normalize_app_topo_layer

    assert normalize_app_topo_layer("") == "none"
    assert normalize_app_topo_layer(None) == "none"
    assert normalize_app_topo_layer("host") == "host"
    assert normalize_app_topo_layer("系统") == "system"
    assert normalize_app_topo_layer("服务") == "service"
    assert normalize_app_topo_layer("应用") == "service"
    assert normalize_app_topo_layer("主机") == "host"
    assert normalize_app_topo_layer("应用服务") == "appService"
    assert normalize_app_topo_layer("基础设施") == "infrastructure"
    assert normalize_app_topo_layer("不分类") == "none"


def test_normalize_app_topo_layer_rejects_root_and_unknown():
    from apps.cmdb.services.app_topo_layer import normalize_app_topo_layer

    with pytest.raises(BaseAppException):
        normalize_app_topo_layer("root")
    with pytest.raises(BaseAppException):
        normalize_app_topo_layer("bogus")


def test_resolve_app_topo_layer_prefers_stored_value():
    from apps.cmdb.services.app_topo_layer import resolve_app_topo_layer

    assert resolve_app_topo_layer("mysql", "host") == "host"
    assert resolve_app_topo_layer("mysql", None) == "appService"
    assert resolve_app_topo_layer("custom_biz", "") == "none"
    assert resolve_app_topo_layer("system", None) == "system"
