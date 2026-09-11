### Overview
Collects the inventory of **running containers** on the target host (container ID, image, created time, start command, port mappings, mounted volumes, network, and status) and syncs them to CMDB in a standardized form. This plugin is a **JOB (SSH script)** type: it logs in, runs `docker ps`/`docker inspect`, then exits. It does not modify any container or configuration.

### Execution Mode
This plugin is a **JOB (script)** type. The execution method is selected automatically based on the target IP:

| Target | Execution method | SSH credential required |
| :--- | :--- | :--- |
| Target host **has Agent installed** (in the Node Management node list) | **Local execution**: The Agent runs the collection script directly on that host | No |
| Target host **does not have Agent installed** (not in the node list) | **SSH remote fallback**: The access point node SSHs into the target and runs the script | Yes |

> In short: hosts with Agent can be collected with zero credentials; hosts without Agent depend on the SSH account you provide for remote collection.

### Version Compatibility
- Supports mainstream Docker versions.

### Prerequisites
1. **Network and connectivity**
   - SSH target: the SSH port from the access point to the target is reachable (default `22`, customizable).
   - Local-execution target: the host's Agent/Executor is online in Node Management.
2. **Collection account and permissions (important)**
   - Can run `docker ps` / `docker inspect`.
   - The collection account **must belong to the `docker` group or be root**, and must be able to access `/var/run/docker.sock`; otherwise the `docker` command cannot read container information due to insufficient permissions.
3. **Target dependencies**
   - Docker daemon is running.
   - At least one container is running (this plugin only collects running containers).

### Procedure
#### Step 0: Entry Point
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Docker** plugin and click "Add Task".

> The task actually runs on the "access point" you select; the self-check commands below should be run on the access point host.

#### Step 1: Network connectivity self-check (run on the access point, SSH targets only)
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

Pass criterion: the port is reachable.

#### Step 2: Fill in the task
- **Collection target**: enter the target IP.
- **Credential**: prepare an SSH credential for targets "without Agent". Note that the account must belong to the `docker` group or be root (see Prerequisites).
- Set timeout (default 60s) and collection interval, then save and run.

#### Step 3: Verify results
- In the task details, check the `Added / Updated / Deleted` summary and raw data. You should be able to query the corresponding container instances under the Docker model in CMDB.
- If the result is empty, the collection account usually lacks Docker access, or there is no running container on the target. Recollect after granting permissions / confirming containers.

### Credential Fields
- `username`: SSH login username (required only for SSH targets). Prefer an account that belongs to the `docker` group or has root privileges.
- `password`: Password for the account above. Encrypted at rest and injected as an environment variable when dispatched; not written to plaintext config files.
- `port`: SSH port, default `22`.

> If collection fails with a permission error: ① confirm the account has been added to the docker group with `usermod -aG docker <user>` (re-login required), and verify with `groups <user>`; ② confirm `/var/run/docker.sock` exists and the account can access it; ③ or switch to root.

### Collected Data
**Docker (docker)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name |
| container_id | Container ID |
| ip_addr | Host IP |
| port | Port |
| image | Image |
| created | Created time |
| command | Start command |
| ports | Port mappings (JSON) |
| mounts | Mounted volumes (JSON) |
| networks | Network |
| status | Container status |

> Note: when the container has no port mapping or volume configured, or the corresponding information cannot be parsed, fields such as `ports`, `mounts`, and `networks` may be empty.
