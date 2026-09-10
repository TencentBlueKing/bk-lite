### Overview
Parses a running ActiveMQ process and configuration file via a script (JOB), automatically collects core instance parameters (version, listen port, install/config paths, JVM heap parameters, etc.), and syncs them to CMDB in a standardized form. Collection is read-only and does not modify any target configuration.

> **[BETA / Untested]** This plugin has not been fully verified in real environments. Field parsing may differ from your actual deployment. Try a small-scope collection and verify results before production use.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Applies to ActiveMQ instances identifiable by script. Directory layout and configuration syntax may differ across major versions; use actual trial-collection results as the reference.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions (required only for SSH remote)**
   - Must be able to read the ActiveMQ `activemq.xml` configuration file.
   - Must be able to read `/proc/<pid>/cmdline` of the target process (collecting processes of other users usually requires root or equivalent).
3. **Target dependencies**
   - ActiveMQ is deployed and started, and the process runs with `-Dactivemq` parameters.
   - Java runtime is installed on the target.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **ActiveMQ** plugin and click "Add Task".

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
| port | Listen port (`activemq.xml` transportConnector, default `61616`) |
| install_path | Install path |
| conf_path | Configuration file path |
| java_path | Java executable path |
| java_version | JDK version |
| version | ActiveMQ version |
| xms | JVM initial heap size |
| xmx | JVM max heap size |

> Note: corresponding fields may be empty when the target process is not started with `-Dactivemq`, the `activemq.xml` path is non-standard, or `/proc/<pid>/cmdline` cannot be read. This plugin is **BETA / Untested**; verify results before putting it into use.
