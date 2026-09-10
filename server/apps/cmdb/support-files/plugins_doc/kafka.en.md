### Overview
Collects Kafka basic configuration inventory (version, listen port, install/config/log paths, Java and JVM heap parameters, and core broker parameters) and syncs it to CMDB in a standardized form. This plugin is a **JOB (SSH script)** type: it logs in, parses the process and `server.properties`, then exits. It does not modify any configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Compatible with official Kafka 2.8.x - 4.0.x (including 2.8.x, 3.3.x, 3.5.x, 4.0.x, etc.).
- In Kafka 3.3.x-4.0.x KRaft mode (KRaft is the ZooKeeper-free self-managed mode introduced in Kafka 3.3+), the node_id field is assigned to broker_id after it is obtained.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions**
   - Can run `ps` to view Kafka processes.
   - Can read the configuration file `server.properties`.
   - Can access `$KAFKA_HOME/libs/` (used to parse the version).
3. **Target dependencies**
   - Java is installed on the target (required to run Kafka).
   - Kafka is started.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Kafka** plugin and click "Add Task".

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
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the Kafka model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets).
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**Kafka (kafka)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name |
| ip_addr | Host IP |
| port | Listen port (`listeners`) |
| version | Kafka version |
| install_path | Install path |
| conf_path | Configuration file path |
| log_path | Log directory |
| java_path | Java executable path |
| java_version | Java version |
| xms | JVM initial heap size |
| xmx | JVM max heap size |
| broker_id | Broker unique identifier |
| io_threads | I/O thread count |
| network_threads | Network thread count |
| socket_receive_buffer_bytes | Receive buffer size |
| socket_request_max_bytes | Max request size |
| socket_send_buffer_bytes | Send buffer size |

> Note: related fields may be empty when `server.properties` is missing the corresponding items, JVM parameters are not set explicitly, or the script cannot parse them.
