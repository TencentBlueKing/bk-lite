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
