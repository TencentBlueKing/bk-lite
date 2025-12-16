## 说明
基于阿里云开放 API 并行拉取账户下多类资源（ECS、RDS、Redis、MongoDB、OSS、CLB、Kafka 等）清单与核心属性，统一格式化后同步至 CMDB。

## 前置要求
1. 提供有效 AccessKey / AccessSecret，具备只读或查询权限（ECS、RDS、Redis、MongoDB、OSS、SLB、Kafka 等）。
2. 指定 RegionId（默认 cn-hangzhou）；需对各目标地域开放访问。
3. 账号未触发访问频控（支持分页与多线程并发抓取）。

## 采集内容

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