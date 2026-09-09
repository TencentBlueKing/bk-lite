### Overview
Collects Windows IIS version, site and application binding ports, application pools, virtual directories, and physical paths via a script (PowerShell), and syncs them to CMDB in a standardized form. Collection is read-only and does not modify any target configuration.

> **[BETA / Untested]** This plugin has not been fully verified in real environments. Field parsing may differ from your actual deployment. Try a small-scope collection and verify results before production use.

### Execution Mode
This plugin is **Windows only**, a **JOB (PowerShell script)** type, executed via WinRM/Agent (WinRM is the Windows remote management protocol, similar in role to SSH on Linux):

| Target | Execution method | Credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the PowerShell collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **Remote fallback**: connect to the target via WinRM and run the PowerShell script | Yes |

> In short: Windows hosts with Agent can be collected with zero credentials; hosts without Agent depend on the account you provide for remote collection via WinRM.

### Version Compatibility
- Applies to Windows IIS instances identifiable by PowerShell. Registry keys and configuration syntax may differ across Windows/IIS versions; use actual trial-collection results as the reference.

### Prerequisites
1. **Platform**
   - Windows only.
2. **Network and connectivity**
   - Remote target: the WinRM port from the access point to the target is reachable.
   - Local-execution target: the host's Agent/Executor is online in Node Management.
3. **Collection account and permissions (required only for remote)**
   - `appcmd.exe` is available, usually at `C:\Windows\System32\inetsrv\`.
   - Can read IIS-related registry keys. The version is read from registry `HKLM\SOFTWARE\Microsoft\InetStp` (usually requires administrator privileges).
4. **Target dependencies**
   - IIS is installed and enabled on the target.
   - PowerShell 5+.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **IIS** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, remote targets only)
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 5985`

Pass criterion: the WinRM port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP range (supports CIDR, comma-separated, and ranges).
- **Credential**: prepare administrator credentials for targets "without Agent" (multiple sets can be configured; they are tried in order and hits are recorded).
- Set timeout and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the instance under the corresponding CMDB model.

### Credential Fields
- `username`: Login username (required only for remote targets); must have administrator permission to read IIS configuration and the registry.
- `password`: Password for the account above. Encrypted at rest and injected when dispatched; not written to plaintext config files.
- `port`: Connection port (WinRM, default `5985`).

### Collected Data
| Key | Description |
| :--- | :--- |
| inst_name | Instance display name |
| ip_addr | Host private IP |
| port | Site-bound HTTP port |
| version | IIS version (registry InetStp) |
| website | Site name |
| webapp | Application name |
| virdir | Virtual directory |
| apppool | Application pool |
| apppool_count | Application pool count |
| webapp_count | Application count |
| phys_path | Physical path |
| configfile | Configuration file path (`applicationHost.config`) |
| max_concur_connect | Max concurrent connections |
| server_name | Server name |

> Note: related fields may be empty when `appcmd.exe` is unavailable or the registry/configuration cannot be read. This plugin is **BETA / Untested**; verify results before putting it into use.
