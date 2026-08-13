"""host 拉同步与 ingest 共用身份规则。"""

from types import SimpleNamespace

from apps.cmdb.services.host_sync_identity import (
    build_host_inst_name,
    is_node_mgmt_sidecar_id,
    is_unique_conflict,
    node_id_to_write,
    resolve_host_identity,
)
from apps.node_mgmt.services.module_push_contract import LINK_CONFLICT


def test_build_host_inst_name_prefers_cloud_name():
    assert build_host_inst_name(ip="10.0.0.1", cloud_name="华东", cloud_id=2) == "10.0.0.1[华东]"


def test_build_host_inst_name_falls_back_to_cloud_id():
    assert build_host_inst_name(ip="10.0.0.1", cloud_name="", cloud_id=7) == "10.0.0.1[7]"


def test_resolve_by_node_id_does_not_fall_back_to_cmdb_id():
    match = resolve_host_identity(
        node_id="n1",
        cmdb_id="99",
        ip="1.1.1.1",
        cloud=1,
        find_by_node_id=lambda _nid: {"_id": 10, "node_id": "n1"},
        find_by_cmdb_id=lambda _cid: {"_id": 99},
        find_by_ip_cloud=lambda _ip, _cloud: {"_id": 20},
    )
    assert match.via == "node_id"
    assert match.instance["_id"] == 10
    assert match.conflict is None


def test_resolve_claims_ip_cloud_when_node_id_misses():
    match = resolve_host_identity(
        node_id="n2",
        cmdb_id=None,
        ip="1.1.1.2",
        cloud=1,
        find_by_node_id=lambda _nid: None,
        find_by_cmdb_id=lambda _cid: None,
        find_by_ip_cloud=lambda _ip, _cloud: {"_id": 20, "node_id": ""},
    )
    assert match.via == "ip_cloud"
    assert match.instance["_id"] == 20
    assert match.conflict is None


def test_resolve_conflict_when_ip_cloud_bound_to_other_node():
    match = resolve_host_identity(
        node_id="n2",
        cmdb_id=None,
        ip="1.1.1.2",
        cloud=1,
        find_by_node_id=lambda _nid: None,
        find_by_cmdb_id=lambda _cid: None,
        find_by_ip_cloud=lambda _ip, _cloud: {"_id": 20, "node_id": "other"},
    )
    assert match.conflict == LINK_CONFLICT
    assert match.instance["_id"] == 20


def test_resolve_skips_when_ip_or_cloud_missing_after_id_miss():
    match = resolve_host_identity(
        node_id="n2",
        cmdb_id=None,
        ip="",
        cloud=None,
        find_by_node_id=lambda _nid: None,
        find_by_cmdb_id=lambda _cid: None,
        find_by_ip_cloud=lambda _ip, _cloud: {"_id": 1},
    )
    assert match.skipped is True
    assert match.instance is None


def test_node_id_to_write_fills_empty_only():
    assert node_id_to_write({"node_id": ""}, "n1") == "n1"
    assert node_id_to_write({"node_id": "n1"}, "n1") is None
    assert node_id_to_write({"node_id": "n1"}, "n2") is None
    assert node_id_to_write(None, "n1") == "n1"


def test_is_node_mgmt_sidecar_id_matches_uuid4_hex_only():
    assert is_node_mgmt_sidecar_id("7e1bcd3d738c482fa33530b289d1c444") is True
    assert is_node_mgmt_sidecar_id("ioc-ipmi-15a2a84b91") is False
    assert is_node_mgmt_sidecar_id("rpcprobe3") is False
    assert is_node_mgmt_sidecar_id("node-7") is False
    assert is_node_mgmt_sidecar_id("") is False


def test_is_unique_conflict_accepts_reason_and_message():
    assert is_unique_conflict(SimpleNamespace(reason="unique_conflict", message="x")) is True
    assert is_unique_conflict(RuntimeError("ip_addr exist；")) is True
    assert is_unique_conflict(RuntimeError("disk full")) is False
