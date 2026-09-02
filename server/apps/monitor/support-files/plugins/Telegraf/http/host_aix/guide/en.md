# AIX Host Collection Guide (resident ksh)

The platform installs the **same original ksh** onto the AIX host on first collect (SRC subsystem `bklite_osmon` via `mkssys` + `startsrc` of a keeper; if SRC is unavailable, a tagged `@reboot` crontab is written only when those markers are missing). A **Linux collect node** then SSH-runs `/usr/bin/ksh -c '/opt/bk-lite/aix/os_monitor.ksh'`. Later scrapes **only execute the installed script**; they do not reinstall or rewrite crontab. AIX is not a bk-lite Node. Do not install Telegraf or node_exporter on AIX, and do not open `:9100`. You do not install Splunk Add-on.

Re-saving an instance **updates the existing child config**; it does not stack a new uuid.

## Prerequisites

- The collect node can SSH to AIX (default port 22) and write `/opt/bk-lite/aix/`.
- Target OS is AIX 7.2 or 7.3 (POWER8+). Missing commands are skipped. Do not use this for AIX 5/6.
- The account must run: `uptime`, `vmstat`, `svmon`, `lsps`, `mpstat`, `lparstat`, `df`, `iostat`, `ps`, `ifconfig`, `netstat`, `oslevel`. SRC install also needs `mkssys`/`lssrc`; otherwise cron is used.
- Firewall: SSH only. Do not open `:9100`.

## Onboarding

1. Pick a Linux collect node that can reach the AIX host.
2. Fill in host IP, username (default `root`), SSH authentication (password or SSH key), and interval (default 60 seconds).
3. After save, the first collect installs ksh at `/opt/bk-lite/aix/os_monitor.ksh` and `startsrc` the SRC keeper when available. Later intervals only SSH-run that script.

## Form fields

| Field | Required | Notes |
| --- | --- | --- |
| Target Host IP | Yes | AIX address. |
| Username | Yes | SSH user, default `root`. |
| SSH Authentication | Yes | Password or SSH key. |
| Password / SSH Private Key | Depends | Encrypted at rest; logs do not print private keys. |
| Port | No | SSH port, default 22. |
| Collection Interval | Yes | Default 60 seconds. |
| Node | Yes | Linux collect node used for SSH and file transfer. |

## After onboarding

Confirm `/opt/bk-lite/aix/os_monitor.ksh` exists on AIX, SRC `bklite_osmon` is active (or crontab markers exist), then query `cpu_usage_total`, `mem_used_percent`, `disk_used_percent`, `disk_iused`, and `disk_ifree` after one interval. The Host dashboard is reused.

After deploy, run `plugin_init` (or `batch_init`) so the plugin definition is imported.
