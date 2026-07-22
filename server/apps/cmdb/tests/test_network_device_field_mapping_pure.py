# -- coding: utf-8 --
"""网络设备采集字段一致性（_pure，无 DB/IO 依赖外部服务）。

锁定三处协同改动，防止「映射字段无对应模型属性」或「OID 特征库漏录」回归：
1. SOID 特征库 systemoid.json 收录目标网络设备 OID（型号/厂商可命中）。
2. NETWORK_DEVICE_MAPPING 把 VM 的 sysdescr 接入 CMDB 的 sys_desc 字段。
3. model_config.xlsx 的 switch/router/firewall 模型均含 sys_desc 属性。
"""
import json
import os

import openpyxl

from apps.cmdb.collection.plugins.community.network.plugins import NETWORK_DEVICE_MAPPING

SUPPORT_FILES = os.path.join(os.path.dirname(__file__), "..", "support-files")
SYSTEMOID = os.path.join(SUPPORT_FILES, "systemoid.json")
MODEL_CONFIG = os.path.join(SUPPORT_FILES, "model_config.xlsx")

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
