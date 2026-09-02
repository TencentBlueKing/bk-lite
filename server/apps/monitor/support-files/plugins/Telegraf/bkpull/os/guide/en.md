# Host AIX Monitoring Guide

The platform installs official `node_exporter` on the target AIX host. A Linux collector node then scrapes `:9100/metrics` with Telegraf Prometheus. Do not download or install `node_exporter` yourself from GitHub or any other external source.

## Prerequisites

- The target host is AIX 7.2 / 7.3 on POWER8 or later `ppc64`.
- The collector node must be Linux and must be able to reach port `9100` on the target host.
- On save, the platform uses the collector node to SSH (default port `22`), copy official `node_exporter` 1.12.1 (aix-ppc64) to `/opt/bklite/node_exporter`, and start it with SRC as root on `0.0.0.0:9100`.
- The SSH account needs write access to the install directory and permission to run `mkssys` / `startsrc` / `stopsrc`. `root` is recommended.
- The SRC subsystem name is `node_exporter`. If the subsystem already exists, the platform does not run `mkssys` again. An upgrade stops the subsystem, replaces the binary, then starts it.

## Setup Steps

1. Select a Linux collector node and enter the target AIX host IP, instance name, and SSH credentials.
2. Confirm the collection interval and the `node_exporter` listen port (default `9100`).
3. Run the pre-check. The platform probes **copy → start → scrape → metrics** and stops at the first failed stage.
4. Save the configuration. The platform distributes the Linux Telegraf scrape config and installs or updates `node_exporter` on AIX after the database transaction commits. Changing only the collection interval does not recopy the package.
5. Wait for at least one collection interval. The default interval is `60` seconds.

`plugin_init` is required after deploy. Otherwise the plugin metadata is not loaded into the monitor object.

## Page Fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| Node | Yes | none | Linux collector node that scrapes metrics and performs the remote install. |
| Target Host IP | Yes | none | AIX host address. The Linux collector scrapes `http://<IP>:<port>/metrics`. |
| Instance Name | Yes | none | Display name in the platform. It can start from the target host IP and then be edited. |
| Username | Yes | `root` | SSH login username. It is used only for install and detect, and is not written into the scrape config. |
| Linux Authentication | No | Password | Linux SSH authentication method. |
| Password | Yes | none | SSH/WinRM login password |
| SSH Private Key | No | none | Linux SSH private key content, used only when authentication is SSH Key |
| SSH Private Key Passphrase | No | none | Linux SSH private key passphrase, may be empty |
| Port | No | `9100` | `node_exporter` listen and scrape port, not the SSH port. SSH always uses `22`. |
| Collection Interval | Yes | `60` seconds | Collection time interval (unit: seconds) |
| Group | No | none | Optional instance group. |

## Post-setup Checks

1. On the AIX host, confirm SRC subsystem `node_exporter` is running and listening on `9100`.
2. From the Linux collector node, open `http://<target-host-ip>:9100/metrics` and confirm `node_cpu_`, `node_memory_`, `node_filesystem_`, `node_load`, and `node_partition_` series are present.
3. After at least one collection interval, confirm CPU, memory, disk, network, and LPAR metrics have data on the Host object.

## Common Issues

### Save succeeds but no metrics appear

Confirm the Linux collector can reach AIX port `9100`, and that `plugin_init` has run. The scrape config must not contain an SSH username or password.

### SRC fails to start

Install and start require root. Confirm the account can run `mkssys`, `startsrc`, and `stopsrc`, and that `/opt/bklite/node_exporter` is writable.

### Repeated saves create extra scrape targets

Editing the same instance updates the existing `bkpull/aix` child config and does not create a second `inputs.prometheus` block.
