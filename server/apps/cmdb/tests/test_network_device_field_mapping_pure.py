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

# 已确认的三个网络设备 OID（来自 sysObjectID/sysDescr 比对）
EXPECTED_OIDS = {
    "1.3.6.1.4.1.9.1.3210": ("Cisco", "C1200-8T-D"),
    "1.3.6.1.4.1.2011.2.23.968": ("华为", "S5735S-L8T4S-QA2"),
    "1.3.6.1.4.1.25506.1.2609": ("H3C", "S2610V2"),
}


def test_systemoid_contains_confirmed_network_oids():
    with open(SYSTEMOID, encoding="utf-8") as fp:
        oid_map = json.load(fp)
    for oid, (brand, model) in EXPECTED_OIDS.items():
        assert oid in oid_map, f"特征库缺少 OID {oid}"
        entry = oid_map[oid]
        assert entry["brand"] == brand
        assert entry["model"] == model
        # device_type 由 FirstTypeId 小写而来，须为 switch 以匹配 ip-switch 实例名
        assert entry["FirstTypeId"].lower() == "switch"


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
