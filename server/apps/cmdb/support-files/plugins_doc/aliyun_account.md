## 说明
基于阿里云开放 API 并行拉取账户下多类资源（ECS、RDS、Redis、MongoDB、OSS、CLB、Kafka 等）清单与核心属性，统一格式化后同步至 CMDB。
---

## 操作入口与执行位置
在 CMDB Web 页面：
1. 进入“CMDB → 资产管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **阿里云**。
3. 点击“新增任务”，按步骤填写并保存。

说明：任务实际执行发生在你选择的“接入点”上；连通性自测命令应在接入点机器上执行。

---

## 前置要求（建议做法）
1. 创建专用于采集的 RAM 用户，并生成 AccessKey / AccessSecret。
2. 授予该 RAM 用户目标产品的只读/查询权限（建议先用只读策略跑通流程，再逐步收敛到最小权限）。
3. 接入点能访问阿里云 API（公网 `443/TCP`）。

---

## 步骤 1：网络连通性自测（接入点执行）
- Linux：`curl -I https://sts.aliyuncs.com`
- Windows PowerShell：`Test-NetConnection sts.aliyuncs.com -Port 443`

---

## 步骤 2：在 CMDB 上创建采集任务（页面操作）
1. 点击“新增任务”。
2. 选择云账号：从下拉列表选择要采集的阿里云账号（若为空，请先在 CMDB 资产数据中维护云账号实例）。
3. 基本配置：任务名称、周期、超时、组织、接入点。
4. 凭据：填写 `AccessKey` 与 `AccessSecret`。
5. 地域（Region）：点击地域右侧的“刷新”图标拉取地域列表，然后选择一个地域。
6. 保存后，回到任务列表点击“同步”（立即执行）验证。

---

## 验收与常见问题
1. 执行状态为“成功”，且资产数据中出现/更新 ECS、RDS、Redis 等资源。
2. 地域刷新失败：多为密钥错误/无权限，或接入点无法访问阿里云 API。
3. 部分资源为空：确认该地域确有资源，并检查是否对该产品授予了查询权限。
4. 限流/频控：适当拉长采集周期，或在云侧提升 API 配额。

---

## 采集内容（字段字典）

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