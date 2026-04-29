# Zabbix 告警源实施文档

## 1. 文档用途

本文面向实施、运维和上线测试人员，用于将现有 Zabbix 告警通过 Webhook Media Type 接入 BK-Lite 告警中心。

本文只保留实施所需内容：

- BK-Lite 侧需要准备什么
- Zabbix 侧需要配置什么
- 最终 URL、Header、字段应该怎么填
- 上线后如何验证链路是否打通
- 出问题时如何快速定位

## 2. 最终接入方式

Zabbix 告警源统一使用以下 webhook 路径：

```text
/api/v1/alerts/api/source/{source_id}/webhook/
```

示例：

- source_id 为 zabbix：

```text
https://alerts.example.com/api/v1/alerts/api/source/zabbix/webhook/
```

- source_id 为 zabbix-prod-core：

```text
https://alerts.example.com/api/v1/alerts/api/source/zabbix-prod-core/webhook/
```

认证方式：

- Header 名：SECRET
- Header 值：BK-Lite 告警源中配置的 secret

## 3. 实施前准备

### 3.1 BK-Lite 侧准备项

上线前在 BK-Lite 中准备一条 Zabbix 告警源，记录以下信息：

- source_id
- secret
- webhook_url

建议规则：

- 每个 Zabbix 实例使用一个独立 source_id
- 每个 source_id 使用独立 secret
- source_id 使用可识别命名，例如 zabbix-prod-core、zabbix-shared-platform

### 3.2 参数获取方式

推荐通过接口获取最终接入参数：

```text
GET /api/v1/alerts/api/alert_source/{id}/integration-guide/
```

重点看返回值：

- webhook_url
- headers.SECRET
- script_template

上线时以接口返回值为准，不要手工拼路径。

## 4. Zabbix 侧实施步骤

### 4.1 推荐脚本模板

下面示例假设：

- source_id：zabbix-prod-core
- secret：your_zabbix_secret
- BK-Lite 域名：alerts.example.com

```javascript
var params = JSON.parse(value);
var isRecovery = String(params.EventValue) === "0";
var payload = {
  source_id: "zabbix-prod-core",
  event: {
    external_id: String(params.ProblemId),
    title: params.Subject,
    description: params.Message,
    level: String(params.Severity || "3"),
    item: params.TriggerName,
    rule_id: params.TriggerId,
    resource_id: params.HostId,
    resource_name: params.HostName,
    resource_type: params.ResourceType || "",
    action: isRecovery ? "recovery" : "created",
    labels: {
      problem_id: String(params.ProblemId),
      event_id: String(params.EventId || ""),
      trigger_id: String(params.TriggerId || ""),
      host_id: String(params.HostId || ""),
      host_name: params.HostName || ""
    }
  }
};

var req = new HttpRequest();
req.addHeader("Content-Type: application/json");
req.addHeader("SECRET: your_zabbix_secret");
req.post("https://alerts.example.com/api/v1/alerts/api/source/zabbix-prod-core/webhook/", JSON.stringify(payload));
return "OK";
```

### 4.2 实施时必须确认

1. source_id 与 BK-Lite 中配置的一致
2. SECRET 与 BK-Lite 中保存的 secret 一致
3. Problem 和 Recovery 使用同一个 ProblemId
4. Recovery 阶段 EventValue=0 或 action=recovery

### 4.3 参数建议

建议至少传这些参数：

- ProblemId
- EventId
- TriggerId
- HostId
- HostName
- Severity
- Subject
- Message
- EventValue
- TriggerName
- ResourceType

实施关注点：

- ProblemId 是恢复闭环主键，不能变
- Severity 建议使用数字字符串 0/1/2/3

## 5. 手工验证步骤

### 5.1 先做 CURL 打通

在正式切 Zabbix Action 前，先用 CURL 验证 webhook 是否可达。

```bash
curl --location 'https://alerts.example.com/api/v1/alerts/api/source/zabbix-prod-core/webhook/' \
  --header 'SECRET: your_zabbix_secret' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "event": {
      "external_id": "10001",
      "title": "Zabbix CPU High",
      "description": "cpu usage > 90%",
      "level": "3",
      "item": "system.cpu.util",
      "rule_id": "30001",
      "resource_id": "40001",
      "resource_name": "host-1",
      "resource_type": "host",
      "action": "created",
      "labels": {
        "problem_id": "10001",
        "event_id": "20001",
        "trigger_id": "30001",
        "host_id": "40001",
        "host_name": "host-1"
      }
    }
  }'
```

判定标准：

- HTTP 返回 200
- BK-Lite 中能看到 created 事件

### 5.2 再做真实 Problem 验证

1. 触发一个 Zabbix Problem
2. 确认 Action 已调用 Webhook Media Type
3. 在 BK-Lite 中确认 created 事件已生成

### 5.3 恢复验证

1. 让问题恢复
2. 确认 Zabbix 再次发送 webhook
3. 在 BK-Lite 中确认 recovery 事件已生成
4. 核对 created / recovery 的 external_id 是否一致

## 6. 字段对应关系

Zabbix 进入 BK-Lite 后，关键字段对应关系如下：

| BK-Lite 字段 | 上游来源 |
| --- | --- |
| title | Subject 或 event.title |
| description | Message 或 event.description |
| level | Severity 或 event.level |
| item | TriggerName 或 event.item |
| rule_id | TriggerId 或 event.rule_id |
| external_id | ProblemId 或 event.external_id |
| resource_id | HostId 或 event.resource_id |
| resource_name | HostName 或 event.resource_name |
| action | EventValue=0 -> recovery，其他 -> created |

实施关注点：

- external_id 必须稳定使用 ProblemId
- Recovery 不能换 ProblemId

## 7. 快速排障

### 7.1 返回 Missing source_id

原因：

- URL 中没有正确带上 source_id

处理：

- 确认使用的是 /api/source/{source_id}/webhook/

### 7.2 返回 Invalid secret

原因：

- Header 中 SECRET 错误

处理：

- 对照 BK-Lite 告警源配置重新填写

### 7.3 created 有，recovery 没有

原因：

- ProblemId 在恢复阶段变化
- 或 EventValue 不是 0

处理：

- 确认 Recovery 使用同一个 ProblemId
- 确认 EventValue=0

## 8. 实施结论

Zabbix 实施只需要记住三件事：

1. 统一使用 /api/source/{source_id}/webhook/
2. Header 固定传 SECRET
3. ProblemId 必须在 Problem / Recovery 两次通知中保持一致
