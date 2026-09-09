### Overview
Collects Tomcat basic configuration inventory (version, listen port, CATALINA path, JVM heap/non-heap parameters, log path, and Java version) and syncs it to CMDB in a standardized form. This plugin is a **JOB (SSH script)** type: it logs in, parses `server.xml` and JVM startup parameters, then exits. It does not modify any configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Compatible with official Tomcat 7.x - 11.x (including 8.5.x, 9.0.x, 10.1.x, 11.0.x, etc.).

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions**
   - Can run `ps` to view Tomcat processes.
   - Can read `$CATALINA_HOME/conf/server.xml`.
   - Can run `catalina.sh version` and `java -version`.
3. **Target dependencies**
   - Java is installed on the target and `CATALINA_HOME` is accessible.
   - Tomcat is running.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Tomcat** plugin and click "Add Task".

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
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the Tomcat model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**Tomcat (tomcat)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name |
| ip_addr | Host IP |
| port | Listen port (`Connector`) |
| catalina_path | CATALINA path |
| version | Tomcat version |
| xms | JVM initial heap size |
| xmx | JVM max heap size |
| max_perm_size | Max non-heap / metaspace size |
| permsize | Initial non-heap / metaspace size |
| log_path | Main log file path |
| java_version | Java version |

> Note: `xms`, `xmx`, `max_perm_size`, and `permsize` have values only when they are explicitly set in JVM startup parameters. `version` and `log_path` may be empty when they cannot be parsed or the corresponding file does not exist.
