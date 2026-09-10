### Overview
Collects WebLogic instance version, listen port, install/domain directories, Server name, and Admin Server information via a script (JOB), and syncs them to CMDB in a standardized form. Collection is read-only and does not modify any target configuration.

> **[BETA / Untested]** This plugin has not been fully verified in real environments. Field parsing may differ from your actual deployment. Try a small-scope collection and verify results before production use.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Applies to WebLogic instances identifiable by script. Directory layout and configuration syntax may differ across major versions; use actual trial-collection results as the reference.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions (required only for SSH remote)**
   - Must be able to read `config/config.xml` under the domain.
3. **Target dependencies**
   - WebLogic is deployed and started.
   - Java runtime is installed on the target.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **WebLogic** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP range (supports CIDR, comma-separated, and ranges).
- **Credential**: prepare SSH credentials for targets "without Agent" (multiple sets can be configured; they are tried in order and hits are recorded).
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
| inst_name | Instance display name |
| ip_addr | Host private IP |
| port | Listen port (`config.xml` listen-port, default `7001`) |
| wlst_path | WLST tool path |
| weblogic_home | WebLogic install directory |
| domain_path | Domain directory path |
| name | Server name |
| domain_version | Domain version |
| admin_server_name | Admin Server name |
| java_version | JDK version |

> Note: related fields may be empty when the domain `config/config.xml` path is non-standard or cannot be read. This plugin is **BETA / Untested**; verify results before putting it into use.
