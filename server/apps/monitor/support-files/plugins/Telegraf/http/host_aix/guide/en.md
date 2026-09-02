# Host AIX

The monitor object is **Host**. This plugin collects AIX 7.2 / 7.3 OS metrics. The first save installs collection on the target host and keeps it available; later intervals only pull data.

What is collected: CPU (including LPAR entitled capacity), memory and paging, load 1 / 5 / 15, processes and AIX process states, disk capacity / inodes / IO / busy, NICs, uptime, and svmon categories.

## How to use

1. Pick a collect node that can reach the AIX host.
2. Fill in host IP, username, SSH authentication, and interval.
3. Save, wait one interval, then view data on the Host object.

## Form fields

| Field | Required | Notes |
| --- | --- | --- |
| Target Host IP | Yes | AIX address. |
| Username | Yes | Default `root`. |
| SSH Authentication | Yes | Password or SSH key. |
| Password / SSH Private Key | Depends | Password auth needs a password; key auth needs a private key (passphrase optional). |
| Port | No | Default 22. |
| Collection Interval | Yes | Default 60 seconds. |
| Node | Yes | Node that runs collection. |

Supports AIX 7.2 / 7.3. After deploy, run `plugin_init` if this plugin is not yet in the console.
