### 说明
该插件通过火山引擎 OpenAPI 采集一个账号、一个地域下的资产清单，包括云服务器、公网 IP、传统型负载均衡、云数据库 MySQL、云数据库 PostgreSQL 和对象存储。采集为只读，由你选择的接入点出网调用接口。一条任务只采集一个地域，换地域请另建任务。

### 操作入口与执行位置
在 CMDB Web 页面：
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **火山引擎**。
3. 点击“新增任务”，选择已有的火山引擎账号，填写凭据和地域后保存。

任务在所选接入点上执行。连通性自测也在接入点机器上执行。

### 前置要求 / 权限
1. **火山引擎账号**：先在 CMDB 资产中创建一个“火山引擎”账号。`endpoint` 留空时使用公网 OpenAPI 和 `tos-{地域}.volces.com`；填写后，OpenAPI 和对象存储都改用这个地址。
2. **接入点网络**：接入点可访问 `*.volcengineapi.com` 和 `*.volces.com` 的 `443/TCP`。使用自定义地址时，改为访问该地址。
3. **只读凭据**：使用专用 AccessKey，只授予本插件会调用的只读接口：
   - 云服务器：`DescribeRegions`、`DescribeInstances`
   - 公网 IP：`DescribeEipAddresses`
   - 传统型负载均衡：`DescribeLoadBalancers`
   - 云数据库 MySQL：`DescribeDBInstances`
   - 云数据库 PostgreSQL：`DescribeDBInstances`
   - 对象存储：`ListBuckets`

### 操作步骤
#### 步骤 1：网络连通性自测（接入点执行）
- Linux：`curl -I https://ecs.cn-beijing.volcengineapi.com`
- Windows PowerShell：`Test-NetConnection ecs.cn-beijing.volcengineapi.com -Port 443`

能建立 HTTPS 连接即可。自测地域可以换成任务实际选择的地域。

#### 步骤 2：准备 AccessKey
按上文创建或选用只读 AccessKey，记录 AccessKey ID 和 AccessKey Secret。Secret 只在创建时展示一次。

#### 步骤 3：填写任务
选择火山引擎账号、接入点和这一个地域，填写 AccessKey ID 与 AccessKey Secret，设置采集周期并保存。

#### 步骤 4：验证结果
- 执行后在任务详情查看新增、更新和删除摘要，并在 CMDB 中查到对应实例。
- 某一类资源权限不足、限流或分页中断时，该类记为失败，已经成功的类仍会更新，这一轮不删除已有资产。
- 对象存储只保留 `Location` 与任务地域一致的桶。
- 页面账号下拉为空时，先创建火山引擎账号资产。

### 凭据字段说明
- AccessKey ID：火山引擎访问密钥 ID。落库加密。
- AccessKey Secret：与 AccessKey ID 配套的密钥。落库加密，不下发到采集配置正文。
- 地域：本任务采集的 RegionId，例如 `cn-beijing`。地域列表来自云服务器 `DescribeRegions`。
- 账号 `endpoint`：可选。公网留空；专有云或代理地址填写后，OpenAPI 和对象存储都使用该主机。

### 采集内容（字段字典）
子资源以 `belong` 归属到 `volcengine_account`。实例名写成 `名称(资源ID)`，采集按 `resource_id` 认出同一条资产，云上改名后更新原实例。

| 资源类型 | model_id | 核心字段（概要） |
| :--- | :--- | :--- |
| 云服务器 | volcengine_ecs | resource_name、resource_id、region、zone、ip_addr、public_ip、status、instance_type、os_name、vcpus、memory_mb、charge_type |
| 公网 IP | volcengine_eip | resource_name、resource_id、region、ip_addr、status、bandwidth、instance_type、instance_id |
| 传统型负载均衡 | volcengine_clb | resource_name、resource_id、region、vpc、ip_addr、public_ip、status、type、charge_type |
| 云数据库 MySQL | volcengine_mysql | resource_name、resource_id、region、zone、vpc、ip_addr、port、version、status、storage_gb |
| 云数据库 PostgreSQL | volcengine_pgsql | resource_name、resource_id、region、zone、vpc、ip_addr、port、version、status、storage_gb |
| 对象存储 | volcengine_tos | resource_name、resource_id、region、location、extranet_endpoint、intranet_endpoint、bucket_type、creation_date |

**关联关系**
- 上述子资源均 `belong` 到对应火山引擎账号。
- 公网 IP 的绑定类型为云服务器或传统型负载均衡时，按资源 ID 新增 `connect`。其他绑定类型只归属账号。采集只新增连接，不删除已有连接。
