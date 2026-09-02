# AIX Host Collection Guide (resident ksh)

The platform installs the **same original ksh** onto the AIX host (SRC subsystem `bklite_osmon` when available, otherwise a tagged crontab), then a **Linux collect node** SSH-runs `/usr/bin/ksh -c '/opt/bk-lite/aix/os_monitor.ksh'`. AIX is not a bk-lite Node. Do not install Telegraf or node_exporter on AIX, and do not open `:9100`. You do not install Splunk Add-on.

Re-saving an instance **updates the existing child config**; it does not stack a new uuid.

## Prerequisites

- The collect node can SSH to AIX (default port 22) and write `/opt/bk-lite/aix/`.
- Target OS is AIX 7.2 or 7.3 (POWER8+). Missing commands are skipped. Do not use this for AIX 5/6.
- The account must run: `uptime`, `vmstat`, `svmon`, `lsps`, `mpstat`, `lparstat`, `df`, `iostat`, `ps`, `ifconfig`, `netstat`, `oslevel`. SRC install also needs `mkssys`/`lssrc`; otherwise cron is used.
- Firewall: SSH only. Do not open `:9100`.

## Onboarding

1. Pick a Linux collect node that can reach the AIX host.
2. Fill in host IP, username (default `root`), SSH authentication (password or SSH key), and interval (default 60 seconds).
3. After save, the platform installs ksh at `/opt/bk-lite/aix/os_monitor.ksh` and SSH-runs it on the collection interval.

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

Confirm `/opt/bk-lite/aix/os_monitor.ksh` exists on AIX, then query `cpu_usage_total`, `mem_used_percent`, and `disk_used_percent` after one interval. The Host dashboard is reused.

After deploy, run `plugin_init` (or `batch_init`) so the plugin definition is imported.
