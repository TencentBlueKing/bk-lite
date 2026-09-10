### Overview
Collects **text configuration file content** at the OS layer of the target host, and archives it as a configuration file under the target instance (default host). Collection is **read-only** and does not modify any target file.

> Note: `config_file` is not a standalone CMDB model. Collection results are attached as a configuration file under the target instance you select, for configuration inventory and change tracing.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP, and supports Linux and Windows:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions (required only for SSH remote)**
   - The SSH account only needs **read permission** on the configuration file; root is not required.
3. **File type**
   - The file must be text (such as `text/*`, json, xml, yaml). Binary files are refused.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Config File** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Select the target and fill in the file path
- **Collection target**: select the target instance to attach results to (default host).
- **File path**: enter the absolute path of the configuration file to collect (`config_file_path`).
- Prepare an SSH credential for targets "without Agent", set the collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the execution result and status. After a successful collection, the result is archived as a configuration file under the target instance.

### Credential / Parameter Fields
- `config_file_path`: required. Absolute path of the configuration file to collect.
- `target_model_id`: target model to attach results to, default `host`.
- `username`: SSH login username (required only for SSH targets). Read permission on the target file is enough; root is not required.
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
| Key | Description |
| :--- | :--- |
| File content | Configuration file content (base64 encoded) |
| File size | File size in bytes |
| Content hash | File content hash (SHA256) |
| Version | Collection timestamp |
| Status | Collection status: `success` / `file_not_found` / `permission_denied` / `not_text` |

> Note: `config_file` is not a standalone CMDB model. Results are archived as a configuration file under the target instance. Status `file_not_found` means the path does not exist, `permission_denied` means the account has no read permission, and `not_text` means the file is not text (for example binary) and collection was refused.
