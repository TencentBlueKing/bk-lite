## Context

The previous `add-host-remote-collect-plugin` change added the Telegraf http -> Stargazer -> Ansible Executor host remote collection path. Field investigation found that Windows hosts fail when the monitor chain does not pass WinRM authentication options. Ansible's WinRM connection plugin chooses plaintext/basic-like behavior when transport is not explicitly set in some deployments, and default Windows hosts usually do not enable Basic authentication.

Job execution already handles these values through `Target.winrm_scheme`, `Target.winrm_transport`, and `Target.winrm_cert_validation`, then passes them to Ansible Executor. Monitor collection cannot reuse Job targets directly because the customer requires monitor credentials to be configured separately from Job credentials.

Remote metric coverage is also below the local Telegraf host plugin. Current remote scripts cover basic `cpu`, `mem`, `disk`, and `net`; local Telegraf host metrics include CPU breakdowns, memory cache/buffer/shared, disk inode data, disk I/O, process states, network packets/drops/errors/rates, and GPU metrics.

## Goals / Non-Goals

**Goals:**
- Let monitor users configure Windows WinRM scheme, transport, and certificate validation.
- Default Windows monitor collection to `https`, `ntlm`, and ignored certificate validation for self-signed WinRM deployments.
- Let monitor users select metric modules with UI controls rather than typing `cpu,mem,disk,net`.
- Support Linux password and SSH private-key credentials in monitor-side configuration.
- Keep old configs working without mandatory migration.
- Expand remote metric coverage toward local Telegraf host metrics where reliable on Linux and Windows.

**Non-Goals:**
- Do not couple monitor host remote collection to Job target credentials.
- Do not require target-side agents.
- Do not make Windows Basic authentication the default.
- Do not promise full one-to-one parity with every Telegraf host metric in this change, especially GPU metrics and platform-specific fields that need additional binaries or drivers.

## Decisions

### 1. Monitor plugin owns its own credential fields

**Choice**: Add required credential fields to the monitor Host Remote plugin and pass them through Telegraf headers.

**Reasoning**: Customer feedback states Job and monitor credentials are different. Reusing Job target records would introduce cross-module coupling and would not solve separate monitor credential management.

### 2. Windows defaults match common WinRM production setup

**Choice**: For Windows, default to:

- `port=5986`
- `winrm_scheme=https`
- `winrm_transport=ntlm`
- `winrm_cert_validation=false`

**Reasoning**: This avoids requiring Basic authentication on Windows hosts. Basic remains selectable for sites that explicitly enable it, but the UI description must warn that Basic is usually disabled by default.

### 3. Linux credentials support password and private key

**Choice**: Add `auth_type=password|private_key`, with password or private key fields conditionally displayed.

**Reasoning**: Ansible Executor already supports `private_key_content` and `private_key_passphrase` in `host_credentials`; Stargazer only needs to pass them through. This brings monitor host collection closer to Job execution capabilities without sharing Job records.

### 4. Metric modules use plugin UI controls

**Choice**: Replace manual `metrics_modules` text input with a `checkbox_group`, following the local Telegraf host plugin pattern. Render the selected list into the HTTP header as a comma-separated string, and keep Stargazer parsing tolerant of both strings and arrays.

**Reasoning**: The existing local host plugin already uses `checkbox_group` for metric type selection, and users should not need to remember module names.

### 5. Remote metrics align by stable subset first

**Choice**: Expand in priority order:

1. Existing module enhancements:
   - CPU: total usage plus user/system/iowait/irq/steal where available.
   - Memory: total, available, used percent, swap free, cached, shared, buffered where available.
   - Disk: total, free, used percent, inode used percent where available.
   - Network: bytes, packets, errors, drops. Prefer rate-style metric names when the script can calculate deltas reliably within one execution.
2. New modules:
   - `diskio`: read/write counts, bytes, utilization or latency where platform data supports it.
   - `processes`: running, blocked, sleeping, zombie counts where platform data supports it.
   - `system`: load or uptime style values where available.
3. Defer GPU by default because Nvidia data needs target tooling and is not a universal host capability.

**Reasoning**: Full Telegraf parity is not realistic in one pass because Telegraf keeps state between intervals for rate calculations, while the remote script executes per request. The implementation should reuse Telegraf-compatible metric names where semantics match and document gaps where remote execution cannot provide an identical value.

## Data Flow

```text
Monitor Host Remote UI
  -> Telegraf host.child.toml.j2 http_headers
  -> Stargazer /api/monitor/host/metrics
  -> HostCollector builds script and host_credentials
  -> Ansible Executor adhoc inventory
  -> SSH / WinRM target
  -> JSON stdout
  -> Prometheus metrics
```

## Compatibility

- Missing Windows fields default to `https`, `ntlm`, and `false` certificate validation.
- Missing Linux `auth_type` defaults to password.
- Existing `metrics_modules="cpu,mem,disk,net"` remains accepted.
- New module selections should not require old configs to be edited.

## Risks / Trade-offs

- **Rate metric parity**: Telegraf can compute rates across intervals; remote scripts may only capture counters or short-window deltas. Metric names must only match Telegraf names when semantics are close enough.
- **Windows process/disk I/O data**: WMI counter availability varies by Windows version and localization. Scripts should fail soft per module and still return other metrics.
- **Credential exposure**: Sensitive fields continue to use existing encrypted/env placeholder patterns and must not be logged.
- **UI dependency support**: Existing plugin UI supports `dependency`; if it cannot express all OS/credential conditions, make the smallest frontend enhancement necessary rather than hardcoding this plugin.
