# Prometheus 告警源实施文档

## 1. 文档用途

本文面向实施、运维和上线测试人员，用于将现有 Prometheus + Alertmanager 的告警接入 BK-Lite 告警中心。

本文只保留实施所需内容：

- BK-Lite 侧需要准备什么
- Prometheus / Alertmanager 侧需要改什么
- 最终 URL、Header、字段应该怎么填
- 上线后如何验证链路是否打通
- 出问题时如何快速定位

## 2. 最终接入方式

Prometheus 告警源统一使用以下 webhook 路径：

```text
/api/v1/alerts/api/source/{source_id}/webhook/
```

示例：

- source_id 为 prometheus：

```text
https://alerts.example.com/api/v1/alerts/api/source/prometheus/webhook/
```

- source_id 为 prometheus-prod-sh：

```text
https://alerts.example.com/api/v1/alerts/api/source/prometheus-prod-sh/webhook/
```

认证方式：

- Header 名：SECRET
- Header 值：BK-Lite 告警源中配置的 secret

## 3. 实施前准备

### 3.1 BK-Lite 侧准备项

上线前在 BK-Lite 中准备一条 Prometheus 告警源，记录以下信息：

- source_id
- secret
- webhook_url

建议规则：

- 每个 Prometheus / Alertmanager 实例使用一个独立 source_id
- 每个 source_id 使用独立 secret
- source_id 使用可识别命名，例如 prometheus-prod-sh、prometheus-staging-bj

### 3.2 参数获取方式

推荐通过接口获取最终接入参数：

```text
GET /api/v1/alerts/api/alert_source/{id}/integration-guide/
```

重点看返回值：

- webhook_url
- headers.SECRET

上线时以接口返回值为准，不要手工拼路径。

## 4. Prometheus 侧实施步骤

### 4.1 规则文件

规则文件示例：

```yaml
groups:
  - name: bk-lite-cpu-rules
    rules:
      - alert: HighCpuUsage
        expr: cpu_usage_average > 10
        for: 1m
        labels:
          severity: warning
          service: ops-demo
          cluster: prod-sh
        annotations:
          summary: CPU usage is high
          description: cpu_usage_average is above 10, current value is {{ $value }}
```

实施要求：

- alertname 必须稳定
- instance、job、service、cluster 建议尽量带齐
- firing 和 resolved 阶段的关键标签保持一致

### 4.2 Prometheus 主配置

Prometheus 主配置中必须确认以下内容：

```yaml
rule_files:
  - /etc/prometheus/rules/*.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093
```

实施检查点：

- 规则文件目录已被加载
- Prometheus 已指向 Alertmanager

## 5. Alertmanager 侧实施步骤

### 5.1 最终配置模板

下面示例假设：

- BK-Lite 域名：alerts.example.com
- source_id：prometheus-prod-sh
- secret：your_prometheus_secret

```yaml
route:
  receiver: bk-lite-prometheus
  group_by:
    - alertname
    - instance
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: bk-lite-prometheus
    webhook_configs:
      - url: https://alerts.example.com/api/v1/alerts/api/source/prometheus-prod-sh/webhook/
        send_resolved: true
        http_config:
          http_headers:
            SECRET:
              values:
                - your_prometheus_secret
```

### 5.2 实施时必须确认

1. url 中的 source_id 与 BK-Lite 中保存的一致
2. SECRET 值与 BK-Lite 告警源中的 secret 一致
3. send_resolved 必须为 true
4. Alertmanager 配置修改后已 reload 或 restart

## 6. 手工验证步骤

### 6.1 先做 CURL 打通

在正式切 Alertmanager 前，先用 CURL 验证 webhook 是否可达。

```bash
curl --location 'https://alerts.example.com/api/v1/alerts/api/source/prometheus-prod-sh/webhook/' \
  --header 'SECRET: your_prometheus_secret' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "receiver": "bk-lite-prometheus",
    "status": "firing",
    "commonLabels": {
      "alertname": "HighCpuUsage",
      "severity": "warning",
      "service": "ops-demo",
      "cluster": "prod-sh"
    },
    "commonAnnotations": {
      "summary": "CPU usage is high"
    },
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "instance": "node-1",
          "job": "node-exporter"
        },
        "annotations": {
          "description": "cpu_usage_average is above 10, current value is 15"
        },
        "startsAt": "2026-04-27T10:00:00Z",
        "endsAt": "2026-04-27T11:00:00Z"
      }
    ]
  }'
```

判定标准：

- HTTP 返回 200
- BK-Lite 中能看到对应事件

### 6.2 再做真实告警验证

1. 让 cpu_usage_average > 10
2. 在 Prometheus 页面确认规则进入 Pending / Firing
3. 在 Alertmanager 页面确认 webhook 已发送
4. 在 BK-Lite 中确认事件已生成

### 6.3 恢复验证

1. 让 cpu_usage_average 回到阈值以下
2. 确认 Alertmanager 发送 resolved
3. 在 BK-Lite 中确认 recovery 事件已生成

## 7. 字段对应关系

Prometheus 进入 BK-Lite 后，关键字段对应关系如下：

| BK-Lite 字段 | 上游来源 |
| --- | --- |
| title | alertname 或 alertname(resource_name) |
| description | annotations.description -> annotations.summary -> alertname |
| level | severity |
| item | alertname |
| resource_name | instance -> pod -> node -> service -> job |
| service | labels.service -> labels.job |
| location | labels.cluster -> labels.region |
| action | firing -> created, resolved -> recovery |
| external_id | external_id 或自动生成 |

实施关注点：

- alertname 和 instance 等关键标签不要在恢复时变化
- 否则 external_id 可能变化，导致恢复闭环失败

## 8. 快速排障

### 8.1 返回 Missing source_id

原因：

- URL 中没有正确带上 source_id

处理：

- 确认使用的是 /api/source/{source_id}/webhook/

### 8.2 返回 Invalid secret

原因：

- Header 中 SECRET 错误

处理：

- 对照 BK-Lite 告警源配置重新填写

### 8.3 firing 有，recovery 没有

原因：

- send_resolved 没开
- 或 resolved 阶段关键标签变化导致 external_id 不一致

处理：

- 确认 send_resolved=true
- 确认 alertname、instance 等关键标签稳定

## 9. 实施结论

Prometheus 实施只需要记住三件事：

1. 统一使用 /api/source/{source_id}/webhook/
2. Header 固定传 SECRET
3. Alertmanager 必须 send_resolved=true
