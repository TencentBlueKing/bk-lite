### 说明
基于阿里云开放 API 并行拉取账户下多类资源（ECS、RDS、Redis、MongoDB、OSS、CLB、Kafka 等）清单与核心属性，统一格式化后同步至 CMDB。



### 操作入口与执行位置
在 CMDB Web 页面：
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **阿里云**。
3. 点击“新增任务”，按步骤填写并保存。

说明：任务实际执行发生在你选择的“接入点”上；连通性自测命令应在接入点机器上执行。



### 前置要求
开始前建议逐条确认（按“先跑通、再最小权限”的原则）：

1. **阿里云控制台：创建 RAM 采集用户并获取 AccessKey**
	1) 登录阿里云控制台。
	2) 进入：`RAM 访问控制`（也叫“访问控制”）→ `用户` → `创建用户`。
	3) 用户类型建议选择“RAM 用户”，并为该用户启用 **OpenAPI 调用访问**（不同控制台版本可能叫“编程访问/AccessKey 访问/OpenAPI 访问”）。
	4) 创建完成后，在该 RAM 用户详情页进入：`认证管理/AccessKey` → `创建 AccessKey`。
	5) 记录 `AccessKeyId` 与 `AccessKeySecret`（Secret 只在创建时展示一次），妥善保存。

2. **阿里云控制台：给 RAM 用户授权（建议先只读跑通）**
	1) 进入：`RAM 访问控制` → `权限管理` → `授权`（或在用户详情页直接点“新增授权”）。
	2) 首次验证建议直接绑定阿里云系统策略中的只读策略（ReadOnly 类），用于快速排障：
		- 示例：按你要采集的资源绑定相应只读策略（如 ECS/RDS/Redis/OSS/SLB 等的只读策略）。
	3) 流程跑通后，再把权限收敛到最小：只保留“查询/列举/描述”类权限（Describe/List/Get）。
	4) 如果“地域刷新失败/报权限不足”，通常是：RAM 用户未授权、策略范围不包含该产品、或策略未生效。

3. **CMDB 侧准备（否则页面下拉可能为空）**
	- 在 CMDB 资产数据中已维护“阿里云账号”实例（页面会以“云账号”下拉选择）。
	- 明确采集范围：采集哪个账号、哪些地域、哪些资源类型（ECS/RDS/OSS 等）。

4. **接入点网络（任务在哪跑，就在哪验证）**
	- 接入点可解析并访问阿里云 API 域名（DNS 正常）。
	- 接入点可访问公网 `443/TCP`（或通过公司代理/NAT 出口访问）。
	- 若你们环境必须走代理，请确保接入点已配置代理且允许访问阿里云 API。

5. **地域（RegionId）选择方式**
	- 本插件需要先用你的密钥刷新地域列表，再选择一个地域（`RegionId`）。



### 操作步骤
### 步骤 1：网络连通性自测
- Linux：`curl -I https://sts.aliyuncs.com`
- Windows PowerShell：`Test-NetConnection sts.aliyuncs.com -Port 443`



### 步骤 2：在 CMDB 上创建采集任务
在新增任务时，你需要重点关注“凭据/鉴权”相关字段：

- `AccessKey`：阿里云 RAM 用户的 `AccessKeyId`（相当于账号标识）。
- `AccessSecret`：与 `AccessKeyId` 配套的 `AccessKeySecret`（相当于密钥/密码）。
- `RegionId`（页面通常显示为“地域/Region”）：要采集的地域。需要先用上面的密钥刷新地域列表，再选择一个。




### 采集内容（字段字典）

### ECS (aliyun_ecs)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例显示名 |
| resource_id | 实例 ID |
| ip_addr | 内网主 IP |
| public_ip | 公网主 IP（无则回退内网） |
| region | 地域 ID |
| zone | 可用区 |
| vpc | 所属 VPC |
| status | 运行状态 |
| instance_type | 规格类型 |
| os_name | 操作系统名称 |
| vcpus | vCPU 数 |
| memory | 内存（MB） |
| charge_type | 计费类型 |
| create_time | 创建时间 |
| expired_time | 到期时间（包年包月） |

### OSS Bucket (aliyun_bucket)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | Bucket 名称 |
| resource_id | Bucket 名称（同名） |
| location | 地域 |
| extranet_endpoint | 公网访问域名 |
| intranet_endpoint | 内网访问域名 |
| storage_class | 存储类型 |
| cross_region_replication | 跨区域复制状态 |
| block_public_access | 公共访问拦截状态 |
| creation_date | 创建时间 |

### RDS MySQL / PostgreSQL (aliyun_mysql / aliyun_pgsql)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例描述 |
| resource_id | 实例 ID |
| region | 地域 |
| zone | 主可用区 |
| zone_slave | 从/备可用区列表 |
| engine | 引擎类型 |
| version | 引擎版本 |
| type | 实例类型（主/从等） |
| status | 状态 |
| class | 规格 |
| storage_type | 存储类型 |
| network_type | 网络类型 |
| connection_mode | 连接模式 |
| lock_mode | 锁定模式 |
| cpu | CPU 核数 |
| memory_mb | 内存 MB |
| charge_type | 计费类型 |
| create_time | 创建时间 |
| expire_time | 到期时间 |

### Redis (aliyun_redis)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例名称 |
| resource_id | 实例 ID |
| region | 地域 |
| zone | 可用区 |
| engine_version | 引擎版本 |
| architecture_type | 架构（单机/集群） |
| capacity | 容量 |
| network_type | 网络类型 |
| connection_domain | 连接域名 |
| port | 端口 |
| bandwidth | 带宽 |
| shard_count | 分片数量 |
| qps | QPS 指标 |
| instance_class | 规格 |
| package_type | 套餐类型 |
| charge_type | 计费类型 |
| create_time | 创建时间 |
| end_time | 到期时间 |

### MongoDB (aliyun_mongodb)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例描述 |
| resource_id | 实例 ID |
| region | 地域 |
| zone | 主可用区 |
| zone_slave | 备/隐藏区 |
| engine | 引擎 |
| version | 版本 |
| type | 类型（副本集/分片等） |
| status | 状态 |
| class | 规格 |
| storage_type | 存储类型 |
| storage_gb | 存储容量 GB |
| lock_mode | 锁定模式 |
| charge_type | 计费类型 |
| create_time | 创建时间 |
| expire_time | 到期时间 |

### 负载均衡 CLB (aliyun_clb)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例名称 |
| resource_id | 实例 ID |
| region | 地域 |
| zone | 主可用区 |
| zone_slave | 备可用区 |
| vpc | 所属 VPC |
| ip_addr | 负载均衡地址 |
| status | 状态 |
| class | 规格 |
| charge_type | 计费类型 |
| create_time | 创建时间 |

### Kafka 实例 (aliyun_kafka_inst)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例名称 |
| resource_id | 实例 ID |
| region | 地域 |
| zone | 可用区 |
| vpc | 所属 VPC |
| status | 状态 |
| class | 实例规格 |
| storage_gb | 磁盘容量 GB |
| storage_type | 磁盘类型 |
| msg_retain | 消息保留时长 |
| topoc_num | Topic 上限 |
| io_max_read | 最大读取吞吐 |
| io_max_write | 最大写入吞吐 |
| charge_type | 计费类型 |
| create_time | 创建时间 |