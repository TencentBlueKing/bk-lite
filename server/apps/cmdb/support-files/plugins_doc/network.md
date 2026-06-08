### 说明
该插件通过 SNMP 协议发现网络设备及其接口信息（可选发现设备间拓扑），标准化同步至 CMDB。采集为**只读**，不修改设备任何配置。采集为 agentless（无代理）方式，由你选择的“接入点”直连设备。

本文档同时包含两部分：
1. 面向网络运维的操作步骤（如何准备与配置）。
2. 字段字典（采集到 CMDB 的字段含义）。

### 操作入口与执行位置
在 CMDB Web 页面：
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **网络设备**。
3. 点击“新增任务”，按步骤填写并保存。

说明：任务实际执行发生在你选择的“接入点”上；连通性自测命令应在接入点机器上执行。

### 前置要求
1. **网络连通**：接入点到设备的 `161/UDP` 连通。
2. **设备启用 SNMP**：设备需启用 SNMP v2c 或 v3，并授予只读 community（v2c）或只读账号（v3）。
3. **凭据准备**：根据所用 SNMP 版本，准备好对应的 community（v2c）或账号、认证/加密参数（v3）。

### 操作步骤
#### 步骤 1：网络连通性自测（接入点执行）
SNMP 走 UDP，端口连通性可用如下方式辅助判断（以实际工具为准）：
- Linux：`nc -vzu <device_ip> 161`
- 若接入点装有 Net-SNMP 工具，可直接验证 v2c：`snmpget -v2c -c <community> <device_ip> sysDescr.0`

判断标准：能返回设备 sysDescr 等基本信息即说明 SNMP 通路与凭据可用。

#### 步骤 2：填写任务（页面操作）
新增任务时，重点关注 SNMP 版本与凭据：先选择 `version`，再按版本填写对应字段（见下文“凭据字段说明”）。如需发现设备间拓扑，开启参数 `has_network_topo`。

#### 步骤 3：验证结果
- 保存并执行后，在任务详情查看 `新增 / 更新 / 删除` 摘要；在 CMDB 中应能查询到 `network` 设备及其下的 `interface` 接口实例。
- 若清单不全或采集失败，多为 community/账号只读权限未授予、SNMP 版本选择不匹配或 `161/UDP` 未放通，核对后重采。

### 凭据字段说明
SNMP 凭据按版本区分，请先确定 `version` 再填写对应字段。

**通用参数（v2c / v3 均需）**
- `version`：SNMP 版本，可选 `v2c` 或 `v3`。
- `snmp_port`：SNMP 端口，默认 `161`。
- `timeout`：单次请求超时时间。
- `retries`：请求重试次数。

**v2c 专用**
- `community`：只读团体名（community），相当于密码。落库自动加密。建议使用专用只读 community，不要复用可写 community。

**v3 专用**
- `username`：SNMP v3 用户名。
- `level`：安全级别，可选 `authNoPriv`（仅认证不加密）或 `authPriv`（认证 + 加密）。
- `integrity`：认证算法，可选 `md5` 或 `sha`。
- `authkey`：认证密钥，长度需 ≥ 8 位。落库自动加密。
- `privacy`：加密算法，可选 `des` 或 `aes`（仅 `level=authPriv` 时使用）。
- `privkey`：加密密钥，长度需 ≥ 8 位（仅 `level=authPriv` 时使用）。落库自动加密。

### 参数说明
- `has_network_topo`：是否开启拓扑发现（布尔）。开启后在采集接口的基础上，额外发现设备接口之间的连接关系（基于 ARP 表 / 接口表）。

### 采集内容（字段字典）
**网络设备（network）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名（形如 `{ip}-设备类型`） |
| ip_addr | 设备管理 IP |
| soid | sysObjectID（SNMP 标准设备对象标识），用于在 OID 库中匹配设备型号/品牌；未收录则 `model`/`brand` 为空 |
| port | SNMP 端口 |
| sysdescr | 设备系统描述（sysDescr） |
| sysname | 设备系统名称（sysName） |
| syslocation | 设备位置（sysLocation） |
| syscontact | 联系人信息（sysContact） |
| model | 设备型号（来自 OID 库匹配） |
| brand | 设备品牌 |

**接口（interface，network 的关联子项）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 接口实例展示名 |
| name | 接口别名 / 描述 |
| mac | 接口 MAC 地址 |
| status | 接口状态（UP / Down / Testing） |
| mtu | 接口 MTU |
| speed | 接口速率 |
| admin_status | 管理状态 |
| oper_status | 实际运行状态 |

**关联关系**
- `interface belong network`：接口归属设备。
- `interface connect interface`：接口间连接关系（仅在开启 `has_network_topo` 时发现，基于 ARP 表 / 接口表）。

> 补充说明：`model`、`brand` 依赖 `soid`（sysObjectID）在 OID 库中的匹配结果，若设备型号未收录则可能为空；`syslocation`、`syscontact` 等字段在设备未配置时采集结果为空。
