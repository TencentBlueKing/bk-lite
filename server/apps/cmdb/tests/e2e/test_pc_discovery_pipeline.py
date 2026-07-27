# -*- coding: utf-8 -*-
"""PC 发现端到端流水线合同测试。

链路（全部离线可重复）：
  任务+凭据 → PCNodeParams headers（${ENV} 占位符）
    → executor stdout（fixture，与 stargazer 侧合同共用同一份输入）
    → VM rows（fixture，由真实 normalize_snapshot 生成）
    → PCCollectionPlugin.format_data/format_metrics（真实代码）
    → PCSnapshotReconciler（真实代码，图客户端用 InMemoryGraph 替身）

锁定：
- executor stdout 与 VM rows 身份一致（hardware_uuid → inst_name、snapshot_id、计数）；
- Windows 四轮：初始新增 → 版本升级同实例更新 → 完整空快照安全删除并写 DELETE_INST 审计
  → partial 快照永不删除；
- macOS：初始新增 → 升级更新 → partial 不删除；
- collect_status=failed 的行被跳过，零快照零删除；
- 秘密原值（口令/PEM 私钥/密码短语）不出现在 headers、VM rows、format_data、ChangeRecord。
"""
import copy
import json
import types

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes, DataCleanupStrategy
from apps.cmdb.models.change_record import DELETE_INST, ChangeRecord
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.tests.test_pc_reconcile import InMemoryGraph
from apps.cmdb_enterprise.collect.pc import PCCollectionPlugin

BASE_TS = 1753200000

# 秘密原值：只应出现在 env_config，绝不出现在其他链路产物
WINDOWS_PASSWORD = "S3cret!Passw0rd#PC"
MACOS_PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nFAKE-PC-KEY-DATA\n-----END OPENSSH PRIVATE KEY-----"
MACOS_PASSPHRASE = "pc-key-passphrase-001"

EXPECTED = {
    "windows": {
        "host": "192.168.1.56",
        "pc_inst_name": "WIN-4C4C4544-0038-5910-8058-C4C04F433632",
        "software_inst_name": "SW-2650AFE84F84FE9B7C9B69A8A407FB3A",
        "software_version": "127.0.6533.89",
    },
    "macos": {
        "host": "192.168.1.88",
        "pc_inst_name": "MAC-00001111-2222-3333-4444-555566667777",
        "software_inst_name": "SW-0B22C66586805CD4A2F1F2A669501741",
        "software_version": "127.0.6533.89",
    },
}


def _fake_header_task(os_type):
    """构造 headers 合同用的任务替身（与 test_pc_node_params 同一形态）。"""
    task = types.SimpleNamespace()
    task.id = 321
    task.model_id = "pc"
    task.driver_type = CollectDriverTypes.JOB
    task.timeout = 120
    task.instances = []
    task.ip_range = "192.168.1.56"
    task.access_point = [{"id": "node-1"}]
    if os_type == "windows":
        task.params = {
            "os_type": "windows",
            "winrm_scheme": "https",
            "winrm_transport": "ntlm",
            "winrm_cert_validation": False,
        }
        task.decrypt_credentials = [
            {"username": "ACME\\alice", "password": WINDOWS_PASSWORD, "port": 5986}
        ]
    else:
        task.params = {"os_type": "macos"}
        task.decrypt_credentials = [
            {
                "username": "admin",
                "private_key": MACOS_PRIVATE_KEY,
                "passphrase": MACOS_PASSPHRASE,
                "port": 22,
            }
        ]
    return task


def _db_task(strategy=DataCleanupStrategy.IMMEDIATELY):
    return CollectModels.objects.create(
        name="pc-e2e-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="pc",
        cycle_value_type="cycle",
        team=[7],
        data_cleanup_strategy=strategy,
    )


@pytest.fixture
def graph(monkeypatch):
    fake = InMemoryGraph()
    monkeypatch.setattr("apps.cmdb.services.pc_discovery.GraphClient", lambda *a, **k: fake)
    return fake


def _run_plugin(task, vm_doc):
    """跑真实 PCCollectionPlugin 的 format_data + format_metrics，返回任务级 format_data。"""
    plugin = PCCollectionPlugin(inst_name="", inst_id=f"cmdb_{task.id}", task_id=task.id)
    plugin.format_data(vm_doc["data"])
    plugin.format_metrics()
    return plugin.result[PCCollectionPlugin.TASK_FORMAT_DATA_KEY]


def _round(vm_doc, snapshot_id, ts, software_overrides=None, drop_software=False,
           status=None, expected=None):
    """从基线 VM rows 派生一轮快照：固定输入的受控变体（升级/空快照/partial）。"""
    doc = copy.deepcopy(vm_doc)
    rows = doc["data"]["result"]
    for row in rows:
        row["metric"]["snapshot_id"] = snapshot_id
        row["value"] = [ts, "1"]
        if row["metric"]["__name__"] == "pc_info":
            if status is not None:
                row["metric"]["software_snapshot_status"] = status
            if expected is not None:
                row["metric"]["software_expected_count"] = str(expected)
    if software_overrides:
        for row in rows:
            if row["metric"]["__name__"] == "pc_software_info":
                row["metric"].update(software_overrides)
    if drop_software:
        doc["data"]["result"] = [
            row for row in rows if row["metric"]["__name__"] != "pc_software_info"
        ]
    return doc


def _software_of(graph, pc_inst):
    pc_id = graph.store[pc_inst]["_id"]
    sw_ids = {
        edge["src_inst_id"]
        for edge in graph.edges
        if edge["dst_inst_id"] == pc_id and edge["asst_id"] == "install_on"
    }
    return {name: entity for name, entity in graph.store.items() if entity.get("_id") in sw_ids}


def _assert_no_secret_leak(*artifacts):
    """递归断言秘密原值与秘密字段名不出现在任何链路产物。"""
    blob = json.dumps(artifacts, ensure_ascii=False, default=str)
    for secret in (WINDOWS_PASSWORD, MACOS_PRIVATE_KEY, "FAKE-PC-KEY-DATA", MACOS_PASSPHRASE):
        assert secret not in blob

    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert str(key).lower() not in ("password", "private_key", "passphrase")
                _walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)

    for artifact in artifacts:
        _walk(artifact)


# ---------------------------------------------------------------- headers 合同


def test_node_params_headers_carry_no_plaintext_secret():
    for os_type in ("windows", "macos"):
        node = NodeParamsFactory.get_node_params(_fake_header_task(os_type))
        headers = node.custom_headers()
        env_config = node.env_config()

        assert headers["cmdbmodel_id"] == "pc"
        assert headers["cmdbos_type"] == os_type
        _assert_no_secret_leak(headers)
        # 秘密只经 env_config 注入，且以 ${ENV} 占位符引用
        assert env_config, "秘密必须经 env_config 下发"
        assert set(env_config.values()) & {WINDOWS_PASSWORD, MACOS_PRIVATE_KEY, MACOS_PASSPHRASE}
        for value in headers.values():
            assert not str(value).startswith("S3cret")


# ------------------------------------------------------- fixture 身份一致性合同


@pytest.mark.parametrize("os_type", ["windows", "macos"])
def test_executor_stdout_matches_vm_rows_identity(load_fixture, os_type):
    stdout = load_fixture(f"pc/{os_type}_executor_stdout.json")
    vm_doc = load_fixture(f"pc/{os_type}_vm_rows.json")
    expected = EXPECTED[os_type]

    rows = {row["metric"]["__name__"]: row["metric"] for row in vm_doc["data"]["result"]}
    pc_row = rows["pc_info"]
    sw_row = rows["pc_software_info"]

    # 身份由 hardware_uuid 推导，且与 executor stdout 一致
    assert pc_row["inst_name"] == expected["pc_inst_name"]
    assert pc_row["hardware_uuid"] == stdout["pc"][0]["hardware_uuid"].upper()
    assert pc_row["snapshot_id"] == stdout["snapshot_id"]
    assert sw_row["inst_name"] == expected["software_inst_name"]
    assert sw_row["pc_inst_name"] == expected["pc_inst_name"]
    assert sw_row["snapshot_id"] == stdout["snapshot_id"]
    assert int(pc_row["software_expected_count"]) == stdout["software_expected_count"]


# ---------------------------------------------------------------- Windows 四轮


@pytest.mark.django_db
def test_windows_pipeline_full_rounds(load_fixture, graph):
    expected = EXPECTED["windows"]
    vm_doc = load_fixture("pc/windows_vm_rows.json")
    task = _db_task()

    # 第 1 轮：初始完整快照 → 新增 PC + 软件 + install_on 关联
    fd = _run_plugin(task, _round(vm_doc, "win-s1", BASE_TS))
    assert fd["delete"] == []
    assert [row["inst_name"] for row in fd["add"]] == [expected["pc_inst_name"]]
    assert fd["pc_summary"]["pc_complete"] == 1
    assert fd["pc_summary"]["software_added"] == 1

    final_pc = graph.store[expected["pc_inst_name"]]
    assert final_pc["inst_name"] == expected["pc_inst_name"]
    assert final_pc["host_name"] == "FINANCE-PC-01"
    final_software = graph.store[expected["software_inst_name"]]
    assert final_software["inst_name"] == expected["software_inst_name"]
    assert final_software["version"] == expected["software_version"]
    assert len(graph.edges) == 1
    assert graph.edges[0]["asst_id"] == "install_on"

    # 第 2 轮：版本升级 → 同实例更新，不新增、不删除
    fd = _run_plugin(
        task,
        _round(vm_doc, "win-s2", BASE_TS + 300,
               software_overrides={"version": "128.0.6600.1"}),
    )
    assert fd["add"] == []
    assert fd["delete"] == []
    assert [row["inst_name"] for row in fd["update"]] == [expected["pc_inst_name"]]
    assert fd["pc_summary"]["software_updated"] == 1
    assert graph.store[expected["software_inst_name"]]["version"] == "128.0.6600.1"
    assert len(graph.edges) == 1

    # 第 3 轮：完整空快照（软件全部卸载）→ 安全差集删除 + DELETE_INST 审计
    fd = _run_plugin(
        task,
        _round(vm_doc, "win-s3", BASE_TS + 600, drop_software=True, expected=0),
    )
    assert expected["software_inst_name"] not in graph.store
    assert fd["pc_summary"]["software_deleted"] == 1
    assert [row["inst_name"] for row in fd["delete"]] == [expected["software_inst_name"]]
    assert fd["delete"][0]["_status"] == "success"
    record = ChangeRecord.objects.get(type=DELETE_INST)
    assert record.before_data["inst_name"] == expected["software_inst_name"]
    assert record.model_id == "pc_software"

    # 第 4 轮：partial 快照（重新发现同一软件但采集不完整）→ 永不删除
    fd = _run_plugin(
        task,
        _round(vm_doc, "win-s4", BASE_TS + 900, status="partial"),
    )
    assert fd["delete"] == []
    assert fd["pc_summary"]["pc_partial"] == 1
    assert ChangeRecord.objects.filter(type=DELETE_INST).count() == 1  # 仅第 3 轮那一条

    # 链路产物秘密扫描
    _assert_no_secret_leak(vm_doc, fd, [dict(r.before_data) for r in ChangeRecord.objects.all()])


# ---------------------------------------------------------------- macOS 三轮


@pytest.mark.django_db
def test_macos_pipeline_add_update_partial_keeps(load_fixture, graph):
    expected = EXPECTED["macos"]
    vm_doc = load_fixture("pc/macos_vm_rows.json")
    task = _db_task()

    # 第 1 轮：初始新增
    fd = _run_plugin(task, _round(vm_doc, "mac-s1", BASE_TS))
    assert fd["delete"] == []
    assert [row["inst_name"] for row in fd["add"]] == [expected["pc_inst_name"]]
    final_pc = graph.store[expected["pc_inst_name"]]
    assert final_pc["inst_name"] == expected["pc_inst_name"]
    assert final_pc["os_type"] == "macos"
    final_software = graph.store[expected["software_inst_name"]]
    assert final_software["version"] == expected["software_version"]
    assert final_software["product_id"] == "com.google.Chrome"

    # 第 2 轮：升级版本 → 同实例更新
    fd = _run_plugin(
        task,
        _round(vm_doc, "mac-s2", BASE_TS + 300,
               software_overrides={"version": "128.0.6600.1"}),
    )
    assert fd["delete"] == []
    assert graph.store[expected["software_inst_name"]]["version"] == "128.0.6600.1"
    assert fd["pc_summary"]["software_updated"] == 1

    # 第 3 轮：partial 快照 → 永不删除既有软件
    fd = _run_plugin(
        task,
        _round(vm_doc, "mac-s3", BASE_TS + 600, status="partial"),
    )
    assert fd["delete"] == []
    assert expected["software_inst_name"] in graph.store
    assert ChangeRecord.objects.filter(type=DELETE_INST).count() == 0

    _assert_no_secret_leak(vm_doc, fd)


# ------------------------------------------------------------ 失败行与空快照保护


@pytest.mark.django_db
def test_failed_collect_rows_produce_no_snapshot_and_no_delete(load_fixture, graph):
    expected = EXPECTED["windows"]
    vm_doc = load_fixture("pc/windows_vm_rows.json")
    task = _db_task()

    _run_plugin(task, _round(vm_doc, "win-s1", BASE_TS))
    assert expected["software_inst_name"] in graph.store

    # 目标不可达：stargazer 只会落 collect_status=failed 行，全部跳过 → 零快照零删除
    failed_doc = _round(vm_doc, "win-s2", BASE_TS + 300, drop_software=True, expected=0)
    for row in failed_doc["data"]["result"]:
        row["metric"]["collect_status"] = "failed"
        row["metric"]["collect_error"] = "TARGET_UNREACHABLE"
    fd = _run_plugin(task, failed_doc)

    assert fd["add"] == []
    assert fd["update"] == []
    assert fd["delete"] == []
    assert fd["pc_summary"]["pc_total"] == 0
    assert expected["software_inst_name"] in graph.store
    assert ChangeRecord.objects.filter(type=DELETE_INST).count() == 0
