# HP-UX Host Remote Collection

This is remote HP-UX OS monitoring on the Host object. A Linux collect node SSHes to HP-UX on each interval and runs system commands. The target does not need a collector installed. There is no version picker; version and architecture are detected automatically.

What is collected: CPU, load, memory and swap, disk capacity and inodes, disk busy and throughput, NICs, uptime, and OS version. Hardware inventory, lastlog, lsof, and connection tables are not collected.

## How to use

1. Pick a Linux collect node that can reach the HP-UX host.
2. Fill in host IP, SSH username (for example root), password or private key, and interval.
3. Save, wait one interval, and view data on Host.

## Form fields

| Field | Required | Notes |
| --- | --- | --- |
| Target Host IP | Yes | HP-UX address. |
| Username | Yes | SSH username, for example `root`. |
| SSH Authentication | Yes | Password or SSH key. |
| Password / SSH Private Key | Depends | Password auth needs a password; key auth needs a private key (passphrase optional). |
| Port | No | Default 22. |
| Collection Interval | Yes | Default 60 seconds. |
| Node | Yes | Linux node that runs collection. |

## Commands on the target

The script calls these HP-UX commands as needed. A missing or failed command is skipped, or the next fallback is used:

- `uname`, `model`: OS version and machine
- `uptime`: load and uptime
- `sar -u`, fallback `vmstat`: CPU
- `swapinfo`, and `machinfo` when needed: memory and swap
- `bdf` / `bdf -i`: disk capacity and inodes
- `sar -d`, fallback `iostat`: disk busy and throughput
- `lanscan`, `nwmgr`, `lanadmin`: NIC octet counters; if none of those work, fallback `netstat -in`

## Network throughput may be 0

The preferred path reads NIC octet counters from `nwmgr` or `lanadmin`, then rates adjacent scrapes to get throughput.

If neither path yields octets (command missing, no permission, or parse failure), the script falls back to `netstat -in`. On HP-UX that output is packet counts, not bytes, so `rx_bytes` / `tx_bytes` are recorded as 0 and network throughput is 0. Interface names and error counts may still appear. To see throughput, the collect account must be able to run `nwmgr` or `lanadmin -g mibstats`.

After deploy, run `plugin_init` if this plugin is not yet in the console.
