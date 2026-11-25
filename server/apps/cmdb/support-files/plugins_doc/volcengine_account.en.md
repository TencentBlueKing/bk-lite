### Overview
This plugin collects the inventory of one Volcengine account in one region through the Volcengine OpenAPI. It covers ECS, EIP, classic CLB, MySQL, PostgreSQL, and TOS. Collection is read-only. The selected access point calls the APIs outbound. One task collects one region; create another task for another region.

### Entry Point and Execution Location
In the CMDB Web UI:
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Volcengine** plugin.
3. Click "Add Task", choose an existing Volcengine account, fill in the credential and region, and save.

The task runs on the selected access point. Run the connectivity check on that host.

### Prerequisites / Permissions
1. **Volcengine account**: create a Volcengine account asset in CMDB first. An empty `endpoint` uses the public OpenAPI and `tos-{region}.volces.com`. A filled endpoint replaces the host for both OpenAPI and TOS.
2. **Access point network**: the access point can reach `*.volcengineapi.com` and `*.volces.com` on `443/TCP`. When a custom address is set, reach that address instead.
3. **Read-only credential**: use a dedicated AccessKey limited to the read-only actions this plugin calls:
   - ECS: `DescribeRegions`, `DescribeInstances`
   - EIP: `DescribeEipAddresses`
   - Classic CLB: `DescribeLoadBalancers`
   - MySQL: `DescribeDBInstances`
   - PostgreSQL: `DescribeDBInstances`
   - TOS: `ListBuckets`

### Procedure
#### Step 1: Network connectivity self-check (run on the access point)
- Linux: `curl -I https://ecs.cn-beijing.volcengineapi.com`
- Windows PowerShell: `Test-NetConnection ecs.cn-beijing.volcengineapi.com -Port 443`

An HTTPS connection is enough. Replace the region with the region selected by the task.

#### Step 2: Prepare an AccessKey
Create or choose a read-only AccessKey as described above. Record the AccessKey ID and AccessKey Secret. The Secret is shown only once at creation.

#### Step 3: Fill in the task
Select the Volcengine account, the access point, and one region. Enter the AccessKey ID and AccessKey Secret, set the collection interval, and save.

#### Step 4: Verify results
- After a run, check the added, updated, and deleted summary in the task details, and look up the instances in CMDB.
- If one product is denied, throttled, or its pagination stops, that product is a failure. Products that succeeded are still updated, and this round does not delete existing assets.
- TOS keeps only buckets whose `Location` equals the task region.
- If the account dropdown is empty, create a Volcengine account asset first.

### Credential Fields
- AccessKey ID: the Volcengine access key ID. Encrypted at rest.
- AccessKey Secret: the secret paired with the AccessKey ID. Encrypted at rest. It is not written into the collector configuration body.
- Region: the RegionId collected by this task, for example `cn-beijing`. The region list comes from ECS `DescribeRegions`.
- Account `endpoint`: optional. Leave it empty for the public cloud. For a dedicated cloud or proxy, both OpenAPI and TOS use this host.

### Collected Data (Field Dictionary)
Child resources belong to `volcengine_account`. The instance name is `name(resource ID)`. Collection matches a child by `resource_id`, so a cloud rename updates the original instance.

| Resource type | model_id | Core fields (summary) |
| :--- | :--- | :--- |
| ECS | volcengine_ecs | resource_name, resource_id, region, zone, ip_addr, public_ip, status, instance_type, os_name, vcpus, memory_mb, charge_type |
| EIP | volcengine_eip | resource_name, resource_id, region, ip_addr, status, bandwidth, instance_type, instance_id |
| Classic CLB | volcengine_clb | resource_name, resource_id, region, vpc, ip_addr, public_ip, status, type, charge_type |
| MySQL | volcengine_mysql | resource_name, resource_id, region, zone, vpc, ip_addr, port, version, status, storage_gb |
| PostgreSQL | volcengine_pgsql | resource_name, resource_id, region, zone, vpc, ip_addr, port, version, status, storage_gb |
| TOS | volcengine_tos | resource_name, resource_id, region, location, extranet_endpoint, intranet_endpoint, bucket_type, creation_date |

**Relationships**
- Each child resource belongs to the Volcengine account.
- An EIP adds a `connect` edge when it is bound to an ECS or a classic CLB, matched by resource ID. Other bind types only belong to the account. Collection adds connections and does not remove existing ones.
