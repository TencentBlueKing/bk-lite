# Windows WMI Remote Collection Design

## Context

BK-Lite already has two host monitoring paths:

- Local Host: Telegraf runs on the monitored node and uses native host inputs such as `cpu`, `mem`, `disk`, `diskio`, `net`, `processes`, and `system`.
- Host Remote: Telegraf triggers Stargazer, then Stargazer uses Ansible Executor over SSH or WinRM to run host metric scripts.

Some existing Windows customers, especially older Hong Kong deployments, cannot or do not want to enable WinRM. They allow WMI instead. The new plugin must collect Windows host metrics through WMI without deploying a new probe or node.

Stargazer already contains monitoring collectors that connect directly to external systems with host, port, and credentials, such as VMware, QCloud, and OceanStor. Windows WMI should follow that collector model rather than being forced into the Ansible adhoc execution path.

## Goals

- Add a new monitor plugin named `Windows WMI`.
- Collect Windows host metrics remotely through WMI/DCOM from Stargazer.
- Do not deploy a new probe, sidecar, or Windows collection node.
- Do not use WinRM, Ansible adhoc, or ansible-executor for the first version.
- Do not execute scripts on the target Windows host.
- Keep plugin metrics metadata independent through a dedicated `metrics.json`.
- Make collection logs useful for production troubleshooting.
- Use TDD during implementation.

## Non-Goals

- Do not add generic remote command execution through WMI.
- Do not let users configure arbitrary WQL from the UI.
- Do not implement executor fallback or `wmi.collect.{node_id}` in the first version.
- Do not promise GPU parity in the first version.
- Do not redesign the existing Host Remote plugin.

## Architecture

Windows WMI is a Stargazer-native monitoring collector. It should not be placed in the migrated `plugins/inputs` layer or the migrated `common/cmp` / `common/monitor_plugins` layers.

Server plugin files:

```text
server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/
  UI.json
  windows_wmi.child.toml.j2
  metrics.json
  policy.json
```

Stargazer files:

```text
agents/stargazer/tasks/collectors/host_wmi_collector.py
agents/stargazer/tasks/collectors/host_wmi/
  client.py
  modules.py
  metrics.py
  errors.py
```

The `host_wmi` package owns WMI connection, module execution, result normalization, metric conversion, and error classification. `host_wmi_collector.py` integrates that package with the existing Stargazer collector interface.

## Data Flow

```text
Telegraf [[inputs.prometheus]]
  -> GET ${STARGAZER_URL}/api/monitor/windows/wmi/metrics
  -> headers:
       host
       username
       password
       namespace
       metrics_modules
       timeout
       instance_id
       instance_type
       collect_type
       config_type

Stargazer API
  -> validates required headers
  -> enqueues monitor_type=windows_wmi

Stargazer Worker
  -> dispatches monitor_type=windows_wmi
  -> collect_windows_wmi_metrics_task
  -> WindowsWmiCollector.collect()

WindowsWmiCollector
  -> WmiClient connects to target Windows WMI/DCOM
  -> selected modules run read-only WMI queries
  -> structured module data is converted to Prometheus text
  -> metrics are published to NATS
```

## WMI Invocation Model

The collector should use a Python WMI/DCOM client library, with `impacket` as the primary candidate. It should call library APIs directly rather than shelling out to `wmic`, `wmiexec.py`, PowerShell, or any other external command.

The first version must be read-only:

- Query WMI classes and counters.
- Do not call process creation APIs.
- Do not run remote commands.
- Do not upload or execute scripts.

The UI exposes module choices rather than WQL. Module query definitions live in code and are reviewed as part of product behavior.

Default namespace:

```text
root\cimv2
```

Supported first-version modules:

```text
cpu
mem
disk
diskio
net
processes
system
```

## Metrics

The plugin name is `Windows WMI`.

The plugin has its own `metrics.json`. Metric semantics should align with existing Host and Host Remote metrics where practical, but the metadata belongs to this new plugin.

Recommended tagging:

```text
instance_type = "os"
collect_type = "http"
config_type = "windows_wmi"
```

The first version should cover:

- CPU usage and core count.
- Memory total, available, used, used percent, and swap-like values where WMI exposes reliable data.
- Disk total, free, used, and used percent per logical disk.
- Disk IO counters where available.
- Network receive/transmit counters and errors per interface where available.
- Process state/count metrics where available.
- System uptime.

GPU metrics are not required in the first version.

## Logging And Troubleshooting

Production troubleshooting should primarily use logs, not large sets of diagnostic metrics.

Every collection run should carry stable context across API, worker, collector, module, and publish phases:

```text
request_id
task_id
monitor_type=windows_wmi
host
instance_id
modules
```

Sensitive data must not be logged:

- Never log `password`.
- Never log the full credential payload.
- Log username only in masked form, or log `username_present=true`.

Recommended structured events:

```text
wmi_request_received
wmi_task_queued
wmi_collect_start
wmi_connect_start
wmi_connect_success
wmi_connect_failed
wmi_module_start
wmi_module_success
wmi_module_failed
wmi_collect_success
wmi_collect_failed
wmi_metrics_publish_success
wmi_metrics_publish_failed
```

Module failures should log the module name, normalized error type, original exception type, and duration. One module failure should not fail the whole collection when other selected modules succeed.

Connection failures should fail the collection and publish the existing style of monitor error metrics.

Suggested normalized error types:

```text
auth_failed
network_unreachable
rpc_unavailable
dcom_access_denied
namespace_not_found
class_unavailable
query_timeout
query_failed
partial_failure
unknown
```

## User Configuration

The `Windows WMI` plugin UI should expose:

- Target host/IP.
- Username.
- Password.
- Namespace, default `root\cimv2`.
- Metric modules.
- Timeout.
- Collection interval.

The UI and plugin description should state the deployment prerequisites:

- Target Windows WMI service must be enabled.
- The configured account must have WMI read permission.
- Stargazer must be able to reach the target Windows WMI/DCOM/RPC network path.

Avoid suggesting that WMI is a simple single-port protocol in the UI.

## Testing Strategy

Implementation must follow TDD. Tests should be written and observed failing before production code is added.

Required behavior tests:

- API converts headers into a `monitor_type=windows_wmi` task.
- API rejects missing required headers with a Prometheus error response.
- Worker dispatches `monitor_type=windows_wmi` to the Windows WMI handler.
- Collector resolves comma-separated and array module selections.
- Collector calls only selected modules.
- WMI client result data converts to Prometheus text with expected labels.
- A single module failure is logged and does not prevent successful modules from being emitted.
- Connection failure produces the existing monitor error metric path.
- Plugin template renders required headers and encrypted password placeholder.
- `UI.json` and `metrics.json` contain the expected plugin identity and basic fields.

Mocks are acceptable around the WMI network client because live WMI/DCOM requires a Windows target. Tests should exercise real collector parsing, module selection, conversion, and error handling logic.

## Deferred Work

- Executor provider or `wmi.collect.{node_id}` fallback.
- Multi-host batching.
- Arbitrary WQL.
- GPU metrics.
- Deep Windows service/event-log monitoring.

