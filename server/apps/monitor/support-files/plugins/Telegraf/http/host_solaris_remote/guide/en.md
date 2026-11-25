# Solaris Host Remote Collection

This is remote Solaris OS monitoring on the Host object. A Linux collect node SSHes to Solaris on each interval and runs system commands. x86 and SPARC share this plugin; architecture is read from `uname -p`. The target does not need a collector installed. There is no version picker.

What is collected: CPU, load, memory and swap, disk capacity and inodes, disk read/write and busy, NICs, uptime, and OS version. Hardware inventory, lastlog, lsof, and connection tables are not collected.

## Supported versions

x86 and SPARC share this plugin. There is no version or architecture picker.

| Release | Architecture | Notes |
| --- | --- | --- |
| Solaris 10 | x86, SPARC | Supported. The bundled SSH uses older connection algorithms, and collection accepts them. |
| Solaris 11.0 through 11.3 | x86, SPARC | Supported. Host keys are usually older RSA, and collection accepts them. |
| Solaris 11.4 and later | x86, SPARC | Supported. Current SSH algorithms work, and older algorithms remain accepted. |

## Older SSH algorithms

A current Linux collect node does not offer the older SSH algorithms still used by Solaris 10 and some Solaris 11 hosts, so a direct connection fails. Solaris collection accepts those older algorithms for both password and key login. The target does not need an SSH upgrade, and the collect node does not need a system SSH configuration change.

If the connection still fails and the error says the two sides have no matching key exchange, host key, cipher, or message authentication algorithm, the target SSH service is not compatible with the collect node. Confirm the target is running the SSH service bundled with Solaris.

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
