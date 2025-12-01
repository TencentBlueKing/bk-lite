## 说明
基于 SNMP (无 Agent) 周期抓取网络设备系统与接口 OID，标准化输出设备与接口资产及拓扑关联关系，同步至 CMDB。

## 前置要求
1. 设备开启 SNMP v2c 或 v3，连通端口 161。与接入点网络通畅
2. v2c 需提供有效 community；v3 需提供用户名、认证/加密方式与密钥。
3. 允许读取 sysDescr/ifTable/ifAlias/接口速率等基础 MIB；拓扑采集需开放 ARP/桥表相关 OID。

## 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| device.ip_addr | 设备管理 IP |
| device.port | SNMP 端口(默认161) |
| device.model | 设备型号(通过 OID 映射) |
| device.brand | 设备品牌(通过 OID 映射) |
| device.inst_name | 设备展示名：`{ip_addr}-{model_id}` |
| interface.inst_name | 接口展示名：`{device_inst_name}-{alias|description}` |
| interface.self_device | 接口所属设备 inst_name |
| interface.status | 接口运行状态(UP/Down/Other) |
| interface.mac | 接口MAC地址 |
