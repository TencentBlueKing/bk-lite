# 云资源变化事件实施文档

状态: 已确认并实施（2026-11-26）。第 7 节报文已通过 webhook 入库测试。

规格: `specs/changes/alert-cloud-resource-events/spec.md`

## 1. 文档用途

本文面向实施、运维和上线测试人员，用于把阿里云 EventBridge、腾讯云事件总线的资源变化事件接入告警中心。

本文只写实施要做的事。

- 告警中心要准备什么
- 阿里云、腾讯云控制台要填什么
- 地址、请求头和字段怎么对应
- 上线后怎么确认链路通了
- 不通时先看哪里

平台版本还没带上这两张集成源时，先不要到云上建规则。

## 2. 最终接入方式

两张内置源，各一条地址。`source_id` 固定为下面两个值。

| 集成源 | source_id | 回调路径 |
|---|---|---|
| 阿里云 EventBridge | `aliyun_eventbridge` | `/api/v1/alerts/api/source/aliyun_eventbridge/webhook/` |
| 腾讯云事件总线 | `tencent_eventbus` | `/api/v1/alerts/api/source/tencent_eventbus/webhook/` |

把平台对外地址接在路径前面。例如平台地址是 `https://alerts.example.com` 时，阿里云回调地址是：

```text
https://alerts.example.com/api/v1/alerts/api/source/aliyun_eventbridge/webhook/
```

认证：

- 请求头名是 `SECRET`
- 请求头值是接入说明里、所选组织揭示出来的组织密钥
- 不要填告警源上的源级总密钥。除 SNMP Trap 外，源级总密钥会被拒绝，回执 403

腾讯云控制台如果不能加请求头，同一枚组织密钥可以放在查询参数 `secret` 上。阿里云仍用请求头。

```text
https://alerts.example.com/api/v1/alerts/api/source/tencent_eventbus/webhook/?secret=组织密钥
```

上线时以接入说明接口返回的地址和密钥为准，不要手拼。

```text
GET /api/v1/alerts/api/alert_source/{id}/integration-guide/
```

看 `webhook_url`、`headers.SECRET` 和 `examples`。`examples` 的正文是云厂商原始 JSON。指南页展示的是这个接口，不是通用 REST 上报示例。

## 3. 实施前准备

### 3.1 告警中心

1. 升级到带这两张内置源的版本，并完成告警源初始化。
2. 打开集成源概览，确认出现「阿里云 EventBridge」和「腾讯云事件总线」。
3. 进入对应源的接入说明，选择事件要归属的组织，复制回调地址和组织密钥。
4. 核对只读的上报字段映射和默认事件类型。页面不能改这张目录。改目录要发版。

一个组织一条云侧规则。该组织有多个云账号时，可以共用这一条地址和这一枚密钥。事件上的账号用来区分。不同组织要各建一条云侧规则，并使用各自的组织密钥。

### 3.2 告警策略

平台不会自动建策略。回调打通后，再建一条即时策略。

- 匹配条件选这张集成源
- 通知通道用现有通道
- 窗口策略也能匹配，但要等窗口结束才告警。云事件建议用即时策略

没有这条策略时，发生事件只出现在事件列表，不会通知。

## 4. 阿里云侧

在账号的默认事件总线新建规则，投递目标选 HTTP。方法用 POST，地址用第 2 节的阿里云地址，请求头加 `SECRET`。

事件模式只勾选下面这些类型。同一件事不要再勾选不带 `CloudMonitor` 的原生事件，否则一次重启会推两条。平台对原生重复类型会跳过，但仍占用云上投递次数。

过程态要带上该类型实际有的阶段。阶段包括 `Executing`、`Executed`、`Failed`、`Avoided`、`Canceled`、`Scheduled`、`Inquiring`。

| 类别 | 类型 |
|---|---|
| 实例故障 | `InstanceFailure.Reboot` |
| 系统错误 | `SystemFailure.Reboot`、`Stop`、`Redeploy`、`Delete` |
| 系统维护 | `SystemMaintenance.Reboot`、`Stop`、`Redeploy`，以及隔离坏盘、重新初始化坏盘、重启并处理坏盘 |
| 磁盘 | `Disk[ErrorDetected]`、`Disk[Stalled]` |

另外只勾这四条没有过程态的原生事件。它们进事件列表，不建告警。

- `ecs:Instance:StateChange`
- `ecs:Instance:PreemptibleInstanceInterruption`
- `ecs:Instance:LiveMigrationAcrossDDH`
- `ecs:Disk:OverduePaymentRelease`

不要勾选 ActionTrail 和 Config。官方类型说明见 [云服务器 ECS 事件](https://help.aliyun.com/zh/eventbridge/user-guide/ecs-events/)。

## 5. 腾讯云侧

在事件总线新建事件规则。目标使用接口回调，不要选短信或电话。地址用第 2 节的腾讯云地址。能加请求头就加 `SECRET`。不能加请求头就用带 `secret` 查询参数的地址。

规则只匹配 CVM。监控告警模板和 CloudEvent 都可以。平台按报文形状分辨。CVM 的实例字段是 `unInstanceId`。CloudEvent 的资源 ID 用 `subject`。

不要把 DDoS 高防打到这条地址。那种包会被拒绝，回执 400，云上会重试。其它云产品在目录加上产品名和实例字段之前也会被跳过，回执仍是 200。官方说明见 [消息推送目标](https://cloud.tencent.com/document/product/248/87560)。事件总线默认每天触达 10000 次，这是腾讯云侧限额。

## 6. 字段怎么落

实施核对时看事件列表和原始数据，不看云控制台原文。

| 要核对的内容 | 事件上的位置 |
|---|---|
| 云厂商 | 来源列，分别是两张集成源的名称 |
| 账号 | 内容，以及原始数据 `labels.account` |
| 地域 | 内容 |
| 资源 ID | 标题，以及资源 ID |
| 事件类型 | 指标名 |
| 发生、恢复、无状态 | 内容里的这三个词 |
| 云厂商原文 | 原始数据里的 `original` |
| 已纳管实例 | `cmdb_id`。没有或不唯一时为空 |

标题形如「实例计划重启 i-bp1...」。磁盘事件的资源 ID 是磁盘 ID。关联 CMDB 时用父实例去对云主机。

## 7. 上线验证

先用 CURL 打平台，再切云上规则。下面的密钥换成所选组织的组织密钥。

### 7.1 阿里云发生

```bash
curl --location 'https://alerts.example.com/api/v1/alerts/api/source/aliyun_eventbridge/webhook/' \
  --header 'SECRET: 组织密钥' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "id": "delivery-1",
    "source": "acs.ecs",
    "type": "ecs:CloudMonitor:Instance[SystemFailure.Reboot:Executing]",
    "time": "2026-11-26T09:00:00Z",
    "aliyunaccountid": "1234567890",
    "aliyunregionid": "cn-hangzhou",
    "data": {
      "eventId": "e-reboot-1",
      "eventStatus": "Executing",
      "instanceId": "i-test-1"
    }
  }'
```

期望：HTTP 200。事件列表有一条。标题含 `i-test-1`。内容含「发生」和 `cn-hangzhou`。级别是严重。已有匹配的即时策略时生成一条告警。

把同一条再推一次。期望仍是 HTTP 200，事件列表不增加第二行。

### 7.2 阿里云恢复

`type` 末尾改为 `Executed`，`data.eventId` 仍是 `e-reboot-1`，`data.eventStatus` 改为 `Executed`。

期望：HTTP 200。内容含「恢复」。第 7.1 节那条未关闭告警被关掉。不新开告警。

### 7.3 无状态

`type` 改为 `ecs:Instance:StateChange`，`data` 里带 `resourceId`。

期望：HTTP 200。内容含「无状态」。事件列表能看到。不建告警。

### 7.4 目录外和错误密钥

`type` 改为 `ecs:Snapshot:SnapshotDeleted`。期望 HTTP 200，事件列表没有这条。

去掉请求头，或填源级总密钥。期望 HTTP 403，不入库。

报文改成 `{"hello":"world"}`。期望 HTTP 400，不入库。

### 7.5 腾讯云

```bash
curl --location 'https://alerts.example.com/api/v1/alerts/api/source/tencent_eventbus/webhook/' \
  --header 'SECRET: 组织密钥' \
  --header 'Content-Type: application/json' \
  --data-raw '{
    "sessionId": "sess-cvm-1",
    "alarmStatus": "1",
    "alarmType": "event",
    "alarmObjInfo": {
      "region": "ap-guangzhou",
      "dimensions": {"unInstanceId": "ins-test-1"}
    },
    "alarmPolicyInfo": {
      "policyName": "cvm-reboot",
      "conditions": {"productName": "cvm", "eventName": "guest_reboot"}
    },
    "firstOccurTime": "2026-11-26 17:00:00"
  }'
```

期望：HTTP 200。标题含 `ins-test-1`。内容含「发生」。`firstOccurTime` 按东八区入库。把 `alarmStatus` 改为 `0` 后再推，同一条告警恢复。产品不是 CVM 时返回 200 且不入库。

### 7.6 CMDB

组织里恰好有一台 `resource_id` 为 `i-test-1` 的阿里云 ECS 时，第 7.1 节事件的 `cmdb_id` 是这台实例的 UUID。没有这台机器，或同一组织有两台相同 `resource_id` 时，`cmdb_id` 为空，事件仍在。

## 8. 出问题时先看哪里

| 现象 | 先查 |
|---|---|
| HTTP 403 | 用的是不是组织密钥。源级总密钥会被拒绝 |
| HTTP 400 | 报文是不是两种已知形状之一。DDoS 高防属于这一类 |
| HTTP 200 但列表没有 | 事件类型不在默认目录。日志里有源、类型和跳过原因，没有原文 |
| 推了两次出现两条 | 两次的账号或业务 ID 不同。恢复靠「账号 + 业务 ID」对齐 |
| 有事件没有告警 | 动作是不是无状态，有没有即时策略选中这张源，事件有没有被屏蔽 |
| 恢复没有关掉告警 | 恢复报文的业务 ID 是否和第 7 节要求的字段相同。对不上时只改目录 |
| `cmdb_id` 为空 | 该组织里是不是恰好一台，属性是不是 `resource_id`。磁盘看的是父实例，不是磁盘 ID |
| 时间偏了 8 小时 | 腾讯云 `firstOccurTime` 没有时区，按东八区解释。带时区的阿里云时间按其偏移解释 |

第一条真实的阿里云产生和恢复、腾讯云 CVM 未恢复和恢复打到平台后，核对业务 ID 是否两边相同、状态 `0` 是否表示恢复。对不上时改目录后再给客户启用规则，不改回调地址。
