# BK-Lite SNMP Trap Alert Source

这是 BK-Lite 告警中心内置的 `snmp_trap` 告警源说明，用于通过独立 bridge 接收并处理规范化后的 SNMP Trap 事件。

该方案复用现有 source-specific webhook 接入模式，不复用通用 `receiver_data` 接口，也不新增专用 `snmp_trap` receiver 路由。

- 接口地址：`/api/v1/alerts/api/source/snmp_trap/webhook/`
- 请求方法：`POST`
- 认证方式：请求头 `SECRET`
- 请求体格式：`{"events": [...]}`

## 方案说明

`snmp_trap` 告警源的职责是：

1. 接收由独立 SNMP Trap bridge 转发的标准事件列表；
2. 复用现有 `restful` adapter 与 `Event -> Recovery/Aggregation -> Alert` 生命周期；
3. 保留原始 Trap 上下文，便于后续排障与规则演进。

该通道当前不负责：

- 原始 UDP Trap 监听；
- PDU 解码；
- MIB 解析；
- 厂商全量 Trap 适配。

推荐链路：

```text
raw trap
 -> snmptrapd
 -> unix socket
 -> vector
 -> NATS/vector
 -> SNMP bridge
 -> /api/v1/alerts/api/source/snmp_trap/webhook/
```

## 首期支持范围

首期内置规则目前覆盖以下确定性 Trap 家族：

- `linkDown / linkUp`
- `BGP_PEER_DOWN / BGP_PEER_UP`

其余 Trap 暂未做内置规则映射，会按 `unknown_trap` fallback 处理。

无法命中的 Trap 将进入 `unknown_trap` fallback：

- `normalized_key = unknown_trap`
- `action = created`
- `level = 2`
- 不自动恢复已有告警

## 请求体格式

Bridge 发送到告警中心的请求体必须为：

```json
{
  "events": [
    {
      "push_source_id": "snmp_trap_bridge",
      "title": "交换机 GE1/0/3 端口 down",
      "description": "SNMP Trap bridge 转发事件",
      "item": "snmp_trap:link_down",
      "level": "2",
      "action": "created",
      "start_time": "1719912000",
      "external_id": "baf7a5cc9e0b8b7d9c1e3a0d8a2af001",
      "resource_id": "10.0.0.8",
      "resource_name": "10.0.0.8",
      "resource_type": "network_device",
      "labels": {
        "collect_type": "snmp_trap",
        "event_type": "snmp_trap",
        "trap_oid": "1.3.6.1.6.3.1.1.5.3",
        "node_ip": "10.0.0.8",
        "normalized_key": "link_down",
        "raw_message": "SNMPv2-MIB::snmpTrapOID.0=SNMPv2-MIB::linkDown ifIndex=3 ifName=GE1/0/3"
      }
    }
  ]
}
```

## 关键字段建议

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 告警标题 |
| `item` | 建议 | 建议使用 `snmp_trap:<normalized_key>` |
| `level` | 建议 | 显式级别，避免依赖默认值 |
| `action` | 建议 | 首期未知 Trap 一律 `created` |
| `external_id` | 强烈建议 | 用于恢复关联，必须稳定 |
| `start_time` | 建议 | 秒级/毫秒级时间戳 |
| `resource_id/resource_name/resource_type` | 建议 | 资源身份 |
| `labels` | 建议 | 存放 trap_oid、node_ip、varbinds、raw_message 等上下文 |

## 关键规则

1. `external_id` 必须稳定，不能依赖时间戳、展示文案或 varbind 顺序；
2. `recovery` 和 `closed` 只对明确命中的 Trap 规则生效；
3. 未命中的 Trap 一律按 `unknown_trap` 处理，避免误恢复；
4. 原始 Trap 上下文应保存在 `labels` 和 `raw_data` 中，便于排障；
5. 如果上游无法稳定提供 clear trap 语义，建议只发送 `created` 事件。

## curl 示例

```bash
curl --location --request POST 'http://bk-lite-server:8001/api/v1/alerts/api/source/snmp_trap/webhook/' \
  --header 'SECRET: your-snmp-source-secret' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "events": [
      {
        "push_source_id": "snmp_trap_bridge",
        "title": "交换机 GE1/0/3 端口 down",
        "description": "SNMP Trap bridge 转发事件",
        "item": "snmp_trap:link_down",
        "level": "2",
        "action": "created",
        "start_time": "1719912000",
        "external_id": "baf7a5cc9e0b8b7d9c1e3a0d8a2af001",
        "resource_id": "10.0.0.8",
        "resource_name": "10.0.0.8",
        "resource_type": "network_device",
        "labels": {
          "trap_oid": "1.3.6.1.6.3.1.1.5.3",
          "node_ip": "10.0.0.8",
          "normalized_key": "link_down",
          "collect_type": "snmp_trap",
          "event_type": "snmp_trap"
        }
      }
    ]
  }'
```

返回 `{"status": "success", ...}` 表示接收成功。
