# -- coding: utf-8 --
"""网络设备采集字段与 SOID 兼容合同（不依赖外部服务）。

锁定三处协同改动，防止「映射字段无对应模型属性」或「OID 特征库漏录」回归：
1. SOID 特征库 systemoid.json 收录目标网络设备 OID（型号/厂商可命中）。
2. NETWORK_DEVICE_MAPPING 把 VM 的 sysdescr 接入 CMDB 的 sys_desc 字段。
3. model_config.xlsx 的 switch/router/firewall 模型均含 sys_desc 属性。
"""
import json
import os

import openpyxl
import pytest

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics
from apps.cmdb.collection.plugins.community.network.plugins import NETWORK_DEVICE_MAPPING
from apps.cmdb.models import OidMapping
from apps.cmdb.services.oid_catalog import load_oid_catalog, sync_oid_catalog

SUPPORT_FILES = os.path.join(os.path.dirname(__file__), "..", "support-files")
SYSTEMOID = os.path.join(SUPPORT_FILES, "systemoid.json")
MODEL_CONFIG = os.path.join(SUPPORT_FILES, "model_config.xlsx")
NETWORK_DOC = os.path.join(SUPPORT_FILES, "plugins_doc", "network.md")

# 既有三个网络设备 OID（Task 2 历史目录，保持原语义）
EXPECTED_OIDS = {
    "1.3.6.1.4.1.9.1.3210": ("Cisco", "C1200-8T-D", "Switch"),
    "1.3.6.1.4.1.2011.2.23.968": ("Huawei", "S5735S-L8T4S-QA2", "Switch"),
    "1.3.6.1.4.1.25506.1.2609": ("H3C", "S2610V2", "Switch"),
}

# 国内厂商官方公开产品身份来源可逐条复核的代表 OID。
DOMESTIC_REPRESENTATIVE_OIDS = {
    "1.3.6.1.4.1.25506.1.763": ("H3C", "MSR2630", "Router"),
    "1.3.6.1.4.1.4881.250.160": ("Ruijie", "RG-WALL 160E", "Firewall"),
}

# 国际厂商官方产品身份来源可逐条复核的代表 OID。
INTERNATIONAL_REPRESENTATIVE_OIDS = {
    "1.3.6.1.4.1.9.1.3086": (
        "Cisco",
        "C9300X-48HXN",
        "Switch",
        "cisco-products-mib-20250613",
    ),
    "1.3.6.1.4.1.9.1.3091": (
        "Cisco",
        "Nexus 9348D-GX2A",
        "Switch",
        "cisco-products-mib-20250613",
    ),
    "1.3.6.1.4.1.9.1.1935": (
        "Cisco",
        "ISR 4431",
        "Router",
        "cisco-products-mib-20250613",
    ),
    "1.3.6.1.4.1.9.1.3075": (
        "Cisco",
        "ASR 9903",
        "Router",
        "cisco-products-mib-20250613",
    ),
    "1.3.6.1.4.1.9.1.3053": (
        "Cisco",
        "Firepower 3110",
        "Firewall",
        "cisco-products-mib-20250613",
    ),
    "1.3.6.1.4.1.30065.1.3011.7050.2966.4.32.3282": (
        "Arista",
        "DCS-7050DX4-32S",
        "Switch",
        "arista-products-mib-20260303",
    ),
    "1.3.6.1.4.1.12356.101.1.1000": (
        "Fortinet",
        "FortiGate 100F",
        "Firewall",
        "fortinet-fortigate-model-mibs-7-4-0",
    ),
    "1.3.6.1.4.1.25461.2.3.54": (
        "Palo Alto Networks",
        "PA-440",
        "Firewall",
        "paloalto-pan-products-mib-pan-os-12-1",
    ),
    "1.3.6.1.4.1.12276.1.3.1.1": (
        "F5",
        "BIG-IP rSeries R5x00",
        "loadbalance",
        "f5os-rseries-system-settings-1-2-0",
    ),
}

# 四种现有网络设备模型各选择一条可由官方产品身份资料复核的精确 OID。
VERIFIED_DEVICE_TYPE_OIDS = {
    "1.3.6.1.4.1.9.1.3086": ("Cisco", "C9300X-48HXN", "switch"),
    "1.3.6.1.4.1.25506.1.763": ("H3C", "MSR2630", "router"),
    "1.3.6.1.4.1.4881.250.160": ("Ruijie", "RG-WALL 160E", "firewall"),
    "1.3.6.1.4.1.12276.1.3.1.1": (
        "F5",
        "BIG-IP rSeries R5x00",
        "loadbalance",
    ),
}


def test_systemoid_contains_confirmed_network_oids():
    with open(SYSTEMOID, encoding="utf-8") as fp:
        oid_map = json.load(fp)
    for oid, (brand, model, first_type_id) in EXPECTED_OIDS.items():
        assert oid in oid_map, f"特征库缺少 OID {oid}"
        entry = oid_map[oid]
        assert entry["brand"] == brand
        assert entry["model"] == model
        assert entry["FirstTypeId"] == first_type_id
        assert entry["verification"] == "legacy-compatible"


def test_domestic_representative_oids_are_exactly_verified():
    with open(SYSTEMOID, encoding="utf-8") as fp:
        oid_map = json.load(fp)

    for oid, (brand, model, first_type_id) in DOMESTIC_REPRESENTATIVE_OIDS.items():
        assert oid in oid_map, f"特征库缺少国内代表 OID {oid}"
        entry = oid_map[oid]
        assert entry["OID"] == oid
        assert entry["brand"] == brand
        assert entry["model"] == model
        assert entry["FirstTypeId"] == first_type_id
        assert entry["verification"] == "verified"


def test_international_representative_oids_are_exactly_verified():
    with open(SYSTEMOID, encoding="utf-8") as fp:
        oid_map = json.load(fp)

    for oid, (
        brand,
        model,
        first_type_id,
        source_id,
    ) in INTERNATIONAL_REPRESENTATIVE_OIDS.items():
        assert oid in oid_map, f"特征库缺少国际代表 OID {oid}"
        entry = oid_map[oid]
        assert entry["OID"] == oid
        assert entry["brand"] == brand
        assert entry["model"] == model
        assert entry["FirstTypeId"] == first_type_id
        assert entry["source_id"] == source_id
        assert entry["verification"] == "verified"


def test_production_catalog_maps_verified_oids_to_all_network_device_types():
    catalog = load_oid_catalog()

    for oid, (brand, model, device_type) in VERIFIED_DEVICE_TYPE_OIDS.items():
        entry = catalog[oid]
        assert (entry.brand, entry.model, entry.device_type, entry.verification) == (
            brand,
            model,
            device_type,
            "verified",
        )


def test_unknown_oid_uses_compatible_switch_fallback():
    oid = "1.3.6.1.4.1.99999.999"

    assert CollectNetworkMetrics.get_default_oid_map(oid) == {
        "model": "未知",
        "oid": oid,
        "brand": "未知",
        "device_type": "switch",
        "built_in": False,
    }


@pytest.mark.django_db
def test_custom_oid_mapping_is_read_exactly_by_network_collection():
    oid = "1.3.6.1.4.1.99999.100"
    OidMapping.objects.create(
        oid=oid,
        model="用户型号",
        brand="用户品牌",
        device_type="router",
        built_in=False,
    )

    assert CollectNetworkMetrics.get_oid_map()[oid] == {
        "model": "用户型号",
        "oid": oid,
        "brand": "用户品牌",
        "device_type": "router",
        "built_in": False,
    }


def test_device_mapping_carries_sysdescr_to_sys_desc():
    assert NETWORK_DEVICE_MAPPING.get("sys_desc") == "sysdescr"


def test_network_models_define_sys_desc_attr():
    wb = openpyxl.load_workbook(MODEL_CONFIG, read_only=True)
    try:
        for sheet in ("attr-switch", "attr-router", "attr-firewall"):
            attr_ids = {row[0] for row in wb[sheet].iter_rows(min_row=2, values_only=True) if row[0]}
            # 映射左侧每个落库字段都必须在模型属性中存在（sys_desc 为新增项）
            assert "sys_desc" in attr_ids, f"{sheet} 缺少 sys_desc 属性"
    finally:
        wb.close()


def test_network_doc_describes_actual_unknown_oid_fallback():
    with open(NETWORK_DOC, encoding="utf-8") as fp:
        document = fp.read()

    assert "未知 SOID 会保留原始 OID" in document
    assert "品牌和型号标记为 `未知`，设备类型按 `switch` 兼容处理" in document


def test_network_doc_keeps_custom_overrides_out_of_unchanged_count():
    with open(NETWORK_DOC, encoding="utf-8") as fp:
        document = fp.read()

    assert "除用户覆盖外的已同步内置项均计入未变化" in document
    assert "自定义项仍计入用户覆盖" in document
    assert "已有目录项均计入未变化" not in document
    assert "优先按完整 OID 精确匹配" in document
    assert "最长前缀匹配" in document
    assert "同一 OID 的 POST 会被 API 拒绝" in document


def _catalog_oid_map():
    return {
        oid: {
            "oid": entry.oid,
            "model": entry.model,
            "brand": entry.brand,
            "device_type": entry.device_type,
            "built_in": True,
        }
        for oid, entry in load_oid_catalog().items()
    }


def _row(oid, brand, model, device_type, built_in=True):
    return {"oid": oid, "brand": brand, "model": model, "device_type": device_type, "built_in": built_in}


def test_exact_h3c_msr2630_beats_enterprise_prefix():
    oid_map = _catalog_oid_map()
    hit = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.25506.1.763", oid_map)
    assert (hit["brand"], hit["model"], hit["device_type"]) == ("H3C", "MSR2630", "router")


def test_prefix_raisecom_enterprise_when_only_root_matches():
    oid_map = {
        "1.3.6.1.4.1.8886": _row("1.3.6.1.4.1.8886", "Raisecom", "未知", "switch"),
    }
    hit = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.8886.1.2.3", oid_map)
    assert (hit["brand"], hit["model"], hit["device_type"]) == ("Raisecom", "未知", "switch")


def test_longer_prefix_wins_by_arc_count_not_string_length():
    oid_map = {
        "1.3.6.1.4.1.28557": _row("1.3.6.1.4.1.28557", "Hillstone", "未知", "firewall"),
        "1.3.6.1.4.1.28557.1": _row("1.3.6.1.4.1.28557.1", "Hillstone", "未知", "firewall"),
    }
    hit = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.28557.1.96", oid_map)
    assert hit["oid"] == "1.3.6.1.4.1.28557.1"


def test_leading_dot_equals_undotted_sysobjectid():
    oid_map = {
        "1.3.6.1.4.1.2011.2.23": _row("1.3.6.1.4.1.2011.2.23", "Huawei", "S5700", "switch"),
    }
    dotted = CollectNetworkMetrics.resolve_oid_mapping(".1.3.6.1.4.1.2011.2.23", oid_map)
    undotted = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.2011.2.23", oid_map)
    assert dotted == undotted
    assert dotted["brand"] == "Huawei"


def test_unknown_enterprise_uses_default_switch_fallback():
    hit = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.99999.1", {})
    assert hit == CollectNetworkMetrics.get_default_oid_map("1.3.6.1.4.1.99999.1")


def test_enterprise_root_is_never_used_as_catchall():
    oid_map = {
        "1.3.6.1.4.1": _row("1.3.6.1.4.1", "Bogus", "catch-all", "router"),
    }
    hit = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.99999.1", oid_map)
    assert hit["brand"] == "未知"
    assert hit["device_type"] == "switch"


def test_snmpv2_smi_enterprises_text_expands_before_match():
    oid_map = _catalog_oid_map()
    textual = CollectNetworkMetrics.resolve_oid_mapping("SNMPv2-SMI::enterprises.25506.1.763", oid_map)
    short = CollectNetworkMetrics.resolve_oid_mapping("enterprises.25506.1.763", oid_map)
    assert textual["model"] == "MSR2630"
    assert short["model"] == "MSR2630"


def test_production_prefix_and_verified_xinchuang_fingerprints():
    oid_map = _catalog_oid_map()
    raisecom = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.8886.9.9.9", oid_map)
    qianxin = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.47646.1.1", oid_map)
    fiberhome = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.3807.1.8012", oid_map)
    s6530 = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.25506.1.3259", oid_map)
    g6100 = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.28557.1.22", oid_map)
    net_snmp = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.8072.3.2.10", oid_map)
    cisco = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.9.1.3086", oid_map)
    rg_wall = CollectNetworkMetrics.resolve_oid_mapping("1.3.6.1.4.1.4881.250.160", oid_map)

    assert (raisecom["brand"], raisecom["model"], raisecom["device_type"]) == ("Raisecom", "未知", "switch")
    assert (qianxin["brand"], qianxin["device_type"]) == ("Qi-Anxin", "firewall")
    assert fiberhome["brand"] == "FiberHome"
    assert (s6530["brand"], s6530["model"], s6530["device_type"]) == ("H3C", "S6530X-48Y8C", "switch")
    assert (g6100["brand"], g6100["model"], g6100["device_type"]) == ("Hillstone", "SG-6000-G6100", "firewall")
    assert net_snmp["brand"] == "未知"
    assert (cisco["brand"], cisco["model"]) == ("Cisco", "C9300X-48HXN")
    assert (rg_wall["brand"], rg_wall["model"]) == ("Ruijie", "RG-WALL 160E")


@pytest.mark.django_db
def test_user_override_update_wins_over_catalog_and_sync_skips_it():
    """用户覆盖只能 UPDATE 已有行并设 built_in=False。

    init_oid 随 batch_init 每次启动会重置 built_in=True；同一 OID 的 POST 会被拒绝。
    """
    oid = "1.3.6.1.4.1.25506.1.763"
    row = OidMapping.objects.create(oid=oid, model="MSR2630", brand="H3C", device_type="router", built_in=True)
    row.model = "用户型号"
    row.brand = "用户品牌"
    row.device_type = "firewall"
    row.built_in = False
    row.save()

    mapping = CollectNetworkMetrics.get_oid_map()[oid]
    assert mapping == {
        "model": "用户型号",
        "oid": oid,
        "brand": "用户品牌",
        "device_type": "firewall",
        "built_in": False,
    }
    hit = CollectNetworkMetrics.resolve_oid_mapping(oid, CollectNetworkMetrics.get_oid_map())
    assert hit["brand"] == "用户品牌"

    result = sync_oid_catalog(load_oid_catalog())
    row.refresh_from_db()
    assert row.built_in is False
    assert row.model == "用户型号"
    assert oid in result.custom_override_oids


def test_format_data_applies_normalized_prefix_match():
    plugin = CollectNetworkMetrics.__new__(CollectNetworkMetrics)
    plugin.oid_map = _catalog_oid_map()
    plugin.timestamp_gt = True
    plugin.instance_id_map = {}
    plugin.collection_metrics_dict = {"network_device_info_gauge": []}
    plugin.format_data(
        {
            "result": [
                {
                    "metric": {
                        "__name__": "network_device_info_gauge",
                        "sysobjectid": "SNMPv2-SMI::enterprises.8886.9.9.9",
                        "host": "10.0.0.8",
                    },
                    "value": [1, "1"],
                }
            ]
        }
    )
    metric = plugin.collection_metrics_dict["network_device_info_gauge"][0]
    assert metric["brand"] == "Raisecom"
    assert metric["model"] == "未知"
    assert metric["device_type"] == "switch"
