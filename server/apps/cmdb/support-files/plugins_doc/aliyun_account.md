### 说明
该插件通过阿里云开放 API（SDK）采集阿里云账户下的资产清单，包括 ECS、RDS、OSS、Redis、MongoDB、Kafka、CLB 等资源类型，统一格式化后同步至 CMDB。采集为只读，agentless（无代理）方式，由你选择的“接入点”出网调用阿里云 API。

### 操作入口与执行位置
在 CMDB Web 页面：
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **阿里云**。
3. 点击“新增任务”，按步骤填写并保存。

说明：任务实际执行发生在你选择的“接入点”上；连通性自测命令应在接入点机器上执行。

### 前置要求 / 权限
1. **接入点网络**：接入点可出网访问 `*.aliyuncs.com`（公网 `443/TCP`，或通过代理/NAT 出口访问）。
2. **创建只读 RAM 子账号**：为采集创建专用 RAM 子账号，启用 OpenAPI 调用访问并获取 `AccessKeyId` / `AccessKeySecret`。
3. **只读授权**：为该子账号授予**只读**权限。可先绑定系统只读策略快速跑通（如 `ReadOnlyAccess`，或各产品只读策略 `AliyunECSReadOnlyAccess`、`AliyunRDSReadOnlyAccess`、`AliyunOSSReadOnlyAccess` 等），验证后再收敛为自定义最小策略（仅 `ecs:Describe*`、`rds:Describe*`、`oss:List*`/`oss:GetBucketInfo` 等只读 API）。可收敛到的最小只读 API 例如：
   - ECS：`ecs:Describe*`
   - RDS：`rds:Describe*`
   - OSS：`oss:ListBuckets`、`oss:GetBucketInfo`
   - Redis：`r-kvstore:Describe*`
   - MongoDB：`dds:Describe*`
   - Kafka：`alikafka:Get*`
   - SLB/CLB：`slb:Describe*`

### 操作步骤
#### 步骤 1：网络连通性自测（接入点执行）
- Linux：`curl -I https://ecs.aliyuncs.com`
- Windows PowerShell：`Test-NetConnection ecs.aliyuncs.com -Port 443`

判断标准：能建立 HTTPS 连接即可。

#### 步骤 2：创建只读 RAM 账号并拿 AK/SK
按上文“前置要求 / 权限”创建专用 RAM 子账号，授予只读权限，并记录 `AccessKeyId` 与 `AccessKeySecret`（Secret 仅创建时展示一次）。

#### 步骤 3：填写任务（页面操作）
新增任务时填写凭据与参数（见下文“凭据字段说明”），设置采集周期并保存。

#### 步骤 4：验证结果
- 保存并执行后，在任务详情查看 `新增 / 更新 / 删除` 摘要；在 CMDB 中应能查询到对应资源实例。
- 若某类资源为空或报权限不足，多为子账号未授予对应产品只读权限、地域选择无资源或接入点无法出网，核对后重采。
- 若页面“阿里云账号”下拉为空，需先在 CMDB 资产中新增一个“阿里云账号”实例。

### 凭据字段说明
- `secret_id`：即阿里云 RAM 用户的 AccessKey ID。落库自动加密。建议使用专用只读子账号，不要复用主账号。
- `secret_key`：即与 AccessKey ID 配套的 AccessKey Secret。落库自动加密。
- `region_id`：采集地域，默认 `cn-hangzhou`。
- `timeout`：API 请求超时时间。
- `host`：可选。专有云场景下填写自定义 Endpoint，公共云一般留空。

### 采集内容（字段字典）
各资源类型均以 `belong` 关系关联到 `aliyun_account`。以下为概要核心字段：

| 资源类型 | model_id | 核心字段（概要） |
| :--- | :--- | :--- |
| ECS 云服务器 | aliyun_ecs | resource_name、resource_id、region、zone、status、规格 等 |
| OSS 存储桶 | aliyun_bucket | resource_name、resource_id、region、storage_class 等 |
| RDS MySQL | aliyun_mysql | resource_name、resource_id、region、zone、status、规格 等 |
| RDS PostgreSQL | aliyun_pgsql | resource_name、resource_id、region、zone、status、规格 等 |
| Redis | aliyun_redis | resource_name、resource_id、region、zone、status、规格 等 |
| MongoDB | aliyun_mongodb | resource_name、resource_id、region、zone、status、规格 等 |
| Kafka 实例 | aliyun_kafka_inst | resource_name、resource_id、region、zone、status、规格 等 |
| 负载均衡 CLB | aliyun_clb | resource_name、resource_id、region、zone、status、规格 等 |

**关联关系**
- 上述各资源均以 `belong aliyun_account` 归属到对应阿里云账号实例。
