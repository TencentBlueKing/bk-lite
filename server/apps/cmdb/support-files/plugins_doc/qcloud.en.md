### Overview
This plugin collects the asset inventory under a Tencent Cloud account via Tencent Cloud Open API (SDK), including CVM, CDB (MySQL), COS, Redis, MongoDB, Pulsar, RocketMQ, CLB, EIP, CFS, domains, and other resource types. After unified formatting, it syncs them to CMDB. Collection is read-only and agentless: the "access point" you select calls Tencent Cloud APIs outbound.

### Entry Point and Execution Location
In the CMDB Web UI:
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Tencent Cloud** plugin.
3. Click "Add Task", fill in the steps, and save.

Note: the task actually runs on the "access point" you select; connectivity self-check commands should be run on the access point host.

### Prerequisites / Permissions
1. **Access point network**: the access point can reach `*.tencentcloudapi.com` outbound (public `443/TCP`, or via proxy/NAT egress).
2. **Create a read-only CAM sub-account**: create a dedicated CAM sub-account for collection, enable programmatic access / API keys, and obtain `SecretId` / `SecretKey`.
3. **Read-only authorization**: grant **read-only** permission to that sub-account. You can first bind a system read-only policy (such as the `QcloudXXXReadOnlyAccess` series, or each product's read-only policy) to get a working path, then tighten to only `Describe*`/`List*` read-only APIs.

### Procedure
#### Step 1: Network connectivity self-check (run on the access point)
- Linux：`curl -I https://cvm.tencentcloudapi.com`
- Windows PowerShell：`Test-NetConnection cvm.tencentcloudapi.com -Port 443`

Pass criterion: an HTTPS connection can be established.

#### Step 2: Create a read-only CAM account and obtain SecretId/SecretKey
Following "Prerequisites / Permissions" above, create a dedicated CAM sub-account, grant read-only permission, and record `SecretId` and `SecretKey` (SecretKey is usually shown in full only once at creation).

#### Step 3: Fill in the task (page operation)
When adding a task, fill in credentials and parameters (see "Credential Fields" below), set the collection interval, and save.

#### Step 4: Verify results
- After saving and running, check the `Added / Updated / Deleted` summary in the task details. In CMDB you should be able to query the corresponding resource instances.
- If a resource type is empty or reports insufficient permission, the sub-account usually lacks the corresponding product read-only permission, the region has no resources, or the access point cannot go outbound. Recollect after checking.

### Credential Fields
- `secret_id`: Tencent Cloud SecretId (account identifier). Encrypted at rest. Prefer a dedicated read-only sub-account; do not reuse the primary account.
- `secret_key`: Tencent Cloud SecretKey (key/password). Encrypted at rest.
- `timeout`: API request timeout.
- `ssl`: Whether to enable SSL. Advanced option; usually no change needed, enabled by default.
- `host`: Custom Endpoint. Advanced option; usually no change needed. Leave empty to use the default Endpoint; fill in only for a self-built gateway or restricted network.

### Collected Data (Field Dictionary)
Each resource type is associated to `qcloud` via a `belong` relationship. Core fields (summary):

| Resource type | model_id | Core fields (summary) |
| :--- | :--- | :--- |
| CVM | qcloud_cvm | resource_name, resource_id, region, zone, status, spec (CPU/memory/storage, depending on resource type), etc. |
| MySQL (CDB) | qcloud_mysql | resource_name, resource_id, region, zone, status, spec (CPU/memory/storage, depending on resource type), etc. |
| Redis | qcloud_redis | resource_name, resource_id, region, zone, status, spec (CPU/memory/storage, depending on resource type), etc. |
| MongoDB | qcloud_mongodb | resource_name, resource_id, region, zone, status, spec (CPU/memory/storage, depending on resource type), etc. |
| PostgreSQL | qcloud_pgsql | resource_name, resource_id, region, zone, status, spec (CPU/memory/storage, depending on resource type), etc. |
| RocketMQ cluster | qcloud_rocketmq | resource_name, resource_id, region, zone, status, etc. |
| Pulsar cluster | qcloud_pulsar_cluster | resource_name, resource_id, region, status, spec (CPU/memory/storage, depending on resource type), etc. |
| CMQ queue | qcloud_cmq | resource_name, resource_id, region, status, etc. |
| CMQ Topic | qcloud_cmq_topic | resource_name, resource_id, region, status, etc. |
| Load balancer CLB | qcloud_clb | resource_name, resource_id, region, status, spec (CPU/memory/storage, depending on resource type), etc. |
| EIP | qcloud_eip | resource_name, resource_id, region, status, ip_addr, etc. |
| COS bucket | qcloud_bucket | resource_name, resource_id, region, etc. |
| File system CFS | qcloud_filesystem | resource_name, resource_id, region, zone, status, spec (CPU/memory/storage, depending on resource type), etc. |
| Domain | qcloud_domain | resource_name, resource_id, status, expiration time, etc. |

**Relationships**
- All of the above resources belong to the corresponding Tencent Cloud account instance via `belong qcloud`.
