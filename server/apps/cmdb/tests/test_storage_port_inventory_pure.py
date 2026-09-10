"""存储以太口 / FC 口身份：MAC/WWPN 归一化与空值跳过（_pure）。"""
from apps.cmdb.collection.common import Management
from apps.cmdb.collection.storage_port_inventory import (
    eth_port_identity,
    fc_port_identity,
    normalize_storage_mac,
    normalize_wwpn,
    optional_ipv4,
    optional_speed,
    port_display_name,
)


def test_normalize_storage_mac_matches_nic_convention():
    assert normalize_storage_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
    assert normalize_storage_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"
    assert normalize_storage_mac("aabbccddeeff") == "aa:bb:cc:dd:ee:ff"
    assert normalize_storage_mac("aabb.ccdd.eeff") == "aa:bb:cc:dd:ee:ff"


def test_normalize_storage_mac_skips_empty_and_invalid():
    assert normalize_storage_mac("") == ""
    assert normalize_storage_mac(None) == ""
    assert normalize_storage_mac("N/A") == ""
    assert normalize_storage_mac("--") == ""
    assert normalize_storage_mac("00:00:00:00:00:00") == ""
    assert normalize_storage_mac("not-a-mac") == ""


def test_normalize_wwpn_lowercase_colon():
    assert normalize_wwpn("21:00:00:24:FF:5A:12:34") == "21:00:00:24:ff:5a:12:34"
    assert normalize_wwpn("21000024ff5a1234") == "21:00:00:24:ff:5a:12:34"
    assert normalize_wwpn("21-00-00-24-FF-5A-12-34") == "21:00:00:24:ff:5a:12:34"
    assert normalize_wwpn("0x21000024FF5A1234") == "21:00:00:24:ff:5a:12:34"
    assert normalize_wwpn("20000024ff5a1234aabbccddeeff0011") == "20:00:00:24:ff:5a:12:34:aa:bb:cc:dd:ee:ff:00:11"


def test_normalize_wwpn_skips_empty_and_invalid():
    assert normalize_wwpn("") == ""
    assert normalize_wwpn(None) == ""
    assert normalize_wwpn("N/A") == ""
    assert normalize_wwpn("--") == ""
    assert normalize_wwpn("00:00:00:00:00:00:00:00") == ""
    assert normalize_wwpn("21000024ff") == ""
    assert normalize_wwpn("not-a-wwpn") == ""


def test_eth_port_identity_reads_huawei_mac_keys():
    assert eth_port_identity({"MACADDR": "aabbccddee02"}) == "aa:bb:cc:dd:ee:02"
    assert eth_port_identity({"MACADDRESS": "AA-BB-CC-DD-EE-01"}) == "aa:bb:cc:dd:ee:01"
    assert eth_port_identity({"mac": "aa:bb:cc:dd:ee:03"}) == "aa:bb:cc:dd:ee:03"
    assert eth_port_identity({"NAME": "ETH0"}) == ""
    assert eth_port_identity({"MACADDR": ""}) == ""
    assert eth_port_identity({}) == ""


def test_fc_port_identity_reads_huawei_wwpn_keys():
    assert fc_port_identity({"WWPN": "21:00:00:24:FF:5A:12:35"}) == "21:00:00:24:ff:5a:12:35"
    assert fc_port_identity({"WWN": "21000024ff5a1234"}) == "21:00:00:24:ff:5a:12:34"
    assert fc_port_identity({"NAME": "FC0"}) == ""
    assert fc_port_identity({"WWPN": "--"}) == ""
    assert fc_port_identity({}) == ""


def test_port_display_name_uses_name_or_location():
    assert port_display_name({"NAME": "ETH0", "LOCATION": "CTE0.A.P0"}) == "ETH0"
    assert port_display_name({"LOCATION": "CTE0.A.P0"}) == "CTE0.A.P0"
    assert port_display_name({"NAME": "--", "LOCATION": "CTE0.A.P1"}) == "CTE0.A.P1"
    assert port_display_name({}) == ""


def test_optional_ipv4_and_speed_skip_placeholders():
    assert optional_ipv4("10.0.0.8") == "10.0.0.8"
    assert optional_ipv4("0.0.0.0") == ""
    assert optional_ipv4("--") == ""
    assert optional_ipv4("not-an-ip") == ""
    assert optional_speed({"RUNSPEED": "16"}) == "16"
    assert optional_speed({"MAXSPEED": "32"}) == "32"
    assert optional_speed({"SPEED": "--"}) == ""
    assert optional_speed({}) == ""


def test_contains_edge_is_storage_to_port_not_reverse_belong():
    current = {"model_id": "storage_eth_port", "_id": 2, "inst_name": "aa:bb:cc:dd:ee:01"}
    listed = {
        "model_id": "storage",
        "inst_name": "华为存储-1",
        "asst_id": "contains",
        "model_asst_id": "storage_contains_storage_eth_port",
    }
    src_info, dst_id, dst_info = Management._association_endpoints(current, listed, 1)
    assert src_info["model_id"] == "storage"
    assert src_info["_id"] == 1
    assert dst_id == 2
    assert dst_info["model_id"] == "storage_eth_port"
    assert dst_info["model_asst_id"] == "storage_contains_storage_eth_port"

    fc_current = {"model_id": "storage_fc_port", "_id": 4, "inst_name": "21:00:00:24:ff:5a:12:34"}
    fc_listed = {
        "model_id": "storage",
        "inst_name": "华为存储-1",
        "asst_id": "contains",
        "model_asst_id": "storage_contains_storage_fc_port",
    }
    src_info, dst_id, dst_info = Management._association_endpoints(fc_current, fc_listed, 3)
    assert src_info["model_id"] == "storage"
    assert dst_info["model_id"] == "storage_fc_port"
