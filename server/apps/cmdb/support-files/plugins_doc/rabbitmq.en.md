### Overview
Collects RabbitMQ basic configuration inventory (version, protocol ports, node name, log/config paths, enabled-plugin file, and Erlang version) and syncs it to CMDB in a standardized form. This plugin is a **JOB (SSH script)** type: it logs in, runs `rabbitmqctl status`, parses the output, then exits. It does not modify any configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Compatible with official RabbitMQ 3.6.x to 4.0.x (including 3.8.x, 3.9.x, 3.10.x, 3.12.x, 4.0.x, etc.).

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions**
   - Can run `rabbitmqctl status` (usually as the RabbitMQ runtime user or root, and `~/.erlang.cookie` must be readable).
   - **Erlang Cookie permission**: running `rabbitmqctl status` requires reading `~/.erlang.cookie` (usually readable only by the RabbitMQ runtime user). RabbitMQ is generally started as the `rabbitmq` user; fill that user in the collection credential, or use root; otherwise data may not be obtained.
   - Can read `/proc/<pid>/environ` and `/proc/<pid>/cmdline`.
3. **Target dependencies**
   - `rabbitmqctl` is executable on the target, and RabbitMQ is started.

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **RabbitMQ** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP.
- **Credential**: prepare an SSH credential for targets "without Agent". Note that the account must meet the permission requirements for running `rabbitmqctl status` (see Prerequisites).
- Set timeout (default 60s) and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding instance under the RabbitMQ model in CMDB.

### Credential Fields
- `username`: SSH login username (required only for SSH targets). Prefer an account that can run `rabbitmqctl status`.
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

### Collected Data
**RabbitMQ (rabbitmq)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name |
| ip_addr | Host IP |
| port | Primary listen port |
| allport | Summary of protocol ports |
| node_name | Node name (cluster identifier) |
| log_path | Log file path |
| conf_path | Configuration file path |
| version | RabbitMQ version |
| enabled_plugin_file | Enabled-plugin file path |
| erlang_version | Erlang runtime version |

> Note: all fields depend on `rabbitmqctl status` output and process environment/startup-parameter parsing, and may be empty when they cannot be parsed.
