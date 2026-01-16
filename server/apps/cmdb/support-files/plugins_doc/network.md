## 说明
该插件基于 SNMP（无 Agent）周期抓取网络设备系统与接口 OID，标准化输出设备与接口资产并同步至 CMDB。

说明：系统中存在两个 SNMP 相关插件：
- “NetWork”：用于发现网络设备与接口资产；
- “网络拓扑”：用于采集设备间连接关系（依赖 ARP/桥表等 OID）。

本文件作为统一说明：当你在页面选择不同插件时，配置项类似，但拓扑采集对设备侧权限与可见性要求更高。

---

## 操作入口与执行位置
在 CMDB Web 页面：
1. 进入“CMDB → 资产管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **NetWork（SNMP）**。
3. 点击“新增任务”，按本 SOP 填写并保存。

说明：任务实际执行发生在你选择的“接入点”上；所有网络连通性自测命令，都应该在该接入点机器上执行。

---

## 前置要求
1. 设备开启 SNMP v2/v2c 或 v3，接入点到设备 `161/UDP` 连通。
2. v2/v2c 需要 community；v3 需要用户名、认证/加密算法与密钥。
3. 设备允许读取基础 MIB（至少 sysDescr、sysObjectID、ifTable）。
4. 如需拓扑采集，通常还需要允许读取 ARP/桥表/FDB 等相关 OID；并确保设备侧 ACL 允许接入点访问。

---

## 步骤 1：网络与账号自测（接入点执行）
建议先用 `snmpwalk/snmpget` 进行自测（需要安装 Net-SNMP 工具）。

### SNMP v2c 示例
```bash
snmpget -v2c -c <community> <device_ip> 1.3.6.1.2.1.1.1.0
snmpget -v2c -c <community> <device_ip> 1.3.6.1.2.1.1.2.0
```

### SNMP v3 示例（认证加密）
```bash
snmpget -v3 -l authPriv -u <username> -a SHA -A <authkey> -x AES -X <privkey> <device_ip> 1.3.6.1.2.1.1.1.0
```

判断标准：能返回 sysDescr/sysObjectID 即通过。

如需拓扑采集，建议额外验证 ARP 表：
```bash
snmpwalk -v2c -c <community> <device_ip> 1.3.6.1.2.1.4.22
```

---

## 步骤 2：在 CMDB 上创建采集任务（页面操作）
1. 进入“专业采集”，选择 **NetWork（SNMP）** 插件。
2. 点击“新增任务”。
3. 基本配置：填写任务名称、周期、超时、组织、接入点。
4. 采集对象（二选一）：
  - IP 范围：填写起止 IP（用于批量发现）。
  - 选择资产：从资产列表选择目标设备（适合你已维护设备资产的场景）。
5. 凭据：
  - 选择 SNMP 版本（v2/v2c/v3）。
  - 填写端口（默认 161）。
  - v2/v2c：填写 community。
  - v3：填写安全级别（认证不加密/认证加密）、用户名、认证密钥、哈希算法（SHA/MD5）；如选择“认证加密”还需填写加密算法与加密密钥。
6. 保存后，在任务列表中点击“同步”（立即执行）做一次验证。

---

## 验收（怎么判断成功）
1. 任务执行状态为“成功”。
2. 在资产数据中能看到设备/接口被新增或更新。
3. 设备型号/品牌依赖 sysObjectID 映射；如果显示为未知，请到“SOID 特征库”补充映射。

---

## 常见问题排查
1. **超时/无响应**：确认设备开启 SNMP、ACL 允许接入点访问、UDP/161 未被拦截。
2. **认证失败**：确认 v2c community 或 v3 用户/算法/密钥完全一致（大小写与空格都会导致失败）。
3. **采集到但型号未知**：需要维护 sysObjectID 映射（SOID 特征库）。
4. **拓扑采集关系不完整**：拓扑推导依赖设备可见的 ARP/转发表，且与设备覆盖范围相关；建议先扩大覆盖范围，再调整周期与超时。

---

## 采集内容（字段字典）
| Key 名称 | 含义 |
| :----------- | :--- |
| device.ip_addr | 设备管理 IP（来自你选择的目标 IP/资产管理 IP） |
| device.port | SNMP 端口(默认161) |
| device.model | 设备型号(通过 OID 映射) |
| device.brand | 设备品牌(通过 OID 映射) |
| device.inst_name | 设备展示名：`{ip_addr}-{model_id}` |
| interface.inst_name | 接口展示名：`{device_inst_name}-{alias|description}` |
| interface.self_device | 接口所属设备 inst_name |
| interface.status | 接口运行状态(UP/Down/Other) |
| interface.mac | 接口MAC地址 |

