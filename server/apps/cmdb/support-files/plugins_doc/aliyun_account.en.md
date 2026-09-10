### Overview
This plugin collects the asset inventory under an Alibaba Cloud account via Alibaba Cloud Open API (SDK), including ECS, RDS, OSS, Redis, MongoDB, Kafka, CLB, and other resource types. After unified formatting, it syncs them to CMDB. Collection is read-only and agentless: the "access point" you select calls Alibaba Cloud APIs outbound.

### Entry Point and Execution Location
In the CMDB Web UI:
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Alibaba Cloud** plugin.
3. Click "Add Task", fill in the steps, and save.

Note: the task actually runs on the "access point" you select; connectivity self-check commands should be run on the access point host.

### Prerequisites / Permissions
1. **Access point network**: the access point can reach `*.aliyuncs.com` outbound (public `443/TCP`, or via proxy/NAT egress).
2. **Create a read-only RAM sub-account**: create a dedicated RAM sub-account for collection, enable OpenAPI access, and obtain `AccessKeyId` / `AccessKeySecret`.
3. **Read-only authorization**: grant **read-only** permission to that sub-account. You can first bind a system read-only policy to get a working path (such as `ReadOnlyAccess`, or product read-only policies `AliyunECSReadOnlyAccess`, `AliyunRDSReadOnlyAccess`, `AliyunOSSReadOnlyAccess`, etc.), then tighten to a custom least-privilege policy (only `ecs:Describe*`, `rds:Describe*`, `oss:List*`/`oss:GetBucketInfo`, and other read-only APIs). Example least-privilege read-only APIs:
   - ECS：`ecs:Describe*`
   - RDS：`rds:Describe*`
   - OSS：`oss:ListBuckets`、`oss:GetBucketInfo`
   - Redis：`r-kvstore:Describe*`
   - MongoDB：`dds:Describe*`
   - Kafka：`alikafka:Get*`
   - SLB/CLB：`slb:Describe*`

### Procedure
#### Step 1: Network connectivity self-check (run on the access point)
- Linux：`curl -I https://ecs.aliyuncs.com`
- Windows PowerShell：`Test-NetConnection ecs.aliyuncs.com -Port 443`

Pass criterion: an HTTPS connection can be established.

#### Step 2: Create a read-only RAM account and obtain AK/SK
Following "Prerequisites / Permissions" above, create a dedicated RAM sub-account, grant read-only permission, and record `AccessKeyId` and `AccessKeySecret` (the Secret is shown only once at creation).

#### Step 3: Fill in the task (page operation)
When adding a task, fill in credentials and parameters (see "Credential Fields" below), set the collection interval, and save.

#### Step 4: Verify results
- After saving and running, check the `Added / Updated / Deleted` summary in the task details. In CMDB you should be able to query the corresponding resource instances.
- If a resource type is empty or reports insufficient permission, the sub-account usually lacks the corresponding product read-only permission, the selected region has no resources, or the access point cannot go outbound. Recollect after checking.
- If the "Alibaba Cloud account" dropdown is empty, first add an "Alibaba Cloud account" instance in CMDB assets.

### Credential Fields
- `secret_id`: AccessKey ID of the Alibaba Cloud RAM user. Encrypted at rest. Prefer a dedicated read-only sub-account; do not reuse the primary account.
- `secret_key`: AccessKey Secret paired with the AccessKey ID. Encrypted at rest.
- `region_id`: Collection region, default `cn-hangzhou`.
- `timeout`: API request timeout.
- `host`: Optional. Fill in a custom Endpoint for dedicated-cloud scenarios; leave empty for public cloud.

### Collected Data (Field Dictionary)
Each resource type is associated to `aliyun_account` via a `belong` relationship. Core fields (summary):

| Resource type | model_id | Core fields (summary) |
| :--- | :--- | :--- |
| ECS | aliyun_ecs | resource_name, resource_id, region, zone, status, spec, etc. |
| OSS bucket | aliyun_bucket | resource_name, resource_id, region, storage_class, etc. |
| RDS MySQL | aliyun_mysql | resource_name, resource_id, region, zone, status, spec, etc. |
| RDS PostgreSQL | aliyun_pgsql | resource_name, resource_id, region, zone, status, spec, etc. |
| Redis | aliyun_redis | resource_name, resource_id, region, zone, status, spec, etc. |
| MongoDB | aliyun_mongodb | resource_name, resource_id, region, zone, status, spec, etc. |
| Kafka instance | aliyun_kafka_inst | resource_name, resource_id, region, zone, status, spec, etc. |
| Load balancer CLB | aliyun_clb | resource_name, resource_id, region, zone, status, spec, etc. |

**Relationships**
- All of the above resources belong to the corresponding Alibaba Cloud account instance via `belong aliyun_account`.
