### 说明
基于腾讯云开放 API 获取可用地域，采集计算、数据库、缓存、消息、网络、存储与域名等核心资源清单与关键属性，统一格式化后同步至 CMDB。

腾讯云侧的访问凭据为 SecretId / SecretKey；在 CMDB 页面中对应字段名为 `AccessKey` / `AccessSecret`。如果你希望按“入门运维 SOP”一步步操作，请按下方步骤执行。



### 操作入口与执行位置
在 CMDB Web 页面：
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **腾讯云**。
3. 点击“新增任务”，按本 SOP 填写并保存。

说明：任务实际执行发生在你选择的“接入点”上；所有网络连通性自测命令，都应该在该接入点机器上执行。



### 前置要求
开始前建议逐条确认（按“先跑通、再最小权限”的原则）：

1. **腾讯云控制台：创建 CAM 子账号并生成 SecretId / SecretKey**
	1) 登录腾讯云控制台。
	2) 进入：`访问管理 CAM` → `用户` → `新建用户`。
	3) 建议创建“子用户/用户”，并启用 **编程访问 / API 密钥**（不同界面可能叫“编程访问”“访问方式：API 密钥”“创建 SecretId/SecretKey”）。
	4) 创建完成后，在该用户的“API 密钥/凭证”页面获取一对 `SecretId` / `SecretKey`。
	5) 妥善保存 `SecretKey`（通常只在创建时完整展示一次），建议单独存放并定期轮换。

2. **腾讯云控制台：给 CAM 子账号授权（建议先只读跑通）**
	1) 进入：`访问管理 CAM` → `策略` / `权限管理`，或在用户详情页直接“关联策略/授权”。
	2) 首次验证建议先绑定只读类策略（ReadOnly/Describe/List 等查询权限），用于快速排障。
	3) 流程跑通后，再按需收敛到最小权限：只保留你确实要采集产品的查询权限（例如 CVM/CLB/COS/数据库/缓存等的 Describe/List 权限）。
	4) 如果“地域刷新失败/报权限不足”，通常是：子账号未授权、策略范围不包含对应产品，或密钥已禁用。

3. **接入点网络（任务在哪跑，就在哪验证）**
	- 接入点可解析并访问腾讯云公开 API（公网 `443/TCP`）。
	- 若你们环境必须走代理/NAT 出口，请确保接入点已配置代理并允许访问 `api.tencentcloudapi.com`。



### 操作步骤
### 步骤 1：网络连通性自测（接入点执行）
- Linux：`curl -I https://api.tencentcloudapi.com`
- Windows PowerShell：`Test-NetConnection api.tencentcloudapi.com -Port 443`



### 步骤 2：在 CMDB 上创建采集任务
在新增任务时，你需要重点关注“凭据/鉴权”相关字段：

- `AccessKey`：腾讯云 `SecretId`（相当于账号标识）。
- `AccessSecret`：腾讯云 `SecretKey`（相当于密钥/密码）。
- `RegionId`（页面通常显示为“地域/Region”）：要采集的地域。需要先用上面的密钥刷新地域列表，再选择一个。



### 常见问题排查
1. **地域刷新失败**：多为密钥错误/无权限，或接入点无法访问腾讯云 API。
2. **某些资源为空**：确认地域确有资源，并检查该产品是否已授予查询权限。
3. **限流**：适当拉长采集周期，或申请提高 API 配额。



### 采集内容（字段字典）

### CVM (qcloud_cvm)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例名称 |
| resource_id | 实例 ID |
| ip_addr | 内网 IP 列表 |
| public_ip | 公网 IP 列表 |
| region | 地域 |
| zone | 可用区 |
| vpc | VPC 信息结构 |
| status | 实例状态 |
| instance_type | 规格类型 |
| os_name | 操作系统名称 |
| vcpus | vCPU 数 |
| memory_mb | 内存容量(MB) |
| charge_type | 计费类型 |

### RocketMQ 集群 (qcloud_rocketmq)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 集群名称 |
| resource_id | 集群 ID |
| region | 地域 |
| zone | 可用区 |
| status | 状态 |
| topic_num | Topic 总数量上限 |
| used_topic_num | 已用 Topic 数 |
| tpsper_name_space | 集群 TPS 上限 |
| name_space_num | 命名空间上限 |
| used_name_space_num | 已用命名空间数 |
| group_num | Group 上限 |
| used_group_num | 已用 Group 数 |

### MySQL (qcloud_mysql)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例名称 |
| resource_id | 实例 ID |
| ip_addr | 实例访问 IP |
| region | 地域 |
| zone | 可用区 |
| status | 状态(映射) |
| volume | 磁盘大小(GB) |
| memory_mb | 内存(MB) |
| charge_type | 计费类型 |

### Redis (qcloud_redis)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例名称 |
| resource_id | 实例 ID |
| ip_addr | 外网 IP |
| vpc | VPC ID |
| region | 地域(映射) |
| zone | 可用区 |
| port | 端口 |
| wan_address | 外网地址 |
| status | 状态 |
| sub_status | 子状态 |
| engine | 产品类型 |
| version | 兼容版本 |
| Type | 架构版本 |
| memory_mb | 内存容量(MB) |
| shard_size | 分片大小 |
| shard_num | 分片数量 |
| replicas_num | 副本数量 |
| client_limit | 最大连接数 |
| net_limit | 最大网络吞吐(Mb/s) |

### MongoDB (qcloud_mongodb)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例名称 |
| resource_id | 实例 ID |
| ip_addr | 访问 IP |
| tag | 标签列表 |
| project_id | 项目 ID |
| vpc | VPC ID |
| region | 地域 |
| zone | 可用区 |
| port | 端口 |
| status | 状态 |
| cluster_type | 实例类型 |
| machine_type | 配置类型 |
| version | 引擎版本 |
| cpu | CPU 核数 |
| memory_mb | 内存(MB) |
| volume_mb | 磁盘容量(MB) |
| secondary_num | 从节点数 |
| mongos_cpu | Mongos CPU |
| mongos_memory_mb | Mongos 内存(MB) |
| mongos_node_num | Mongos 节点数 |
| charge_type | 计费类型 |

### PostgreSQL (qcloud_pgsql)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 实例名称 |
| resource_id | 实例 ID |
| tag | 标签列表 |
| project_id | 项目 ID |
| vpc | VPC ID |
| region | 地域 |
| zone | 可用区 |
| status | 状态 |
| charset | 字符集 |
| engine | 引擎 |
| mode | 架构类型 |
| version | 数据库版本 |
| kernel_version | 内核版本 |
| cpu | CPU 核数 |
| memory_mb | 内存(MB) |
| volume_mb | 磁盘容量(MB) |
| charge_type | 计费类型 |

### Pulsar 集群 (qcloud_pulsar_cluster)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 集群名称 |
| resource_id | 集群 ID |
| tag | 标签 |
| project_id | 项目 ID |
| region | 地域 |
| status | 状态 |
| version | 版本 |
| vpc_endpoint | 内网接入地址 |
| public_endpoint | 公网接入地址 |
| max_namespace_num | 命名空间上限 |
| max_topic_num | Topic 上限 |
| max_qps | 最大 QPS |
| max_retention_s | 消息保留时间(s) |
| max_storage_mb | 最大存储容量(MB) |
| max_delay_s | 最长消息延迟(s) |
| charge_type | 计费类型 |

### CMQ 队列 (qcloud_cmq)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 队列名称 |
| resource_id | 队列 ID |
| tag | 标签 |
| region | 地域 |
| status | 状态 |
| max_delay_s | 消息未确认最大时间 |
| polling_wait_s | 长轮询等待时间 |
| visibility_timeout_s | 可见性超时(隐藏时长) |
| msg_max_len | 消息最大长度(B) |
| qps | QPS 限制 |

### CMQ Topic (qcloud_cmq_topic)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | Topic 名称 |
| resource_id | Topic ID |
| tag | 标签 |
| region | 地域 |
| status | 状态 |
| max_retention_s | 消息生命周期(s) |
| max_message_b | 消息最大长度(B) |
| filter_type | 过滤类型 |
| qps | QPS 限制 |

### 负载均衡 CLB (qcloud_clb)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 负载均衡名称 |
| resource_id | 实例 ID |
| tag | 标签 |
| project_id | 项目 ID |
| security_group_id | 安全组 ID |
| vpc | VPC ID |
| region | 地域 |
| master_zone | 主可用区 |
| backup_zone | 备可用区列表 |
| status | 状态 |
| domain | 访问域名 |
| ip_addr | VIP 列表 |
| type | 网络类型 |
| isp | 运营商 |
| charge_type | 计费类型 |

### EIP (qcloud_eip)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | EIP 名称 |
| resource_id | EIP ID |
| tag | 标签 |
| region | 地域 |
| status | 状态 |
| type | 类型 |
| ip_addr | 公网 IP |
| instance_type | 绑定资源类型 |
| instance_id | 绑定资源 ID |
| isp | 线路类型 |
| charge_type | 计费类型 |

### COS Bucket (qcloud_bucket)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | Bucket 名称 |
| resource_id | Bucket 名称 |
| region | 所在地域 |

### 文件系统 CFS (qcloud_filesystem)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 文件系统名称 |
| resource_id | 文件系统 ID |
| tag | 标签 |
| region | 地域 |
| zone | 可用区 |
| status | 状态 |
| protocol | 协议类型 |
| type | 存储类型 |
| net_limit | 吞吐上限(MiB/s) |
| size_gib | 总容量(GiB) |

### 域名 (qcloud_domain)
| Key 名称 | 含义 |
| :----------- | :--- |
| resource_name | 域名 |
| resource_id | 域名 ID |
| tld | 顶级域后缀 |
| status | 购买/状态标识 |
| expired_time | 到期时间 |