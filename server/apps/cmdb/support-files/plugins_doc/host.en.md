### Overview
Collects basic host OS inventory (hostname, operating system, CPU, memory, disk, NIC MAC, running processes, and listen ports) and syncs it to CMDB in a standardized form for asset inventory and capacity assessment. Collection is **read-only** and does not modify any target configuration.

> Note: this plugin collects static "configuration/inventory" information (such as CPU model, core count, memory capacity). It does not collect performance metrics such as CPU usage or load (those belong to the "Monitoring" module).

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
#### Linux
- Compatible with openEuler 22.03/24.03 LTS series
- Compatible with Kylin V10/V11 series
- Compatible with UnionTech UOS V20/V25 series
- Compatible with RHEL/CentOS 6/7/8/9/10 series

#### Windows
- Compatible with Windows Server 2016 LTSB, 2019 LTSC, 2022 LTSC, 2025 LTSC

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions (required only for SSH remote)**
   - **Basic information** (hostname, OS, CPU, memory, disk, MAC): a normal login account is enough; root/sudo is not required. The script only reads globally readable information such as `lscpu`, `free`, `df`, `ip link`, `/etc/os-release`, and `/proc`.
   - **Processes and listen ports (`proc` field)**: to collect executable paths and port ownership for all processes, **root (or equivalent)** is required; a normal account can only see its own processes, so the process inventory will be incomplete.
3. **Target dependencies**
   - Linux: `/bin/sh` and common commands such as `lscpu`, `free`, `df`, `ip`/`ifconfig`, `ss`/`netstat`, `ps`, `awk`, `readlink` (bundled with most distributions). JSON escaping is done by `awk`; **python3 is not required**. Falls back to `redhat-release` when `/etc/os-release` is absent.
   - Windows: PowerShell 5+.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Host** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP range (supports CIDR, comma-separated, and ranges such as `10.0.0.1-10.0.0.50`).
- **Credential**: prepare SSH credentials for targets "without Agent" (multiple sets can be configured; they are tried in order and hits are recorded).
- Set timeout and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the Host model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets), such as `root` or a normal account with read permission.
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**Host (host)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name |
| ip_addr | Host IP |
| hostname | Hostname (`hostname -f`, fallback `hostname`) |
| os_type | OS type (`uname -s`) |
| os_name | OS name (`/etc/os-release` NAME) |
| os_version | OS version (`/etc/os-release` VERSION_ID) |
| os_bit | OS bit width (derived from architecture) |
| cpu_arch | CPU instruction architecture (`uname -m`) |
| cpu_model | CPU model (`lscpu`, fallback `/proc/cpuinfo`) |
| cpu_core | CPU logical core count |
| memory | Total physical memory (GB) |
| disk | Aggregated disk capacity (GB) |
| inner_mac | First NIC MAC address (`ip link`) |
| proc | Running process inventory (including listen ports), written to related model host_proc_usage |

**Process (host_proc_usage, related child of host)**

| Key | Description |
| :--- | :--- |
| pid | Process ID |
| name | Process name |
| arg | Startup command line |
| exe | Executable path (`readlink /proc/<pid>/exe`) |
| cwd | Working directory (`readlink /proc/<pid>/cwd`) |
| ports | Listen port set of this process (`ss -lntp`) |

> Note: `cpu_model` and `cpu_core` are set to `unknown` when `lscpu`/`/proc/cpuinfo` permission is insufficient; `memory` and `disk` fall back to `0.0` when the statistics command fails; `inner_mac` is set to `unknown` in environments such as containers where the first NIC cannot be resolved. `cpu_arch` comes from `uname -m`; domestic architectures such as Loongson/Sunway/RISC-V can be collected normally, but `os_bit` only recognizes `x86_64`/`aarch64`/`i386`/`i686`; other architectures are marked `unknown`. For other users' processes in `proc`, `exe`/`cwd`/`ports` require root to collect fully.
