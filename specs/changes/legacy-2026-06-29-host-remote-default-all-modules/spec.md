# Historical Superpowers change: 2026-06-29-host-remote-default-all-modules

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-29-host-remote-default-all-modules.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Host Remote and Windows WMI collect all host metric modules by default, hide module selection from users, migrate existing child configs to full collection, and fill missing Host metric translations.

**Architecture:** Keep the behavior in the existing plugin-template pipeline. UI JSON supplies a hidden default `metrics_modules` value, Jinja child templates and Stargazer API provide full-collection fallbacks, and `plugin_migrate.py` performs a targeted idempotent child-config repair for existing Host Remote / Windows WMI configs.

**Tech Stack:** Django 4.2 monitor app, JSON plugin templates, Jinja/TOML child templates, Stargazer Sanic API, pytest, PyYAML.

---

## File Structure

- Modify `server/apps/monitor/support-files/plugins/Telegraf/http/host/UI.json`
  - Replace the visible `metrics_modules` `checkbox_group` with a hidden field whose default is the full module list.
- Modify `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json`
  - Make the same hidden-field change for Windows WMI.
- Modify `server/apps/monitor/support-files/plugins/Telegraf/http/host/host.child.toml.j2`
  - Change Host Remote template fallback modules to full collection.
- Modify `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2`
  - Keep Windows WMI fallback full collection and verify it in tests.
- Modify `agents/stargazer/api/monitor.py`
  - Change Host Remote API fallback modules to full collection.
- Modify `server/apps/monitor/management/services/plugin_migrate.py`
  - Add constants for the full module list.
  - Add a pure helper to replace a `metrics_modules = "..."` TOML line.
  - Add an idempotent sync function that filters Host Remote / Windows WMI `CollectConfig` rows and updates matching NodeMgmt child configs.
  - Call the sync function after plugin templates are imported.
- Modify `server/apps/monitor/language/zh-Hans.yaml`
  - Add missing Host metric group and metric translations.
- Modify `server/apps/monitor/language/en.yaml`
  - Add matching English translations.
- Create `server/apps/monitor/tests/test_host_remote_default_all_modules.py`
  - Add static template/UI/language tests and migration-helper tests.
- Modify `agents/stargazer/tests/test_api_http_layer.py`
  - Add direct API tests proving Host Remote and Windows WMI default missing `metrics_modules` headers to full collection.

---

### Task 1: Add Failing Server-Side Guard Tests

**Files:**
- Create: `server/apps/monitor/tests/test_host_remote_default_all_modules.py`

- [ ] **Step 1: Write static guard tests for UI templates, child templates, Stargazer source fallback, language coverage, and migration helpers**

Create `server/apps/monitor/tests/test_host_remote_default_all_modules.py` with this content:

```python
# -*- coding: utf-8 -*-
import json
from pathlib import Path

import pytest
import yaml

from apps.monitor.management.services import plugin_migrate
from apps.monitor.models import CollectConfig, MonitorObject, MonitorPlugin
from apps.monitor.models.monitor_object import MonitorInstance


REPO_ROOT = Path(__file__).resolve().parents[4]
MONITOR_ROOT = REPO_ROOT / "server/apps/monitor"
ALL_MODULES = ["cpu", "mem", "disk", "diskio", "net", "processes", "system"]
ALL_MODULES_CSV = ",".join(ALL_MODULES)

HOST_UI = MONITOR_ROOT / "support-files/plugins/Telegraf/http/host/UI.json"
WINDOWS_WMI_UI = MONITOR_ROOT / "support-files/plugins/Telegraf/http/windows_wmi/UI.json"
HOST_TEMPLATE = MONITOR_ROOT / "support-files/plugins/Telegraf/http/host/host.child.toml.j2"
WINDOWS_WMI_TEMPLATE = MONITOR_ROOT / "support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2"
HOST_METRICS = MONITOR_ROOT / "support-files/plugins/Telegraf/http/host/metrics.json"
WINDOWS_WMI_METRICS = MONITOR_ROOT / "support-files/plugins/Telegraf/http/windows_wmi/metrics.json"
ZH_LANG = MONITOR_ROOT / "language/zh-Hans.yaml"
EN_LANG = MONITOR_ROOT / "language/en.yaml"
STARGAZER_MONITOR = REPO_ROOT / "agents/stargazer/api/monitor.py"


def _load_json(path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_yaml(path):
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _field_by_name(ui, name):
    return next(field for field in ui["form_fields"] if field["name"] == name)


def _metric_names(path):
    return {metric["name"] for metric in _load_json(path)["metrics"]}


def _metric_groups(path):
    return {metric["metric_group"] for metric in _load_json(path)["metrics"]}


@pytest.mark.parametrize("path", [HOST_UI, WINDOWS_WMI_UI])
def test_remote_host_plugin_ui_hides_metrics_modules(path):
    ui = _load_json(path)

    field = _field_by_name(ui, "metrics_modules")

    assert field["type"] == "hidden"
    assert field["default_value"] == ALL_MODULES
    assert field.get("options") is None
    assert field.get("label") is None


@pytest.mark.parametrize("path", [HOST_TEMPLATE, WINDOWS_WMI_TEMPLATE])
def test_remote_host_child_templates_default_to_full_modules(path):
    content = path.read_text(encoding="utf-8")

    assert f"default('{ALL_MODULES_CSV}', true)" in content
    assert "default('cpu,mem,disk,net', true)" not in content


def test_stargazer_monitor_api_defaults_to_full_modules():
    content = STARGAZER_MONITOR.read_text(encoding="utf-8")

    assert f'request.headers.get("metrics_modules", "{ALL_MODULES_CSV}")' in content
    assert 'request.headers.get("metrics_modules", "cpu,mem,disk,net")' not in content


@pytest.mark.parametrize("lang_path", [ZH_LANG, EN_LANG])
def test_remote_host_metric_groups_and_names_are_bilingual(lang_path):
    lang = _load_yaml(lang_path)
    host_groups = lang["monitor_object_metric_group"]["Host"]
    host_metrics = lang["monitor_object_metric"]["Host"]

    required_groups = _metric_groups(HOST_METRICS) | _metric_groups(WINDOWS_WMI_METRICS)
    required_metrics = _metric_names(HOST_METRICS) | _metric_names(WINDOWS_WMI_METRICS)

    missing_groups = sorted(required_groups - set(host_groups))
    missing_metrics = sorted(required_metrics - set(host_metrics))

    assert missing_groups == []
    assert missing_metrics == []


def test_replace_metrics_modules_line_forces_full_modules_and_is_idempotent():
    original = (
        '[[inputs.prometheus]]\n'
        '    urls = ["${STARGAZER_URL}/api/monitor/host/metrics"]\n'
        '    [inputs.prometheus.http_headers]\n'
        '        metrics_modules = "cpu,mem,disk,net"\n'
        '        collect_type = "http"\n'
    )

    updated, changed = plugin_migrate._replace_remote_host_metrics_modules_line(original)
    updated_again, changed_again = plugin_migrate._replace_remote_host_metrics_modules_line(updated)

    assert changed is True
    assert f'metrics_modules = "{ALL_MODULES_CSV}"' in updated
    assert 'metrics_modules = "cpu,mem,disk,net"' not in updated
    assert updated_again == updated
    assert changed_again is False


def test_replace_metrics_modules_line_ignores_missing_and_commented_lines():
    content = (
        '[[inputs.prometheus]]\n'
        '    # metrics_modules = "cpu,mem,disk,net"\n'
        '    collect_type = "http"\n'
    )

    updated, changed = plugin_migrate._replace_remote_host_metrics_modules_line(content)

    assert updated == content
    assert changed is False


@pytest.mark.django_db
def test_sync_remote_host_child_configs_updates_only_host_remote_and_wmi(monkeypatch):
    monitor_object = MonitorObject.objects.create(name="Host")
    plugin = MonitorPlugin.objects.create(name="Host Remote", collector="Telegraf", collect_type="http")

    def create_collect_config(config_id, instance_id, collect_type, config_type, is_child):
        instance = MonitorInstance.objects.create(
            id=instance_id,
            name=instance_id,
            monitor_object=monitor_object,
        )
        CollectConfig.objects.create(
            id=config_id,
            monitor_instance=instance,
            monitor_plugin=plugin,
            collector="Telegraf",
            collect_type=collect_type,
            config_type=config_type,
            file_type="toml",
            is_child=is_child,
        )

    create_collect_config("sync-host", "host-1", "http", "host", True)
    create_collect_config("sync-wmi", "host-2", "http", "windows_wmi", True)
    create_collect_config("skip-snmp", "host-3", "snmp", "host", True)
    create_collect_config("skip-base", "host-4", "http", "host", False)
    create_collect_config("skip-other", "host-5", "http", "other", True)

    child_contents = {
        "sync-host": 'metrics_modules = "cpu,mem,disk,net"\n',
        "sync-wmi": 'metrics_modules = "cpu,mem,disk,net"\n',
        "skip-snmp": 'metrics_modules = "cpu,mem,disk,net"\n',
        "skip-base": 'metrics_modules = "cpu,mem,disk,net"\n',
        "skip-other": 'metrics_modules = "cpu,mem,disk,net"\n',
    }
    requested_ids = []
    updates = {}

    class FakeNodeMgmt:
        def get_child_configs_by_ids(self, ids):
            requested_ids.extend(ids)
            return [{"id": config_id, "content": child_contents[config_id]} for config_id in ids]

        def update_child_config_content(self, config_id, content, env_config=None):
            updates[config_id] = content
            child_contents[config_id] = content

    monkeypatch.setattr(plugin_migrate, "NodeMgmt", FakeNodeMgmt)

    updated_count = plugin_migrate._sync_remote_host_metrics_modules()
    updated_count_again = plugin_migrate._sync_remote_host_metrics_modules()

    assert updated_count == 2
    assert updated_count_again == 0
    assert set(requested_ids) == {"sync-host", "sync-wmi"}
    assert set(updates) == {"sync-host", "sync-wmi"}
    assert updates["sync-host"] == f'metrics_modules = "{ALL_MODULES_CSV}"\n'
    assert updates["sync-wmi"] == f'metrics_modules = "{ALL_MODULES_CSV}"\n'
```

- [ ] **Step 2: Run the new server tests and verify they fail for current behavior**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_host_remote_default_all_modules.py -q
```

Expected: FAIL. At minimum:

- `test_remote_host_plugin_ui_hides_metrics_modules` fails because both UI templates still use `checkbox_group`.
- `test_remote_host_child_templates_default_to_full_modules` fails for Host Remote because its template still defaults to `cpu,mem,disk,net`.
- `test_stargazer_monitor_api_defaults_to_full_modules` fails because Host Remote API still defaults to `cpu,mem,disk,net`.
- Migration helper tests fail because `_replace_remote_host_metrics_modules_line` and `_sync_remote_host_metrics_modules` do not exist.

---

### Task 2: Hide Module Selection and Normalize Template/API Defaults

**Files:**
- Modify: `server/apps/monitor/support-files/plugins/Telegraf/http/host/UI.json`
- Modify: `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json`
- Modify: `server/apps/monitor/support-files/plugins/Telegraf/http/host/host.child.toml.j2`
- Modify: `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2`
- Modify: `agents/stargazer/api/monitor.py`
- Test: `server/apps/monitor/tests/test_host_remote_default_all_modules.py`

- [ ] **Step 1: Replace Host Remote `metrics_modules` UI field**

In `server/apps/monitor/support-files/plugins/Telegraf/http/host/UI.json`, replace the existing `metrics_modules` field object with:

```json
{
  "name": "metrics_modules",
  "type": "hidden",
  "default_value": ["cpu", "mem", "disk", "diskio", "net", "processes", "system"],
  "transform_on_edit": {
    "origin_path": "child.content.config.http_headers.metrics_modules",
    "to_api": {
      "type": "string"
    }
  }
}
```

- [ ] **Step 2: Replace Windows WMI `metrics_modules` UI field**

In `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json`, replace the existing `metrics_modules` field object with:

```json
{
  "name": "metrics_modules",
  "type": "hidden",
  "default_value": ["cpu", "mem", "disk", "diskio", "net", "processes", "system"],
  "transform_on_edit": {
    "origin_path": "child.content.config.http_headers.metrics_modules",
    "to_api": {
      "type": "string"
    }
  }
}
```

- [ ] **Step 3: Update Host Remote child template fallback**

In `server/apps/monitor/support-files/plugins/Telegraf/http/host/host.child.toml.j2`, change:

```toml
        metrics_modules = "{{ metrics_modules | default('cpu,mem,disk,net', true) }}"
```

to:

```toml
        metrics_modules = "{{ metrics_modules | default('cpu,mem,disk,diskio,net,processes,system', true) }}"
```

- [ ] **Step 4: Keep Windows WMI child template fallback full collection**

In `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2`, ensure the line is:

```toml
        metrics_modules = "{{ metrics_modules | default('cpu,mem,disk,diskio,net,processes,system', true) }}"
```

- [ ] **Step 5: Update Host Remote Stargazer API fallback**

In `agents/stargazer/api/monitor.py`, inside `host_metrics`, change:

```python
    metrics_modules = request.headers.get("metrics_modules", "cpu,mem,disk,net")
```

to:

```python
    metrics_modules = request.headers.get("metrics_modules", "cpu,mem,disk,diskio,net,processes,system")
```

- [ ] **Step 6: Run the static default tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_host_remote_default_all_modules.py::test_remote_host_plugin_ui_hides_metrics_modules apps/monitor/tests/test_host_remote_default_all_modules.py::test_remote_host_child_templates_default_to_full_modules apps/monitor/tests/test_host_remote_default_all_modules.py::test_stargazer_monitor_api_defaults_to_full_modules -q
```

Expected: PASS for these three tests.

- [ ] **Step 7: Commit template/API default changes**

Run:

```bash
git add server/apps/monitor/support-files/plugins/Telegraf/http/host/UI.json \
  server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json \
  server/apps/monitor/support-files/plugins/Telegraf/http/host/host.child.toml.j2 \
  server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2 \
  agents/stargazer/api/monitor.py \
  server/apps/monitor/tests/test_host_remote_default_all_modules.py
git commit -m "fix(monitor): default remote host modules to full collection"
```

---

### Task 3: Add Idempotent Existing Child Config Migration

**Files:**
- Modify: `server/apps/monitor/management/services/plugin_migrate.py`
- Test: `server/apps/monitor/tests/test_host_remote_default_all_modules.py`

- [ ] **Step 1: Add imports and constants to `plugin_migrate.py`**

Near the top of `server/apps/monitor/management/services/plugin_migrate.py`, after existing imports, add:

```python
from apps.rpc.node_mgmt import NodeMgmt
```

After `TEMPLATE_COLLECT_TYPE_PATTERN`, add:

```python
REMOTE_HOST_METRICS_MODULES = (
    "cpu",
    "mem",
    "disk",
    "diskio",
    "net",
    "processes",
    "system",
)
REMOTE_HOST_METRICS_MODULES_CSV = ",".join(REMOTE_HOST_METRICS_MODULES)
REMOTE_HOST_CONFIG_TYPES = ("host", "windows_wmi")
METRICS_MODULES_TOML_LINE_PATTERN = re.compile(r'(?m)^(\s*metrics_modules\s*=\s*)"[^"\n]*"')
```

- [ ] **Step 2: Add the pure line replacement helper**

In `server/apps/monitor/management/services/plugin_migrate.py`, after `_collect_file_supplementary_indicators`, add:

```python
def _replace_remote_host_metrics_modules_line(content: str):
    """Force a Telegraf child config metrics_modules line to the full host module list."""
    if not content:
        return content, False

    replacement = rf'\1"{REMOTE_HOST_METRICS_MODULES_CSV}"'
    updated, count = METRICS_MODULES_TOML_LINE_PATTERN.subn(replacement, content)
    if count == 0 or updated == content:
        return content, False

    return updated, True
```

- [ ] **Step 3: Add the DB/RPC sync function**

In `server/apps/monitor/management/services/plugin_migrate.py`, after `_replace_remote_host_metrics_modules_line`, add:

```python
def _sync_remote_host_metrics_modules():
    """Update existing Host Remote / Windows WMI child configs to full metrics module collection."""
    from apps.monitor.models import CollectConfig

    config_ids = list(
        CollectConfig.objects.filter(
            collect_type="http",
            config_type__in=REMOTE_HOST_CONFIG_TYPES,
            is_child=True,
        ).values_list("id", flat=True)
    )
    if not config_ids:
        logger.info("Host Remote / Windows WMI 子配置不存在，跳过采集模块修复")
        return 0

    node_mgmt = NodeMgmt()
    child_configs = node_mgmt.get_child_configs_by_ids(config_ids) or []
    updated_count = 0

    for child_config in child_configs:
        config_id = child_config.get("id")
        content = child_config.get("content") or ""
        updated_content, changed = _replace_remote_host_metrics_modules_line(content)
        if not changed:
            continue

        node_mgmt.update_child_config_content(config_id, updated_content)
        updated_count += 1

    logger.info(f"Host Remote / Windows WMI 采集模块修复完成: 更新={updated_count}")
    return updated_count
```

- [ ] **Step 4: Call the sync function from `migrate_plugin`**

In `migrate_plugin`, immediately after:

```python
    stats = _batch_save_templates(templates_data)
```

add:

```python
    remote_host_metrics_module_updates = _sync_remote_host_metrics_modules()
```

After the template stats logs, add:

```python
    logger.info(f"Host Remote / Windows WMI 采集模块修复: 更新={remote_host_metrics_module_updates}")
```

- [ ] **Step 5: Run the migration helper tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_host_remote_default_all_modules.py::test_replace_metrics_modules_line_forces_full_modules_and_is_idempotent apps/monitor/tests/test_host_remote_default_all_modules.py::test_replace_metrics_modules_line_ignores_missing_and_commented_lines apps/monitor/tests/test_host_remote_default_all_modules.py::test_sync_remote_host_child_configs_updates_only_host_remote_and_wmi -q
```

Expected: PASS.

- [ ] **Step 6: Run existing plugin migration identity tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_plugin_migrate_identity.py -q
```

Expected: PASS. This verifies the new `migrate_plugin` hook does not break existing plugin import idempotence.

- [ ] **Step 7: Commit migration logic**

Run:

```bash
git add server/apps/monitor/management/services/plugin_migrate.py \
  server/apps/monitor/tests/test_host_remote_default_all_modules.py
git commit -m "fix(monitor): migrate remote host modules to full collection"
```

---

### Task 4: Fill Host Metric Group and Metric Translations

**Files:**
- Modify: `server/apps/monitor/language/zh-Hans.yaml`
- Modify: `server/apps/monitor/language/en.yaml`
- Test: `server/apps/monitor/tests/test_host_remote_default_all_modules.py`

- [ ] **Step 1: Add missing Host group translations in Chinese**

In `server/apps/monitor/language/zh-Hans.yaml`, under `monitor_object_metric_group.Host`, keep existing keys and add:

```yaml
    Network: 网络
    Processes: 进程
```

The resulting Host group block must include both the old keys and new keys:

```yaml
  Host:
    CPU: CPU
    System: 系统
    Disk IO: 磁盘 IO
    Disk: 磁盘
    Process: 进程
    Processes: 进程
    Memory: 内存
    Net: 网络
    Network: 网络
    Nvidia GPU: Nvidia GPU
```

- [ ] **Step 2: Add missing Host group translations in English**

In `server/apps/monitor/language/en.yaml`, under `monitor_object_metric_group.Host`, keep existing keys and add:

```yaml
    Network: Network
    Processes: Processes
```

The resulting Host group block must include both the old keys and new keys:

```yaml
  Host:
    CPU: CPU
    System: System
    Disk IO: Disk I/O
    Disk: Disk
    Process: Process
    Processes: Processes
    Memory: Memory
    Net: Net
    Network: Network
    Nvidia GPU: Nvidia GPU
```

- [ ] **Step 3: Add missing Host metric translations in Chinese**

In `server/apps/monitor/language/zh-Hans.yaml`, under `monitor_object_metric.Host`, add these entries if they are absent:

```yaml
    system_uptime:
      name: 系统运行时长
      desc: 表示主机自上次启动以来持续运行的时间，用于识别重启、异常恢复或稳定性变化。
    net_packets_recv_total:
      name: 网络接收包总数
      desc: 表示网络接口累计接收的数据包数量，用于观察接口接收流量规模。
    net_packets_sent_total:
      name: 网络发送包总数
      desc: 表示网络接口累计发送的数据包数量，用于观察接口发送流量规模。
    net_drop_in_total:
      name: 网络接收丢包总数
      desc: 表示网络接口累计丢弃的接收数据包数量，用于排查接收方向拥塞或异常。
    net_drop_out_total:
      name: 网络发送丢包总数
      desc: 表示网络接口累计丢弃的发送数据包数量，用于排查发送方向拥塞或异常。
    diskio_reads_total:
      name: 磁盘读取次数
      desc: 表示磁盘设备累计完成的读取操作次数，用于分析磁盘读请求规模。
    diskio_writes_total:
      name: 磁盘写入次数
      desc: 表示磁盘设备累计完成的写入操作次数，用于分析磁盘写请求规模。
    diskio_read_bytes_total:
      name: 磁盘读取字节数
      desc: 表示磁盘设备累计读取的数据量，用于评估读方向吞吐规模。
    diskio_write_bytes_total:
      name: 磁盘写入字节数
      desc: 表示磁盘设备累计写入的数据量，用于评估写方向吞吐规模。
```

- [ ] **Step 4: Add missing Host metric translations in English**

In `server/apps/monitor/language/en.yaml`, under `monitor_object_metric.Host`, add these entries if they are absent:

```yaml
    system_uptime:
      name: System Uptime
      desc: Represents how long the host has been running since the last boot, useful for detecting restarts, recovery events, or stability changes.
    net_packets_recv_total:
      name: Network Received Packets Total
      desc: Represents the cumulative number of packets received by a network interface, used to understand inbound packet volume.
    net_packets_sent_total:
      name: Network Sent Packets Total
      desc: Represents the cumulative number of packets sent by a network interface, used to understand outbound packet volume.
    net_drop_in_total:
      name: Network Receive Drops Total
      desc: Represents the cumulative number of incoming packets dropped by a network interface, useful for diagnosing inbound congestion or errors.
    net_drop_out_total:
      name: Network Send Drops Total
      desc: Represents the cumulative number of outgoing packets dropped by a network interface, useful for diagnosing outbound congestion or errors.
    diskio_reads_total:
      name: Disk Reads Total
      desc: Represents the cumulative number of read operations completed by a disk device, used to analyze read request volume.
    diskio_writes_total:
      name: Disk Writes Total
      desc: Represents the cumulative number of write operations completed by a disk device, used to analyze write request volume.
    diskio_read_bytes_total:
      name: Disk Read Bytes Total
      desc: Represents the cumulative amount of data read from a disk device, used to evaluate read throughput volume.
    diskio_write_bytes_total:
      name: Disk Write Bytes Total
      desc: Represents the cumulative amount of data written to a disk device, used to evaluate write throughput volume.
```

- [ ] **Step 5: Run the language coverage test**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_host_remote_default_all_modules.py::test_remote_host_metric_groups_and_names_are_bilingual -q
```

Expected: PASS.

- [ ] **Step 6: Commit translation updates**

Run:

```bash
git add server/apps/monitor/language/zh-Hans.yaml \
  server/apps/monitor/language/en.yaml \
  server/apps/monitor/tests/test_host_remote_default_all_modules.py
git commit -m "fix(monitor): add remote host metric translations"
```

---

### Task 5: Add Stargazer HTTP Default Behavior Tests

**Files:**
- Modify: `agents/stargazer/tests/test_api_http_layer.py`
- Test: `agents/stargazer/tests/test_api_http_layer.py`

- [ ] **Step 1: Add a module-level full-module constant**

In `agents/stargazer/tests/test_api_http_layer.py`, after `_API_DIR = _STARGAZER_ROOT / "api"`, add:

```python
_FULL_HOST_MODULES = "cpu,mem,disk,diskio,net,processes,system"
```

- [ ] **Step 2: Add Host Remote default modules API test**

Inside `class TestMonitorEndpointLogic`, after `test_qcloud_metrics_accepted_returns_prometheus_accepted_format`, add:

```python
    async def test_host_metrics_without_metrics_modules_defaults_to_full_collection(self):
        result = await self.mod.host_metrics(self._req(
            headers={
                "host": "10.0.0.8",
                "username": "root",
                "password": "secret",
                "ansible_node_id": "node-1",
            }
        ))

        assert result["status"] == 200
        queued_payload = self.task_queue.enqueue_collect_task.await_args.args[0]
        assert queued_payload["monitor_type"] == "host"
        assert queued_payload["metrics_modules"] == _FULL_HOST_MODULES
```

- [ ] **Step 3: Add Windows WMI default modules API test**

Inside `class TestMonitorEndpointLogic`, after the Host Remote default test, add:

```python
    async def test_windows_wmi_metrics_without_metrics_modules_defaults_to_full_collection(self):
        result = await self.mod.windows_wmi_metrics(self._req(
            headers={
                "host": "10.0.0.9",
                "username": "DOMAIN\\monitor",
                "password": "secret",
            }
        ))

        assert result["status"] == 200
        queued_payload = self.task_queue.enqueue_collect_task.await_args.args[0]
        assert queued_payload["monitor_type"] == "windows_wmi"
        assert queued_payload["metrics_modules"] == _FULL_HOST_MODULES
```

- [ ] **Step 4: Run the new Stargazer API tests**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_api_http_layer.py::TestMonitorEndpointLogic::test_host_metrics_without_metrics_modules_defaults_to_full_collection tests/test_api_http_layer.py::TestMonitorEndpointLogic::test_windows_wmi_metrics_without_metrics_modules_defaults_to_full_collection -q
```

Expected: PASS.

- [ ] **Step 5: Commit Stargazer tests**

Run:

```bash
git add agents/stargazer/tests/test_api_http_layer.py
git commit -m "test(stargazer): cover remote host full module defaults"
```

---

### Task 6: Final Verification

**Files:**
- Verify all modified files from Tasks 1-5.

- [ ] **Step 1: Run focused server tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_host_remote_default_all_modules.py apps/monitor/tests/test_plugin_migrate_identity.py -q
```

Expected: PASS.

- [ ] **Step 2: Run focused Stargazer tests**

Run:

```bash
cd agents/stargazer && uv run pytest tests/test_api_http_layer.py::TestMonitorEndpointLogic::test_host_metrics_without_metrics_modules_defaults_to_full_collection tests/test_api_http_layer.py::TestMonitorEndpointLogic::test_windows_wmi_metrics_without_metrics_modules_defaults_to_full_collection -q
```

Expected: PASS.

- [ ] **Step 3: Run module gate**

Run:

```bash
cd server && make test
```

Expected: PASS. If this fails because local environment services such as database, Redis, NATS, or `.env` are unavailable, capture the exact error and keep the focused pytest results as the narrower verification evidence.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git diff --stat HEAD
git diff -- server/apps/monitor/support-files/plugins/Telegraf/http/host/UI.json \
  server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json \
  server/apps/monitor/support-files/plugins/Telegraf/http/host/host.child.toml.j2 \
  server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2 \
  agents/stargazer/api/monitor.py \
  server/apps/monitor/management/services/plugin_migrate.py \
  server/apps/monitor/language/zh-Hans.yaml \
  server/apps/monitor/language/en.yaml \
  server/apps/monitor/tests/test_host_remote_default_all_modules.py \
  agents/stargazer/tests/test_api_http_layer.py
```

Expected:

- No visible `checkbox_group` remains for Host Remote / Windows WMI `metrics_modules`.
- No `cpu,mem,disk,net` default remains in Host Remote template or API fallback.
- `plugin_migrate.py` sync only targets `collect_type="http"`, `config_type in ("host", "windows_wmi")`, and `is_child=True`.
- Language files only add Host group/metric translations needed by the two remote host plugins.

- [ ] **Step 5: Final commit if any verification-only fixes were made**

If Tasks 1-5 already created all commits and no further changes remain, skip this step. If final verification required fixes, run:

```bash
git add server/apps/monitor/support-files/plugins/Telegraf/http/host/UI.json \
  server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json \
  server/apps/monitor/support-files/plugins/Telegraf/http/host/host.child.toml.j2 \
  server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2 \
  agents/stargazer/api/monitor.py \
  server/apps/monitor/management/services/plugin_migrate.py \
  server/apps/monitor/language/zh-Hans.yaml \
  server/apps/monitor/language/en.yaml \
  server/apps/monitor/tests/test_host_remote_default_all_modules.py \
  agents/stargazer/tests/test_api_http_layer.py
git commit -m "fix(monitor): stabilize remote host full collection"
```

## specs: 2026-06-29-host-remote-default-all-modules-design.md

## 背景

监控模块的主机远程插件目前在配置页暴露了“采集模块”复选框。用户可以勾选 CPU、Memory、Disk、Disk IO、Network、Processes、System 等模块。截图中暴露出两个问题：

1. 产品期望采集模块默认全部采集，不再让用户在页面上选择。
2. 指标页中部分插件分组和指标名仍显示英文，例如 `Network`、`Processes`，说明语言包存在缺口。

本次范围限定为两个主机远程插件：

- `Host Remote`
- `Windows WMI`

## 目标

1. `Host Remote` 和 `Windows WMI` 新增配置时默认全量采集：`cpu,mem,disk,diskio,net,processes,system`。
2. 配置页不再展示采集模块勾选项。
3. 编辑已有配置时不再允许用户修改采集模块。
4. 已存在的 `Host Remote` / `Windows WMI` 子配置通过幂等修复统一改为全量采集，避免页面隐藏后仍保留部分采集的旧状态。
5. 补齐这两个插件在 Host 对象指标页使用到的中英文分组和指标翻译。

## 非目标

1. 不改变 Stargazer 的采集实现、任务队列或指标生成逻辑。
2. 不重构监控插件 UI 渲染框架。
3. 不清理其他插件的历史翻译缺口。
4. 不引入用户可配置的采集模块开关。

## 方案

### 插件 UI 模板

修改以下插件 UI 模板：

- `server/apps/monitor/support-files/plugins/Telegraf/http/host/UI.json`
- `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json`

将 `metrics_modules` 从可见的 `checkbox_group` 改为 `hidden` 字段，默认值为：

```json
["cpu", "mem", "disk", "diskio", "net", "processes", "system"]
```

前端 `web/src/app/monitor/hooks/integration/useConfigRenderer.tsx` 已支持 `hidden` 类型，隐藏字段仍可进入表单默认值和提交参数，因此不需要扩展前端渲染器。

### 采集模板默认值

修改以下采集模板中的 `metrics_modules` 默认值：

- `server/apps/monitor/support-files/plugins/Telegraf/http/host/host.child.toml.j2`
- `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2`

默认值统一为：

```text
cpu,mem,disk,diskio,net,processes,system
```

同时修改 Stargazer HTTP API 的兜底默认值：

- `agents/stargazer/api/monitor.py`

`/api/monitor/host/metrics` 当前默认是 `cpu,mem,disk,net`，需要改成全量。`/api/monitor/windows/wmi/metrics` 当前已经是全量，保留并用测试覆盖。

### 已有配置迁移

在监控插件迁移流程中增加幂等修复步骤，放在插件模板导入之后执行。

修复对象：

- `CollectConfig.collect_type = "http"`
- `CollectConfig.config_type in {"host", "windows_wmi"}`
- `CollectConfig.is_child = true`
- 关联的 NodeMgmt 子配置内容中包含 `metrics_modules = "..."`

修复行为：

1. 读取对应子配置内容。
2. 将 `metrics_modules = "现有双引号内模块列表"` 替换为 `metrics_modules = "cpu,mem,disk,diskio,net,processes,system"`。
3. 内容已是全量时不更新。
4. 不匹配的配置不修改。

该步骤重复执行结果一致，不依赖用户是否重新编辑配置。

## 翻译

补齐语言包：

- `server/apps/monitor/language/zh-Hans.yaml`
- `server/apps/monitor/language/en.yaml`

### 分组

在 `monitor_object_metric_group.Host` 下补：

- `Network`
- `Processes`

保留已有 `Net`、`Process`，避免影响旧指标或其他页面。

### 指标

在 `monitor_object_metric.Host` 下补齐：

- `system_uptime`
- `net_packets_recv_total`
- `net_packets_sent_total`
- `net_drop_in_total`
- `net_drop_out_total`
- `diskio_reads_total`
- `diskio_writes_total`
- `diskio_read_bytes_total`
- `diskio_write_bytes_total`

这些 key 覆盖 `Host Remote` 缺失的指标翻译；`Windows WMI` 复用 `system_uptime`。

## 测试

新增或更新 monitor 相关测试，覆盖以下断言：

1. `Host Remote` / `Windows WMI` 的 `UI.json` 中 `metrics_modules` 为 `hidden`，默认值为全量模块，不再是可见 `checkbox_group`。
2. `host.child.toml.j2`、`windows_wmi.child.toml.j2` 和 Stargazer API 默认值均为全量模块。
3. 两个插件 `metrics.json` 使用到的 Host 分组和指标 key 在 `zh-Hans.yaml` 与 `en.yaml` 中都有映射。
4. 已有子配置修复逻辑只修改 `collect_type=http` 且 `config_type in {"host", "windows_wmi"}` 的子配置内容，并且重复执行幂等。

最小验证命令：

```bash
cd server && make test
```

如测试耗时过长，可先运行覆盖本次变更的精确 pytest 用例，再补跑模块门禁。

## 风险与处理

1. **旧配置被强制扩展采集范围**：这是本次产品目标。采集量会增加，但两个插件目标就是主机指标全量采集，且页面隐藏后必须避免用户不可见的部分采集状态。
2. **已有翻译 key 命名不一致**：只新增 `Network` / `Processes`，不删除旧 `Net` / `Process`，降低兼容风险。
3. **迁移误改其他插件**：通过 `CollectConfig` 元数据限定 `collect_type`、`config_type`、`is_child`，并只替换明确的 `metrics_modules` 行。

## 验收标准

1. 配置页不再显示 Host Remote / Windows WMI 的采集模块复选框。
2. 新建 Host Remote / Windows WMI 配置时生成的 Telegraf 子配置包含全量 `metrics_modules`。
3. 已存在的 Host Remote / Windows WMI 子配置在迁移后也包含全量 `metrics_modules`。
4. 指标页中 `Network`、`Processes` 分组不再回退显示英文；缺失指标显示对应中英文文案。
5. 相关自动化测试通过。
