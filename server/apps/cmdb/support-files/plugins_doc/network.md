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

### SOID 匹配与目录同步
- 采集到的 `sysObjectID` 会先去掉首尾空白和前导点；若值为 `SNMPv2-SMI::enterprises.N...` 或 `enterprises.N...`，展开为 `1.3.6.1.4.1.N...`。
- 设备品牌、型号和类型优先按完整 OID 精确匹配；未命中时再按目录键做最长前缀匹配（比较 OID 弧数，最短 7 弧 `1.3.6.1.4.1.<enterprise>`），不把 `1.3.6.1.4.1` 当作兜底，也不按 `sysDescr` 猜测。
- `verified` 记录来自可复核的厂商官方产品 MIB 或产品文档；`legacy-compatible` 记录用于保留历史识别能力，不代表已经取得同等级别的公开产品身份依据。企业前缀行用于识别厂商，型号为 `未知`。
- 升级前执行 `python manage.py init_oid --dry-run` 可查看稳定排序的完整差异，包括新增及其目标值、更新字段的前后值、用户覆盖、目录外遗留和汇总数量；该命令不会写数据库。
- 正常执行 `batch_init` 或 `python manage.py init_oid` 会幂等同步内置目录：每次启动都会把 `built_in=True` 重置为目录值，新增缺失项、原地纠正内置项、保留未变化项和目录外遗留项。重复同步不会删除后重建记录。
- 同一 OID 的 POST 会被 API 拒绝。用户覆盖只能 UPDATE 已有行并设 `built_in=False`；这类记录始终优先，同步报告为“用户覆盖”且不会改写。
- `--force` 仅为兼容旧自动化保留，仍执行安全的全量比较，不会删除或重建内置记录。
- 未知 SOID 会保留原始 OID，品牌和型号标记为 `未知`，设备类型按 `switch` 兼容处理。

#### 发布、验证与回滚
1. 发布前在待升级版本和数据库副本上执行 `python manage.py init_oid --dry-run`，重点复核设备类型变化、用户覆盖和目录外遗留。
2. 生产同步前备份数据库，并确认备份覆盖 `OidMapping` 数据及用户自定义 SOID；保留 dry-run 输出作为变更审计记录。
3. 发布后执行正常 `batch_init`（或单独执行 `python manage.py init_oid`），再执行一次 `--dry-run`；此时应无新增和更新，除用户覆盖外的已同步内置项均计入未变化，自定义项仍计入用户覆盖。
4. 应用版本回滚不会自动反向恢复已经纠正的内置映射。需要恢复旧映射时，从同步前数据库备份恢复 `OidMapping` 数据；用户自定义记录虽不会被同步覆盖，也应纳入同一备份和核对流程。

### 采集内容（字段字典）
**网络设备（network）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名（形如 `{ip}-设备类型`） |
| ip_addr | 设备管理 IP |
| soid | sysObjectID（SNMP 标准设备对象标识），用于在 OID 库中匹配设备型号、品牌和类型；未知 SOID 会保留原始 OID，品牌和型号标记为 `未知`，设备类型按 `switch` 兼容处理 |
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

> 补充说明：`model`、`brand` 依赖 `soid`（sysObjectID）在 OID 库中的匹配结果；`syslocation`、`syscontact` 等字段在设备未配置时采集结果为空。
