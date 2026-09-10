### Overview
Pulls inventories and core attributes of multiple resource types under an Alibaba Cloud account in parallel via Alibaba Cloud Open API (ECS, RDS, Redis, MongoDB, OSS, CLB, Kafka, etc.), formats them uniformly, and syncs them to CMDB.



### Entry Point and Execution Location
In the CMDB Web UI:
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select the **Alibaba Cloud** plugin.
3. Click "Add Task", fill in the steps, and save.

Note: the task actually runs on the "access point" you select; connectivity self-check commands should be run on the access point host.



### Prerequisites
Before starting, confirm the following items one by one (principle: get it working first, then tighten to least privilege):

1. **Alibaba Cloud console: create a RAM collection user and obtain AccessKey**
	1) Log in to the Alibaba Cloud console.
	2) Go to: `RAM Access Control` (also called "Access Control") → `Users` → `Create User`.
	3) Prefer user type "RAM User", and enable **OpenAPI access** for that user (different console versions may call it "Programmatic Access / AccessKey Access / OpenAPI Access").
	4) After creation, on the RAM user details page go to: `Authentication / AccessKey` → `Create AccessKey`.
	5) Record `AccessKeyId` and `AccessKeySecret` (the Secret is shown only once at creation) and store them securely.

2. **Alibaba Cloud console: authorize the RAM user (prefer read-only first to get it working)**
	1) Go to: `RAM Access Control` → `Permission Management` → `Grant` (or click "Add Authorization" on the user details page).
	2) For first-time verification, bind a ReadOnly system policy to speed up troubleshooting:
		- Example: bind the corresponding read-only policies for the resources you want to collect (such as ECS/RDS/Redis/OSS/SLB read-only policies).
	3) After the flow works, tighten permissions to the minimum: keep only query/list/describe permissions (Describe/List/Get).
	4) If "region refresh failed / insufficient permission" occurs, it is usually because the RAM user is not authorized, the policy scope does not include that product, or the policy has not taken effect.

3. **CMDB-side preparation (otherwise the page dropdown may be empty)**
	- An "Alibaba Cloud account" instance already exists in CMDB asset data (the page uses a "cloud account" dropdown).
	- Collection scope is clear: which account, which regions, and which resource types (ECS/RDS/OSS, etc.).

4. **Access point network (verify where the task runs)**
	- The access point can resolve and reach Alibaba Cloud API domains (DNS is healthy).
	- The access point can reach public `443/TCP` (or via company proxy/NAT egress).
	- If your environment must use a proxy, ensure the access point is configured with a proxy that allows Alibaba Cloud API access.

5. **Region (RegionId) selection**
	- This plugin first refreshes the region list with your keys, then you select a region (`RegionId`).



### Procedure
### Step 1: Network connectivity self-check
- Linux：`curl -I https://sts.aliyuncs.com`
- Windows PowerShell：`Test-NetConnection sts.aliyuncs.com -Port 443`



### Step 2: Create a collection task in CMDB
When adding a task, focus on the "credential/auth" fields:

- `AccessKey`: `AccessKeyId` of the Alibaba Cloud RAM user (account identifier).
- `AccessSecret`: `AccessKeySecret` paired with `AccessKeyId` (key/password).
- `RegionId` (usually shown as "Region"): the region to collect. Refresh the region list with the keys above first, then select one.



### Collected Data (Field Dictionary)

### ECS (aliyun_ecs)
| Key | Description |
| :----------- | :--- |
| resource_name | Instance display name |
| resource_id | Instance ID |
| ip_addr | Primary private IP |
| public_ip | Primary public IP (falls back to private if none) |
| region | Region ID |
| zone | Availability zone |
| vpc | VPC |
| status | Running status |
| instance_type | Instance type |
| os_name | OS name |
| vcpus | vCPU count |
| memory | Memory (MB) |
| charge_type | Billing type |
| create_time | Creation time |
| expired_time | Expiration time (subscription) |

### OSS Bucket (aliyun_bucket)
| Key | Description |
| :----------- | :--- |
| resource_name | Bucket name |
| resource_id | Bucket name (same) |
| location | Region |
| extranet_endpoint | Public endpoint |
| intranet_endpoint | Internal endpoint |
| storage_class | Storage class |
| cross_region_replication | Cross-region replication status |
| block_public_access | Block public access status |
| creation_date | Creation time |

### RDS MySQL / PostgreSQL (aliyun_mysql / aliyun_pgsql)
| Key | Description |
| :----------- | :--- |
| resource_name | Instance description |
| resource_id | Instance ID |
| region | Region |
| zone | Primary availability zone |
| zone_slave | Secondary/standby availability zone list |
| engine | Engine type |
| version | Engine version |
| type | Instance type (primary/secondary, etc.) |
| status | Status |
| class | Spec |
| storage_type | Storage type |
| network_type | Network type |
| connection_mode | Connection mode |
| lock_mode | Lock mode |
| cpu | CPU cores |
| memory_mb | Memory MB |
| charge_type | Billing type |
| create_time | Creation time |
| expire_time | Expiration time |

### Redis (aliyun_redis)
| Key | Description |
| :----------- | :--- |
| resource_name | Instance name |
| resource_id | Instance ID |
| region | Region |
| zone | Availability zone |
| engine_version | Engine version |
| architecture_type | Architecture (standalone/cluster) |
| capacity | Capacity |
| network_type | Network type |
| connection_domain | Connection domain |
| port | Port |
| bandwidth | Bandwidth |
| shard_count | Shard count |
| qps | QPS metric |
| instance_class | Spec |
| package_type | Package type |
| charge_type | Billing type |
| create_time | Creation time |
| end_time | Expiration time |

### MongoDB (aliyun_mongodb)
| Key | Description |
| :----------- | :--- |
| resource_name | Instance description |
| resource_id | Instance ID |
| region | Region |
| zone | Primary availability zone |
| zone_slave | Standby/hidden zone |
| engine | Engine |
| version | Version |
| type | Type (replica set/sharding, etc.) |
| status | Status |
| class | Spec |
| storage_type | Storage type |
| storage_gb | Storage capacity GB |
| lock_mode | Lock mode |
| charge_type | Billing type |
| create_time | Creation time |
| expire_time | Expiration time |

### Load balancer CLB (aliyun_clb)
| Key | Description |
| :----------- | :--- |
| resource_name | Instance name |
| resource_id | Instance ID |
| region | Region |
| zone | Primary availability zone |
| zone_slave | Standby availability zone |
| vpc | VPC |
| ip_addr | Load balancer address |
| status | Status |
| class | Spec |
| charge_type | Billing type |
| create_time | Creation time |

### Kafka instance (aliyun_kafka_inst)
| Key | Description |
| :----------- | :--- |
| resource_name | Instance name |
| resource_id | Instance ID |
| region | Region |
| zone | Availability zone |
| vpc | VPC |
| status | Status |
| class | Instance spec |
| storage_gb | Disk capacity GB |
| storage_type | Disk type |
| msg_retain | Message retention duration |
| topoc_num | Topic limit |
| io_max_read | Max read throughput |
| io_max_write | Max write throughput |
| charge_type | Billing type |
| create_time | Creation time |
