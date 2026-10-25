"""Hyper-V 配置采集契约：独立插件、WinRM、延迟不入库。"""

from pathlib import Path

STARGAZER_LINUX = Path(__file__).resolve().parents[4] / "agents/stargazer/plugins/inputs/host/host_default_discover.sh"
HYPERV_DISCOVER = Path(__file__).resolve().parents[4] / "agents/stargazer/plugins/inputs/hyperv_host/hyperv_discover.ps1"
METRICS = Path(__file__).resolve().parents[2] / "monitor/support-files/plugins/Telegraf/http/hyperv/metrics.json"
POLICY = Path(__file__).resolve().parents[2] / "monitor/support-files/plugins/Telegraf/http/hyperv/policy.json"


def test_linux_host_discover_script_has_no_hyperv():
    text = STARGAZER_LINUX.read_text(encoding="utf-8")
    assert "Get-VM" not in text
    assert "Hyper-V" not in text


def test_hyperv_cmdb_plugin_contract():
    from apps.cmdb.collection.plugins.community.vm.hyperv import HYPERV_MODEL_FIELD_MAPPING, HypervHostCollectionPlugin
    from apps.cmdb.collection.plugins.registry import CollectionPluginRegistry
    from apps.cmdb.constants.constants import CollectPluginTypes

    assert HypervHostCollectionPlugin.supported_model_id == "hyperv_host"
    assert HypervHostCollectionPlugin.supported_task_type == CollectPluginTypes.VM
    host_fields = set(HYPERV_MODEL_FIELD_MAPPING["hyperv_host"])
    vm_fields = set(HYPERV_MODEL_FIELD_MAPPING["hyperv_vm"])
    for banned in ("storage_read_latency", "storage_write_latency", "read_latency_ms", "write_latency_ms"):
        assert banned not in host_fields
        assert banned not in vm_fields
    plugin = CollectionPluginRegistry.get_plugin(CollectPluginTypes.VM, "hyperv_host")
    assert plugin is HypervHostCollectionPlugin


def test_hyperv_in_collect_object_tree_as_winrm_job():
    from apps.cmdb.constants.constants import COLLECT_OBJ_TREE, CollectDriverTypes, CollectPluginTypes

    children = [child for group in COLLECT_OBJ_TREE if group["id"] == "vmware" for child in group["children"]]
    host_ids = {child["id"] for child in children}
    assert "hyperv_host" in host_ids
    assert "vmware_vc" in host_ids
    entry = next(child for child in children if child["id"] == "hyperv_host")
    assert entry["task_type"] == CollectPluginTypes.VM
    assert entry["type"] == CollectDriverTypes.JOB
    assert "WinRM" in entry["tag"]
    host_group = next(group for group in COLLECT_OBJ_TREE if group["id"] == "host_manage")
    assert "hyperv_host" not in {child["id"] for child in host_group["children"]}


def test_job_collect_routes_vm_tasks():
    from apps.cmdb.collection.collect_tasks.job_collect import JobCollect
    from apps.cmdb.constants.constants import CollectPluginTypes

    assert CollectPluginTypes.VM in JobCollect(task=type("T", (), {"id": 1, "instances": []})()).collect_manage


def test_hyperv_vault_binding_is_winrm():
    from apps.cmdb.services.collect_vault_binding import binding_for_collect_object

    assert binding_for_collect_object("hyperv_host", model_id="hyperv_host", driver_type="job") == "host/winrm"


def test_monitor_latency_metrics_are_milliseconds_without_builtin_alert():
    import json

    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    by_name = {item["name"]: item for obj in metrics["objects"] for item in obj["metrics"]}
    assert by_name["storage_read_latency"]["unit"] == "ms"
    assert by_name["storage_write_latency"]["unit"] == "ms"
    for item in by_name.values():
        if item["name"] in {"hyperv_host_count", "hyperv_vm_count"}:
            continue
        assert "_gauge{" in item["query"], item["name"]
    assert policy["templates"] == []


def test_hyperv_models_in_xlsx_have_no_latency_fields():
    import pandas as pd

    xlsx = Path(__file__).resolve().parents[1] / "support-files/model_config.xlsx"
    models = pd.read_excel(xlsx, sheet_name="models", header=1)
    assert set(models["model_id"]) >= {"hyperv_host", "hyperv_vm"}
    for model_id in ("hyperv_host", "hyperv_vm"):
        attrs = set(pd.read_excel(xlsx, sheet_name=f"attr-{model_id}", header=1)["attr_id"].astype(str))
        assert "storage_read_latency" not in attrs
        assert "storage_write_latency" not in attrs
        assert "tag" in attrs


def test_hyperv_discover_script_uses_virtualization_namespace():
    text = HYPERV_DISCOVER.read_text(encoding="utf-8")
    assert "Get-VMHost" in text
    assert "Get-VM" in text
    assert "root\\virtualization\\v2" in text or r"root\virtualization\v2" in text
    assert "storage_read_latency" not in text
    assert "storage_write_latency" not in text
