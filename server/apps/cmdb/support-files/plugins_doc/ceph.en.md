### Overview
Collects Ceph node version, role, and configuration via a script (version, role, install path, configuration file, startup command line, etc.) and syncs them to CMDB in a standardized form. Collection is read-only and does not modify any target configuration.

> **[BETA / Untested]** This plugin has not been fully tested. Try it in a non-production environment first and confirm the collection results match expectations before rolling it out.

### Execution Mode
This plugin is a **JOB (SSH script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Compatible with mainstream Ceph versions; verify on the target node first.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions (required only for SSH remote)**
   - Need to be able to run the `ceph` command and have permission to read `/etc/ceph/ceph.conf`.
3. **Target dependencies**
   - A running Ceph process exists on the target host (one of ceph-mon / ceph-osd / ceph-mds / ceph-mgr).
   - Can run `ceph version` to get version information.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Ceph** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP range (supports CIDR, comma-separated, and ranges).
- **Credential**: prepare an SSH credential for targets "without Agent".
- Set timeout and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the instance under the corresponding CMDB model.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
| Key | Description |
| :--- | :--- |
| bk_inst_name | Instance display name |
| ip_addr | Host private IP |
| port | Listen port |
| version | Ceph version (`ceph version`) |
| role | Node role (ceph-mon / ceph-osd / ceph-mds / ceph-mgr) |
| install_path | Install path |
| config_file | Configuration file path (specified by `--conf`, or `/etc/ceph/ceph.conf`) |
| cmdline | Process startup command line |
| ceph_exe | ceph executable path |

> Note: `config_file` prefers the configuration file specified by the startup `--conf` option, and falls back to `/etc/ceph/ceph.conf` when not specified. `role` is identified from the actual running Ceph process type.
