#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 live SSH 目标跑两次物理服务器 nic 入库路径（不另起 BK-Lite 产品栈）。

1. ssh 上传并执行 physcial_server_default_discover.sh（两次）
2. parse_server_info → HostCollect / PhysicalServerCollectionPlugin.format_metrics
3. Management.controller 两次（第二次 old_data=第一次已入库 nic）

用法（在 server 目录、sqlite 即可）：

  DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \\
    SSH_HOST=127.0.0.1 SSH_PORT=12226 SSH_USER=root SSH_PASSWORD=testpw \\
    uv run python ../agents/stargazer/tests/collect_fixtures/physcial_server_ssh_target/run_twice_collect.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
SERVER_ROOT = REPO_ROOT / "server"
STARGAZER_ROOT = REPO_ROOT / "agents" / "stargazer"
DISCOVER_SCRIPT = STARGAZER_ROOT / "plugins" / "inputs" / "physcial_server" / "physcial_server_default_discover.sh"

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
os.environ.setdefault("DB_ENGINE", "sqlite")
os.environ.setdefault("DB_NAME", ":memory:")
os.environ.setdefault("SECRET_KEY", "cursor-cloud-dev")
os.environ.setdefault("ENABLE_CELERY", "true")
sys.path.insert(0, str(SERVER_ROOT))
sys.path.insert(0, str(STARGAZER_ROOT))

import django  # noqa: E402

django.setup()

from plugins.inputs.physcial_server.server_info_parse import parse_server_info  # noqa: E402

from apps.cmdb.collection.common import Management  # noqa: E402
from apps.cmdb.collection.plugins.community.host.physical_server import PhysicalServerCollectionPlugin  # noqa: E402
from apps.cmdb.tests.test_collect_management_service import FakeGraph  # noqa: E402

SSH_HOST = os.environ.get("SSH_HOST", "127.0.0.1")
SSH_PORT = os.environ.get("SSH_PORT", "12226")
SSH_USER = os.environ.get("SSH_USER", "root")
SSH_PASSWORD = os.environ.get("SSH_PASSWORD", "testpw")
PARENT_NAME = os.environ.get("PHYS_SERVER_INST_NAME", "srv-live-1")


def _ssh_base():
    return [
        "sshpass",
        "-p",
        SSH_PASSWORD,
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=10",
        "-p",
        str(SSH_PORT),
        f"{SSH_USER}@{SSH_HOST}",
    ]


def ssh_run(remote_cmd: str, timeout: int = 120) -> str:
    result = subprocess.run(
        _ssh_base() + [remote_cmd],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout


def upload_discover_script() -> None:
    remote = "/tmp/physcial_server_default_discover.sh"
    scp = [
        "sshpass",
        "-p",
        SSH_PASSWORD,
        "scp",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-P",
        str(SSH_PORT),
        str(DISCOVER_SCRIPT),
        f"{SSH_USER}@{SSH_HOST}:{remote}",
    ]
    subprocess.run(scp, check=True, capture_output=True, text=True, timeout=30)
    ssh_run(f"chmod +x {remote}")


def ssh_discover() -> str:
    return ssh_run("PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin " "bash /tmp/physcial_server_default_discover.sh")


def nics_to_vm_rows(parsed_nics, now: int):
    rows = []
    for nic in parsed_nics:
        metric = {
            "__name__": "nic_info_gauge",
            "collect_status": "success",
            "self_device": PARENT_NAME,
            **{k: v for k, v in nic.items() if k != "self_device"},
        }
        rows.append({"metric": metric, "value": [now, "1"]})
    return {"result": rows}


def format_nics(vm_rows):
    original_model_id = PhysicalServerCollectionPlugin.model_id
    PhysicalServerCollectionPlugin.model_id = property(lambda self: "physcial_server")
    try:
        plugin = PhysicalServerCollectionPlugin(PARENT_NAME, "cmdb_1", 1)
        plugin.inst_name = PARENT_NAME
        plugin.format_data(vm_rows)
        plugin.format_metrics()
        return plugin.result.get("nic") or []
    finally:
        PhysicalServerCollectionPlugin.model_id = original_model_id


def upsert_nics(nics, old_data, fake: FakeGraph):
    import apps.cmdb.services.auto_relation_reconcile as ar
    from apps.cmdb.collection import common as mod
    from apps.cmdb.services.model import ModelManage

    mod.GraphClient = lambda *a, **k: fake
    ModelManage.search_model_attr = staticmethod(lambda model_id: [{"attr_id": "inst_name", "attr_name": "实例名", "is_only": True}])
    mod.write_collect_instance_change_records = lambda *a, **k: None

    class _Ext:
        def on_collect_instances_applied(self, **kw):
            return None

    mod.get_collect_enterprise_extension = lambda: _Ext()
    ar.schedule_instance_auto_relation_reconcile = lambda ids: None
    ar.schedule_incoming_rule_full_sync_by_model_ids = lambda ids: None
    mgmt = Management(
        organization=[1],
        inst_name=PARENT_NAME,
        model_id="nic",
        old_data=old_data,
        new_data=[dict(item) for item in nics],
        unique_keys=["inst_name"],
        collect_time="2026-08-27",
        task_id=9,
    )
    result = mgmt.controller()
    return result


def main() -> int:
    print(f"SSH {SSH_USER}@{SSH_HOST}:{SSH_PORT}")
    proof = ssh_run("echo ok").strip()
    print(f"ssh_proof={proof}")
    if proof != "ok":
        print("SSH proof failed", file=sys.stderr)
        return 1

    upload_discover_script()
    now = int(time.time())

    stdout1 = ssh_discover()
    parsed1 = parse_server_info(stdout1)
    formatted1 = format_nics(nics_to_vm_rows(parsed1.get("nic") or [], now))
    print("=== collect #1 live discover nics ===")
    for nic in parsed1.get("nic") or []:
        print(f"  parsed iface={nic.get('nic_iface')} mac={nic.get('nic_mac')}")
    print(f"collect1_parsed_nic_count={len(parsed1.get('nic') or [])}")
    print(f"collect1_formatted_nic_count={len(formatted1)}")
    for nic in formatted1:
        print(f"  formatted inst_name={nic.get('inst_name')} assos={nic.get('assos')}")

    if not formatted1:
        print("no ingestible NIC from live SSH discover", file=sys.stderr)
        print(stdout1[-2000:], file=sys.stderr)
        return 2

    created_ids = {"next": 10}
    existing_nics = {}
    created_edges = []

    def create_entity(label, info, check_attr_map, exist_items):
        key = info["inst_name"]
        if key in existing_nics:
            raise AssertionError(f"duplicate nic create: {key}")
        created_ids["next"] += 1
        ent = dict(info)
        ent["_id"] = created_ids["next"]
        existing_nics[key] = ent
        return ent

    def query_entity(label, conds):
        fields = {item["field"]: item.get("value") for item in conds}
        if fields.get("model_id") == "physcial_server":
            return ([{"_id": 1, "inst_name": PARENT_NAME, "model_id": "physcial_server"}], 1)
        return ([], 0)

    def create_edge(*args, **kwargs):
        payload = args[5] if len(args) > 5 else kwargs.get("data") or {}
        src_node = args[1] if len(args) > 1 else None
        dst_node = args[3] if len(args) > 3 else None
        edge = {
            "model_asst_id": payload.get("model_asst_id"),
            "src_model_id": payload.get("src_model_id"),
            "src_inst_id": payload.get("src_inst_id"),
            "dst_model_id": payload.get("dst_model_id"),
            "dst_inst_id": payload.get("dst_inst_id"),
            "create_edge_src": src_node,
            "create_edge_dst": dst_node,
        }
        ident = (edge["model_asst_id"], edge["src_inst_id"], edge["dst_inst_id"])
        if any((e["model_asst_id"], e["src_inst_id"], e["dst_inst_id"]) == ident for e in created_edges):
            raise Exception("edge already exists")
        created_edges.append(edge)
        return {}

    fake = FakeGraph()
    fake.create_entity = create_entity
    fake.returns["query_entity"] = query_entity
    fake.create_edge = create_edge

    first = upsert_nics(formatted1, [], fake)
    count1 = len(existing_nics)
    print(f"collect1_upsert_nic_count={count1}")
    print(f"collect1_add_success={len(first['add']['success'])}")
    print("=== collect #1 contains edges ===")
    for edge in created_edges:
        print(
            f"  {edge['model_asst_id']} "
            f"src={edge['src_model_id']}:{edge['src_inst_id']} "
            f"dst={edge['dst_model_id']}:{edge['dst_inst_id']} "
            f"create_edge({edge['create_edge_src']}->{edge['create_edge_dst']})"
        )

    stdout2 = ssh_discover()
    parsed2 = parse_server_info(stdout2)
    formatted2 = format_nics(nics_to_vm_rows(parsed2.get("nic") or [], now + 1))
    print(f"collect2_parsed_nic_count={len(parsed2.get('nic') or [])}")
    print(f"collect2_formatted_nic_count={len(formatted2)}")

    old_data = [
        {
            "inst_name": mac,
            "_id": ent["_id"],
            "nic_mac": mac,
            "self_device": PARENT_NAME,
        }
        for mac, ent in existing_nics.items()
    ]
    second = upsert_nics(formatted2, old_data, fake)
    count2 = len(existing_nics)
    print(f"collect2_upsert_nic_count={count2}")
    print(f"collect2_add_success={len(second['add']['success'])}")
    print("=== collect #2 contains edges (cumulative, idempotent) ===")
    for edge in created_edges:
        print(
            f"  {edge['model_asst_id']} "
            f"src={edge['src_model_id']}:{edge['src_inst_id']} "
            f"dst={edge['dst_model_id']}:{edge['dst_inst_id']} "
            f"create_edge({edge['create_edge_src']}->{edge['create_edge_dst']})"
        )

    errors = []
    if count1 != count2:
        errors.append(f"nic count changed: {count1} -> {count2}")
    if second["add"]["success"]:
        errors.append(f"second collect created nics: {second['add']['success']}")
    if not created_edges:
        errors.append("no contains edges written")
    for edge in created_edges:
        if edge["src_model_id"] != "physcial_server" or edge["dst_model_id"] != "nic":
            errors.append(f"wrong model endpoints: {edge}")
        if edge["src_inst_id"] != 1 or edge["dst_inst_id"] == 1:
            errors.append(f"wrong instance endpoints: {edge}")
        if edge["create_edge_src"] != 1 or edge["create_edge_dst"] == 1:
            errors.append(f"reversed create_edge args: {edge}")
        if edge["model_asst_id"] != "physcial_server_contains_nic":
            errors.append(f"wrong model_asst_id: {edge}")

    if errors:
        print("FAILED:")
        for item in errors:
            print(f"  - {item}")
        return 3

    print("OK twice-collect nic count unchanged; contains src=physcial_server dst=nic")
    return 0


if __name__ == "__main__":
    sys.exit(main())
