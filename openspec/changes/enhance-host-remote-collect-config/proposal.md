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
