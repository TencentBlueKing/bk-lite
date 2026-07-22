# Enhance Host Remote Collect Config

Status: done

## Migration Context

- Legacy source: `openspec/changes/enhance-host-remote-collect-config/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

Host remote collection currently exposes a rough monitor plugin form and omits several execution parameters that are required by common Windows WinRM deployments. Windows collection can fall back to plaintext/basic authentication when `winrm_transport` is not supplied, which fails on default Windows hosts unless Basic auth is explicitly enabled. Customers also need these values configured from the monitor side because Job targets and monitor credentials are separate.

The existing form also asks users to type metric modules manually and does not support Linux private-key credentials. The remote metric set is smaller than the local Telegraf host plugin, which limits reuse of existing dashboards and alert expectations.

## What Changes

- Enhance the Telegraf http host monitor plugin UI so users select metric modules instead of typing a comma-separated string.
- Add monitor-side Windows WinRM options: scheme, transport, and certificate validation, with Windows-friendly defaults.
- Add monitor-side Linux credential mode selection for password or SSH private key with optional passphrase.
- Pass the new fields through the Telegraf http headers to Stargazer.
- Update Stargazer HostCollector to construct Ansible `host_credentials` with WinRM options or SSH key credentials while remaining compatible with existing configs.
- Expand remote host metrics toward the local Telegraf host plugin, prioritizing cross-platform CPU, memory, disk, network, disk I/O, process, and system fields where reliable.
- Keep Job target credentials independent from monitor plugin credentials.

## Capabilities

### Modified Capabilities

- `host-remote-collect`: improve monitor plugin configuration, credential handling, WinRM parameter pass-through, and remote metric coverage.

## Impact

- **Server monitor plugin templates**: update `server/apps/monitor/support-files/plugins/Telegraf/http/host/`.
- **Stargazer**: update HostCollector parameter parsing, host credential construction, script modules, and metric formatting.
- **Ansible Executor**: no API change expected; it already accepts `winrm_scheme`, `winrm_transport`, `winrm_cert_validation`, and SSH key credential fields in `host_credentials`.
- **Compatibility**: existing host remote configs continue to work through defaults and legacy `metrics_modules` parsing.
- **Verification**: add/update tests for template rendering, Windows WinRM headers, Linux private-key credentials, backward compatibility, and expanded metric parsing.

## Implementation Decisions

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

## Capability Deltas

### host-remote-collect

## MODIFIED Requirements

### Requirement: Server 侧注册 Telegraf http 类型主机插件
Server monitor 模块 SHALL provide a Telegraf http host remote collection plugin whose configuration form supports OS-specific credential and protocol options without relying on Job target credentials.

#### Scenario: 用户通过前端配置 Linux 密码采集
- **WHEN** 用户选择 os_type 为 linux，auth_type 为 password，填写 host、username、password、port 和指标模块
- **THEN** 系统生成 Telegraf http input 子配置，headers 包含 Linux SSH 密码采集所需字段，metrics_modules 由所选模块渲染生成

#### Scenario: 用户通过前端配置 Linux 密钥采集
- **WHEN** 用户选择 os_type 为 linux，auth_type 为 private_key，填写 host、username、private_key_content、可选 private_key_passphrase、port 和指标模块
- **THEN** 系统生成 Telegraf http input 子配置，headers 包含 SSH 私钥采集所需字段，敏感字段使用现有加密/env 占位机制

#### Scenario: 用户通过前端配置 Windows WinRM 采集
- **WHEN** 用户选择 os_type 为 windows，填写 host、username、password、port、winrm_scheme、winrm_transport、winrm_cert_validation 和指标模块
- **THEN** 系统生成 Telegraf http input 子配置，headers 包含 Windows WinRM 采集所需字段

#### Scenario: Windows 使用默认 WinRM 配置
- **WHEN** 用户选择 os_type 为 windows 且未显式修改 WinRM 参数
- **THEN** 默认配置为 port=5986、winrm_scheme=https、winrm_transport=ntlm、winrm_cert_validation=false

#### Scenario: Windows 选择 Basic 认证
- **WHEN** 用户选择 winrm_transport 为 basic
- **THEN** 配置表单说明 SHALL 提示目标 Windows 需要开启 Basic 认证，默认 Windows 通常未开启

### Requirement: 异步 Worker 通过 Ansible Executor 执行远程采集
HostCollector Worker SHALL construct Ansible Executor `host_credentials` from monitor-side parameters, including OS-specific credential fields, and SHALL keep Job target credentials independent from monitor credentials.

#### Scenario: Windows WinRM 参数传递
- **WHEN** os_type 为 windows 且请求包含 winrm_scheme=https、winrm_transport=ntlm、winrm_cert_validation=false
- **THEN** Worker 调用 Ansible Executor adhoc 时 host_credentials 包含 connection=winrm、winrm_scheme=https、winrm_transport=ntlm、winrm_cert_validation=false

#### Scenario: Windows 旧配置兼容
- **WHEN** os_type 为 windows 且旧配置未包含 winrm_scheme、winrm_transport 或 winrm_cert_validation
- **THEN** Worker 使用 https、ntlm、false 作为默认值构造 host_credentials

#### Scenario: Linux 私钥凭据传递
- **WHEN** os_type 为 linux 且 auth_type 为 private_key
- **THEN** Worker 调用 Ansible Executor adhoc 时 host_credentials 包含 connection=ssh、private_key_content，并在提供时包含 private_key_passphrase

#### Scenario: Linux 旧配置兼容
- **WHEN** os_type 为 linux 且旧配置未包含 auth_type
- **THEN** Worker 按 password 模式构造 host_credentials

### Requirement: 模块化脚本按需拼接
系统 SHALL support selectable remote host metric modules using UI-controlled values while accepting legacy comma-separated module strings.

#### Scenario: UI 多选模块
- **WHEN** metrics_modules 由表单多选产生为 ["cpu", "mem", "disk"]
- **THEN** Worker SHALL treat it equivalently to "cpu,mem,disk" and only拼接对应模块

#### Scenario: 旧字符串模块
- **WHEN** metrics_modules 为 "cpu,mem,disk,net"
- **THEN** Worker SHALL continue to parse the string and拼接对应模块

### Requirement: 远程主机指标尽量对齐本地 Telegraf Host 指标
Remote host collection SHALL expand metric coverage toward the local Telegraf host plugin and SHALL prefer local Telegraf metric names when the collected value has matching semantics.

#### Scenario: 基础指标对齐
- **WHEN** 用户选择 cpu、mem、disk、net 模块
- **THEN** 输出指标 SHALL include Telegraf-aligned CPU usage, memory, disk, and network metrics where available on the target OS

#### Scenario: 扩展模块采集
- **WHEN** 用户选择 diskio、processes 或 system 模块
- **THEN** Worker SHALL include the corresponding script fragments and emit supported metrics without causing other selected modules to fail when one expanded module is unavailable

#### Scenario: 语义不匹配的 Telegraf 指标
- **WHEN** remote scripts cannot collect a value with the same semantics as a local Telegraf metric, such as a persistent interval-based rate
- **THEN** implementation SHALL avoid misleading metric-name reuse or document the remote-specific semantics in metrics metadata

#### Scenario: GPU 指标
- **WHEN** local Telegraf host plugin includes GPU metrics
- **THEN** remote host collection SHALL NOT require GPU metrics by default because they depend on target-specific tooling

## Work Checklist

## 1. Server Monitor Plugin UI and Template

- [x] 1.1 Update `Telegraf/http/host/UI.json` so `metrics_modules` uses `checkbox_group` with defaults `cpu`, `mem`, `disk`, `net`.
- [x] 1.2 Add Linux credential fields: `auth_type`, password, private key content, and optional private key passphrase, using existing encrypted field patterns.
- [x] 1.3 Add Windows WinRM fields: `winrm_scheme`, `winrm_transport`, and `winrm_cert_validation`, with defaults `https`, `ntlm`, and `false`.
- [x] 1.4 Add UI descriptions that warn Basic transport requires Windows Basic authentication to be enabled on the target.
- [x] 1.5 Update `host.child.toml.j2` to render new values into HTTP headers while preserving existing password env placeholder behavior.
- [x] 1.6 Update or add Server template tests for rendered headers and legacy-safe defaults.

## 2. Stargazer Credential and Parameter Handling

- [x] 2.1 Update HostCollector parameter parsing to accept `metrics_modules` as comma-separated string or array.
- [x] 2.2 Build Linux `host_credentials` with password or private key fields based on monitor `auth_type`.
- [x] 2.3 Build Windows `host_credentials` with `winrm_scheme`, `winrm_transport`, and `winrm_cert_validation`.
- [x] 2.4 Apply backward-compatible defaults for old monitor configs.
- [x] 2.5 Add tests for Windows NTLM credential construction and Linux private-key credential construction.

## 3. Remote Metric Coverage

- [x] 3.1 Compare current remote metric output against `Telegraf/host/os/metrics.json` and document exact supported/unsupported fields in tests or comments.
- [x] 3.2 Expand CPU metrics toward Telegraf-compatible usage fields where available.
- [x] 3.3 Expand memory metrics toward total, available, used percent, swap free, cached, shared, and buffered fields where available.
- [x] 3.4 Expand disk metrics toward total, free, used percent, and inode used percent where available.
- [x] 3.5 Expand network metrics toward bytes, packets, errors, and drops; only use rate metric names when semantics match.
- [x] 3.6 Add `diskio` module support where Linux `/proc/diskstats` and Windows counters provide reliable data.
- [x] 3.7 Add `processes` and `system` module support where platform data is reliable.
- [x] 3.8 Update `Telegraf/http/host/metrics.json` to include the expanded remote metrics, preferring local Telegraf host metric names for matching semantics.
- [x] 3.9 Add Stargazer script/build/parse tests for expanded module output.

## 4. Verification

- [x] 4.1 Run Stargazer host collector tests.
- [x] 4.2 Run Server monitor plugin/template tests.
- [x] 4.3 Run targeted lint/type checks for any frontend plugin-rendering changes if needed.
- [x] 4.4 Manually verify a Windows rendered config includes `winrm_transport=ntlm` and a Linux private-key config does not include plaintext key material in logs.
