### Overview
Collects Nginx basic configuration inventory (listen port, version, binary/config/log paths, server_name, include, system OpenSSL version, etc.) and syncs it to CMDB in a standardized form. This plugin is a **JOB (SSH script)** type: it logs in, reads process and configuration, then exits. It does not modify any configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Supports official Nginx 1.10+ (including 1.28.x, 1.29.x, 1.26.x, 1.24.x, etc.).

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions**
   - Can read the Nginx main configuration file (`nginx.conf`).
   - Can run `ps` to view Nginx processes and `readlink` to resolve the executable path.
   - Can run `nginx -v` to get the version.
3. **Target dependencies**
   - Nginx is started on the target (the script depends on a running process to locate the executable path and configuration).

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Nginx** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP.
- **Credential**: prepare an SSH credential for targets "without Agent".
- Set timeout (default 60s) and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the Nginx model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**Nginx (nginx)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name (`{ip}-nginx-{port}`) |
| ip_addr | Host IP |
| port | Listen port |
| version | Nginx version (`nginx -v`) |
| bin_path | Executable path |
| conf_path | Main configuration file path |
| log_path | Error log path (`error_log` directive) |
| server_name | server_name configuration |
| include | Configuration included via include |
| ssl_version | System OpenSSL version |

> Note: when the target does not configure the corresponding directive (such as `error_log`, `server_name`, `include`) or the script lacks permission, related fields may be empty.
