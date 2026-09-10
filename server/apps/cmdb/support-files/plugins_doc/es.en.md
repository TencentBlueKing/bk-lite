### Overview
[BETA] Discovers Elasticsearch instances on the target host via a script (JOB), reads `elasticsearch.yml` and process information, collects version, port, and key configuration, and syncs them to CMDB in a standardized form. Collection is read-only and does not modify any target configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Compatible with common mainstream Elasticsearch versions; use the actually deployed version as the reference.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Target dependencies**
   - An Elasticsearch process is running on the host, and Java is correctly installed. Confirm on the target with `java -version`. The script depends on Java to parse ES jar packages for the version; without Java, the `version` field may be empty (other fields are unaffected).
3. **Collection permissions**
   - Can read the `elasticsearch.yml` configuration file and process information.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Elasticsearch** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP.
- **Credential**: prepare an SSH credential for targets "without Agent".
- Set timeout and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the Elasticsearch model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**Elasticsearch (es)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name (`{ip}-es-{port}`) |
| ip_addr | Host private IP |
| port | HTTP port (`http.port`, default `9200`) |
| version | ES version (parsed from `lib/elasticsearch-*.jar`) |
| install_path | Install path |
| conf_path | Configuration file path |
| java_path | Java executable path |
| java_version | Java version |
| cluster_name | Cluster name |
| node_name | Node name |
| is_master | Whether this is a master node |
| data_path | Data directory |
| log_path | Log directory |

> Note: configuration fields may be empty when the corresponding items are not configured in the target `elasticsearch.yml`. `version` depends on parsing the `lib/elasticsearch-*.jar` filename and may be empty if the install directory layout does not match.
