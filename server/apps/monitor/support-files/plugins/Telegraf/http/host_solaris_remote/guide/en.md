# Solaris Host Remote Collection

This is remote Solaris OS monitoring on the Host object. A Linux collect node SSHes to Solaris on each interval and runs system commands. x86 and SPARC share this plugin; architecture is read from `uname -p`. The target does not need a collector installed. There is no version picker.

What is collected: CPU, load, memory and swap, disk capacity and inodes, disk read/write and busy, NICs, uptime, and OS version. Hardware inventory, lastlog, lsof, and connection tables are not collected.

## How to use

1. Pick a Linux collect node that can reach the Solaris host.
2. Fill in host IP, SSH username (for example root), password or private key, and interval.
3. Save, wait one interval, and view data on Host.

## Form fields

| Field | Required | Notes |
| --- | --- | --- |
| Target Host IP | Yes | Solaris address. |
| Username | Yes | SSH username, for example `root`. |
| SSH Authentication | Yes | Password or SSH key. |
| Password / SSH Private Key | Depends | Password auth needs a password; key auth needs a private key (passphrase optional). |
| Port | No | Default 22. |
| Collection Interval | Yes | Default 60 seconds. |
| Node | Yes | Linux node that runs collection. |

The target should be able to run `mpstat`/`sar`, `vmstat`/`prtconf`/`swap`, `df`, `iostat`, `kstat`/`dlstat`/`netstat`, and `uname`. A missing command skips that metric; the rest is still reported.

After deploy, run `plugin_init` if this plugin is not yet in the console.

Script JSON and Prometheus text samples live next to the collector script in `scripts/solaris/samples/`.
