### 说明
该插件通过腾讯云开放 API（SDK）采集腾讯云账户下的资产清单，包括 CVM、CDB（MySQL）、COS、Redis、MongoDB、Pulsar、RocketMQ、CLB、EIP、CFS、域名等资源类型，统一格式化后同步至 CMDB。采集为只读，agentless（无代理）方式，由你选择的“接入点”出网调用腾讯云 API。

### 操作入口与执行位置
在 CMDB Web 页面：
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **腾讯云**。
3. 点击“新增任务”，按步骤填写并保存。

说明：任务实际执行发生在你选择的“接入点”上；连通性自测命令应在接入点机器上执行。

### 前置要求 / 权限
1. **接入点网络**：接入点可出网访问 `*.tencentcloudapi.com`（公网 `443/TCP`，或通过代理/NAT 出口访问）。
2. **创建只读 CAM 子账号**：为采集创建专用 CAM 子账号，启用编程访问 / API 密钥并获取 `SecretId` / `SecretKey`。
3. **只读授权**：为该子账号授予**只读**权限。可先绑定系统只读策略（如 `QcloudXXXReadOnlyAccess` 系列，或各产品的只读策略）快速跑通，验证后收敛为仅 `Describe*`/`List*` 只读 API。

### 操作步骤
#### 步骤 1：网络连通性自测（接入点执行）
- Linux：`curl -I https://cvm.tencentcloudapi.com`
- Windows PowerShell：`Test-NetConnection cvm.tencentcloudapi.com -Port 443`

判断标准：能建立 HTTPS 连接即可。

#### 步骤 2：创建只读 CAM 账号并拿 SecretId/SecretKey
按上文“前置要求 / 权限”创建专用 CAM 子账号，授予只读权限，并记录 `SecretId` 与 `SecretKey`（SecretKey 通常仅创建时完整展示一次）。

#### 步骤 3：填写任务（页面操作）
新增任务时填写凭据与参数（见下文“凭据字段说明”），设置采集周期并保存。

#### 步骤 4：验证结果
- 保存并执行后，在任务详情查看 `新增 / 更新 / 删除` 摘要；在 CMDB 中应能查询到对应资源实例。
- 若某类资源为空或报权限不足，多为子账号未授予对应产品只读权限、地域无资源或接入点无法出网，核对后重采。

### 凭据字段说明
- `secret_id`：腾讯云 SecretId（相当于账号标识）。落库自动加密。建议使用专用只读子账号，不要复用主账号。
- `secret_key`：腾讯云 SecretKey（相当于密钥/密码）。落库自动加密。
- `timeout`：API 请求超时时间。
- `ssl`：是否启用 SSL。高级选项，通常无需修改，默认启用。
- `host`：自定义 Endpoint。高级选项，通常无需修改，留空使用默认 Endpoint，仅自建网关/网络受限时填写。

### 采集内容（字段字典）
各资源类型均以 `belong` 关系关联到 `qcloud`。以下为概要核心字段：

| 资源类型 | model_id | 核心字段（概要） |
| :--- | :--- | :--- |
| CVM 云服务器 | qcloud_cvm | resource_name、resource_id、region、zone、status、规格（CPU/内存/存储等，依资源类型而定）等 |
| MySQL（CDB） | qcloud_mysql | resource_name、resource_id、region、zone、status、规格（CPU/内存/存储等，依资源类型而定）等 |
| Redis | qcloud_redis | resource_name、resource_id、region、zone、status、规格（CPU/内存/存储等，依资源类型而定）等 |
| MongoDB | qcloud_mongodb | resource_name、resource_id、region、zone、status、规格（CPU/内存/存储等，依资源类型而定）等 |
| PostgreSQL | qcloud_pgsql | resource_name、resource_id、region、zone、status、规格（CPU/内存/存储等，依资源类型而定）等 |
| RocketMQ 集群 | qcloud_rocketmq | resource_name、resource_id、region、zone、status 等 |
| Pulsar 集群 | qcloud_pulsar_cluster | resource_name、resource_id、region、status、规格（CPU/内存/存储等，依资源类型而定）等 |
| CMQ 队列 | qcloud_cmq | resource_name、resource_id、region、status 等 |
| CMQ Topic | qcloud_cmq_topic | resource_name、resource_id、region、status 等 |
| 负载均衡 CLB | qcloud_clb | resource_name、resource_id、region、status、规格（CPU/内存/存储等，依资源类型而定）等 |
| EIP 弹性公网 IP | qcloud_eip | resource_name、resource_id、region、status、ip_addr 等 |
| COS 存储桶 | qcloud_bucket | resource_name、resource_id、region 等 |
| 文件系统 CFS | qcloud_filesystem | resource_name、resource_id、region、zone、status、规格（CPU/内存/存储等，依资源类型而定）等 |
| 域名 | qcloud_domain | resource_name、resource_id、status、到期时间 等 |

**关联关系**
- 上述各资源均以 `belong qcloud` 归属到对应腾讯云账号实例。
