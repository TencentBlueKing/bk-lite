### Overview

The PC Discovery plugin collects basic configuration, operating system information, and system-level installed software of Windows / macOS personal computers, and syncs them to CMDB:

- PC basic information is written to the `pc` model;
- Installed software is written to the `pc_software` model;
- Software is associated to the corresponding PC via the `install_on` relationship.

Collection is **read-only**. It does not install, uninstall, or start software, and does not modify the registry, files, or system configuration.

> Current product boundary: the same PC should be configured in only one PC collection task. Avoid overlapping IP ranges across multiple tasks.

---

### Execution Mode

This plugin is a **JOB (script)** type. The task actually runs on the selected access point:

| PC OS | Connection method | Default port | Collection script |
| :--- | :--- | :--- | :--- |
| Windows | WinRM | `5986/HTTPS` | PowerShell |
| macOS | SSH | `22` | Shell + built-in system commands |

One task can collect only one OS. After the task is created, it cannot switch between Windows and macOS. To collect both systems, create two tasks.

### What "Sync Latest Results" means

**Sync Latest Results** in the task list queries the latest PC snapshot already reported to the platform by the collector and syncs it to CMDB. It **does not immediately start a new round of WinRM / SSH remote collection**.

Recommended order:

1. Save the task and wait for the collector to finish remote collection and reporting according to the configuration;
2. Confirm there is new data in the list's "Data Report Time";
3. Click "Sync Latest Results", or wait for the task to sync automatically by interval;
4. If it prompts "No latest PC report found", first check remote connectivity, credentials, collection interval, and data report time.

---

### Prerequisites

#### Common requirements

1. The access point node is online and can reach the target PC.
2. The target IP range contains only the OS selected for the current task.
3. The target firewall allows the corresponding WinRM or SSH port.
4. At least one of the PC's hardware UUID or chassis serial number must be valid; otherwise a stable asset identity cannot be generated. The UUID
   must be the standard `8-4-4-4-12` hexadecimal format. If the format is invalid or it is an all-zero or all-`F` placeholder,
   the system automatically falls back to the chassis serial number.

#### Windows

1. WinRM is enabled on the target.
2. Prefer `5986/HTTPS`; use `5985/HTTP` only on a trusted network.
3. The account must have remote WinRM login, CIM/WMI read, and HKLM Uninstall registry read permissions.
4. PowerShell 5.1 or later is recommended.

Access point connectivity self-check:

```bash
nc -vz <pc_ip> 5986
```

Windows PowerShell self-check:

```powershell
Test-NetConnection <pc_ip> -Port 5986
```

#### macOS

1. Enable "Remote Login" in "System Settings → General → Sharing".
2. The SSH account must be allowed to log in remotely.
3. A normal account can usually read the hardware, system, and `/Applications` app information this plugin needs; sudo is not required.

Access point connectivity self-check:

```bash
nc -vz <pc_ip> 22
```

For local macOS development self-check, you can run the read-only verification entry in the repository without writing to CMDB first:

```bash
cd agents/stargazer
.venv/bin/python scripts/test_pc_macos_local.py
```

This command runs the identity script and the full discovery script in sequence, validating JSON protocol, device identity, software count,
snapshot association, memory and disk fields, and outputs only a redacted summary. If an app's `Info.plist` is unreadable, the
result is `partial`; this is a safety behavior to prevent mistaken software deletion, not a failure of the whole PC collection.

---

### Create a Task

#### Step 1: Entry Point

1. Go to "CMDB → Management → Auto Discovery".
2. Select "Host Logical Host → PC Discovery".
3. Click "Add Task".

#### Step 2: Select OS and target

- **Operating system**: choose Windows or macOS;
- **IP range**: enter target IP, CIDR, or IP range;
- **Access point**: choose a node that can reach the target PC;
- **Timeout**: recommend `120` seconds per PC; adjust by network conditions;
- **Collection interval**: set according to how often assets change.

#### Step 3: Fill in credentials

Multiple credential sets can be configured. The system tries them in order and prefers to reuse a successful hit.

**Windows WinRM**

| Field | Description |
| :--- | :--- |
| username | Windows local account, domain account, or UPN, for example `DOMAIN\user` |
| password | Login password, encrypted at rest, injected via environment variable when dispatched |
| port | HTTPS default `5986`; HTTP default `5985` |
| scheme | Recommend `https` |
| transport | Currently uses `ntlm` |
| certValidation | Whether to verify the HTTPS certificate; enable in production |

> HTTP transmits authentication in plaintext and should only be used on an isolated, trusted network. Disabling certificate verification may expose you to man-in-the-middle attacks.

**macOS SSH**

| Field | Description |
| :--- | :--- |
| username | macOS user allowed to log in remotely |
| port | SSH port, default `22` |
| authType | Password or PEM private key, choose one |
| password | Fill in for password authentication |
| private_key | Fill in PEM private key for key authentication |
| passphrase | Fill in if the private key is passphrase-protected |

Credential secrets are not written to VictoriaMetrics labels or node-parameter headers.

#### Step 4: Test connection

Click "Test Connection" before saving:

- The test only reads PC identity information;
- It does not scan installed software;
- It does not write to CMDB;
- Save the task after it succeeds.

---

### PC Collected Data

| Key | Description |
| :--- | :--- |
| inst_name | Stable instance name, generated from hardware UUID first, falling back to serial number when invalid |
| host_name | PC hostname |
| ip_addr | Target IP actually connected in this task |
| os_type | `windows` or `macos` |
| os_name | OS name |
| os_version | OS version |
| os_build | OS build |
| architecture | System architecture |
| hardware_uuid | Normalized hardware UUID (standard `8-4-4-4-12` hexadecimal format) |
| serial_number | BIOS / chassis serial number |
| brand | Device vendor |
| device_model | Device model |
| cpu | CPU model |
| men | Total physical memory (bytes) |
| disk | Total local disk capacity (bytes) |
| logged_in_user | Currently logged-in user |
| last_collect_time | Data report time of the latest snapshot |

Manually maintained fields such as `asset_code`, user, and location are not in the collection whitelist and will not be overwritten by PC Discovery.

---

### Installed Software Collected Data

| Key | Description |
| :--- | :--- |
| inst_name | Stable software instance name |
| name | Software name |
| version | Software version |
| publisher | Publisher; may be empty on macOS |
| software_key | Stable software identifier |
| product_id | Windows product/registry key or macOS Bundle ID |
| install_location | Install path |
| install_date | Install date; empty when the source does not provide it |
| architecture | Software architecture |
| source | `windows_registry` or `macos_application` |
| last_collect_time | Data report time of the latest snapshot |

Windows reads HKLM 64-bit and 32-bit Uninstall views, and excludes system components, KB patches, language packs, and drivers.

macOS only scans:

- `/Applications`
- `/Applications/Utilities`

It does not scan user directories, `/System/Applications`, or install receipts.

---

### Software Cleanup Rules

Software deletion is protected by a complete-snapshot safety gate:

1. Snapshot status must be `complete`;
2. Software error count must be `0`;
3. Actual software count must match the snapshot-declared count;
4. Software entities and `install_on` associations must all write successfully.

Only when the above conditions are met will the system process software that is no longer in the latest snapshot, according to the selected cleanup policy.

| Cleanup policy | Behavior |
| :--- | :--- |
| No cleanup | Add and update only; do not automatically delete software |
| Immediate cleanup | Diff-delete only associated software of the current PC |
| Expired cleanup | Clean up expired software under this task after the configured number of days |

Partial snapshots do not delete software. Deleting a task only deletes scheduling and node configuration; it does not cascade-delete PC or software assets already written to CMDB.

---

### Task Status

| Status | Description |
| :--- | :--- |
| Success | All PC snapshots are complete and CMDB writes succeeded |
| Partial success | There are partial snapshots, or some PC / software writes failed |
| Failed | All targets failed, or no latest PC snapshot was found |

A complete "zero software" snapshot is a valid result: it means the PC currently has no recognizable system-level installed software.

---

### FAQ

#### Connection test failed

- `TARGET_UNREACHABLE`: check routing and firewall from the access point to the target IP/port;
- `WINRM_AUTH_FAILED`: check Windows username, password, and remote login permission;
- `WINRM_TLS_FAILED`: check HTTPS certificate, hostname, and certificate-validation settings;
- `SSH_AUTH_FAILED`: check macOS user, password, or the list of users allowed to log in remotely;
- `SSH_KEY_INVALID`: check PEM private-key content and passphrase;
- `SCRIPT_TIMEOUT`: check network latency and increase per-host timeout;
- `PC_IDENTITY_INVALID`: both hardware UUID and serial number are invalid; fix device firmware identity first;
- `SCRIPT_OUTPUT_INVALID`: target script output is abnormal; check that system commands are available and review Stargazer logs.

#### No new assets after clicking "Sync Latest Results"

1. Check whether "Data Report Time" was updated;
2. Confirm the collection interval has been reached;
3. Check that the access point and Stargazer are online;
4. Check that the task IP range, OS, and credentials match;
5. Run "Test Connection" first to rule out connectivity and authentication issues.

#### Software was not deleted

This is expected safety behavior. When the snapshot is partial, software counts do not match, or association writes fail, the system keeps old software rather than running a diff cleanup that might delete data by mistake.
