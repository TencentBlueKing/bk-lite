# FreeBSD Host Remote Collection

This is remote FreeBSD OS monitoring on the Host object. A Linux collect node SSHes to FreeBSD on each interval and runs system commands. The target does not need a collector installed. There is no version picker; version is read from `uname` / `freebsd-version`.

What is collected: CPU, load, memory and swap, disk capacity and inodes, disk read/write and busy, NICs, uptime, and OS version. Hardware inventory, lastlog, lsof, and connection tables are not collected.

## How to use

1. Pick a Linux collect node that can reach the FreeBSD host.
2. Fill in host IP, SSH username (for example root), password or private key, and interval.
3. Save, wait one interval, and view data on Host.

## Form fields

| Field | Required | Notes |
| --- | --- | --- |
| Target Host IP | Yes | FreeBSD address. |
| Username | Yes | SSH username, for example `root`. |
| SSH Authentication | Yes | Password or SSH key. |
| Password / SSH Private Key | Depends | Password auth needs a password; key auth needs a private key (passphrase optional). |
| Port | No | Default 22. |
| Collection Interval | Yes | Default 60 seconds. |
| Node | Yes | Linux node that runs collection. |

The target should be able to run `sysctl`, `vmstat`, `swapinfo`, `df`, `iostat`, `netstat`, and `uname`. A missing command skips that metric; the rest is still reported.

## Commands and fallbacks

| Metric | Primary | Fallback |
| --- | --- | --- |
| CPU | Two `sysctl kern.cp_time` samples | Last line of `vmstat 1 2` (us/sy). No Linux-style iowait; `cpu_usage_iowait_total` is 0. |
| Load | `sysctl vm.loadavg` | `uptime` load averages. |
| Uptime | `sysctl kern.boottime` minus `date +%s` | None. |
| Memory | `sysctl hw.physmem` and `vm.stats.vm.v_*_count` (active+wired+laundry) | `v_page_count * pagesize` for total. |
| Swap | `swapinfo -k` | Total and free are 0 when no swap devices exist. |
| Disk | `df -kT` (or `df -kP`) and `df -i` | Skip pseudo filesystems such as devfs/procfs/fdescfs. |
| Disk IO | Last sample of `iostat -x -w 1 -c 2` (kr/s, kw/s, %b) | `iostat -Ix` for since-boot totals; omit totals if `-I` is missing. |
| Network | `netstat -ibn` `<Link>` rows | `netstat -ib`. |
| OS version | `freebsd-version` | `uname -r`; architecture from `uname -p` / `uname -m`. |

Script JSON and Prometheus text samples live next to the collector script in `scripts/freebsd/samples/`.

After deploy, run `plugin_init` if this plugin is not yet in the console.
