# AIX Host Remote Collection Guide

This plugin has a **Linux collect node** SSH-run the platform's original ksh with `/usr/bin/ksh -c` to collect AIX 7.2/7.3 (POWER8+) host metrics. You do **not** install Splunk Add-on for Unix and Linux, node_exporter, Telegraf on AIX, or open `:9100`.

## Prerequisites

- The collect node can SSH to the AIX host (default port 22).
- Target OS is AIX 7.2 or 7.3. The script skips missing commands (for example `svmon` on some hosts). Do not use this plugin for AIX 5/6.
- The account must be able to run: `uptime`, `vmstat`, `svmon`, `lsps`, `mpstat`, `lparstat`, `df`, `iostat`, `ps`, `ifconfig`, `netstat`, `oslevel`.
- Firewall: allow SSH from the collect node to AIX only. Do not open `:9100`.

## Onboarding

1. Pick a Linux collect node that can reach the AIX host.
2. Fill in host IP, username (default `root`), SSH authentication (password or SSH key), and interval (default 60 seconds).
3. Save and wait one collection interval. Each scrape SSH-runs ksh; the script is not left resident on AIX.

Re-saving an instance **updates the existing child config**; it does not stack a new uuid.

## Form fields

| Field | Required | Notes |
| --- | --- | --- |
| Target Host IP | Yes | AIX address. |
| Username | Yes | SSH user, default `root`. |
| SSH Authentication | Yes | Password or SSH key. |
| Password / SSH Private Key | Depends | Encrypted at rest; logs do not print private keys. |
| Port | No | SSH port, default 22. |
| Collection Interval | Yes | Default 60 seconds. |
| Node | Yes | Linux collect node that runs SSH. |

## After onboarding

Confirm `cpu_usage_total`, `mem_used_percent`, `disk_used_percent`, and `system_load1` after one interval. The Host dashboard is reused.

After deploy, run `plugin_init` (or `batch_init`) so the plugin definition is imported.

## Troubleshooting

### Missing commands

On AIX 7.x the collector skips commands that are not present (such as `svmon`). Other metrics still collect.

### Authentication failed

Check SSH from the collect node to AIX, username, and auth method. Do not use Host Remote WinRM fields for AIX.
