# 外部服务订阅 BK-Lite 通知

BK-Lite 的 Event Publish 通道会把通知发布到 Core NATS。外部服务以部署时生成的通知 NKey 身份订阅通知主题，不需要加入 BK-Lite 的 Docker 网络。

## 接入前提

部署管理员需要以受控方式向外部服务注入以下配置；不要把 Seed 写进源码、镜像、日志或仓库。

| 环境变量 | 说明 |
| --- | --- |
| `NATS_URL` | NATS 对外地址，例如 `tls://nats.example.com:4222`。 |
| `NATS_NOTIFICATIONS_NKEY_SEED` | 部署生成的通知 NKey Seed；这是私密凭据。 |
| `NATS_TLS_CA_FILE` | 用于验证 NATS 服务端证书的 CA 文件路径。 |
| `NATS_SUBJECT` | 订阅范围；通常为 `bklite.notifications.>`。 |

通知 NKey 由部署流程写入部署目录的 `.env` 与持久化的 `common.env`。其中只有 Seed 应注入订阅服务；公钥 `NATS_NOTIFICATIONS_NKEY_PUB` 只用于 NATS 服务端授权配置。

若 NATS 使用自签名或内部 CA，请一并安全分发 CA 证书。客户端连接地址必须与服务端证书的 SAN 匹配；不要通过关闭 TLS 证书校验来规避地址或证书配置问题。

## 主题

BK-Lite 的 Event Publish 通道使用以下主题：

```text
bklite.notifications.channel.<通知主题标识>
```

未填写通知主题标识时，末段为 BK-Lite 通道 ID。例如通道 ID 为 `42` 时：

```text
bklite.notifications.channel.42
```

订阅全部通知：

```text
bklite.notifications.>
```

订阅一个特定通道：

```text
bklite.notifications.channel.customer-alerts
```

## 消息协议

消息体为 UTF-8 JSON，当前 `schema_version` 为 `1`：

```json
{
  "schema_version": 1,
  "message_id": "106be954-bb21-4f00-b7f8-ad4458e4b8a2",
  "event_type": "notification",
  "source": "bk-lite",
  "channel_id": 123,
  "org_ids": [1],
  "occurred_at": "2026-08-12T03:10:20.123456+00:00",
  "title": "磁盘空间告警",
  "body": "node-01 可用空间低于 10%",
  "data": {
    "message": "node-01 可用空间低于 10%",
    "team": 1,
    "user_ids": ["admin", "ops"]
  },
  "test": false
}
```

- `message_id` 是单次发布的 UUID，可用于关联 BK-Lite 调用返回值和订阅服务日志。
- `source` 固定为 `bk-lite`，表示发布系统，不表示触发通知的内部模块。
- `data` 保留调用通道时传入的结构化内容；接收方应将未识别字段视为可扩展字段。
- `test=true` 表示由通道配置页的“测试”操作发出，不应触发生产业务动作。

接收方应以 `schema_version` 选择解析逻辑，并在无法识别将来版本时记录错误、隔离该消息，而非按假设继续执行。

## Python 接收示例

安装依赖：

```bash
pip install 'nats-py==2.9.0' 'nkeys==0.2.1'
```

以下示例使用环境变量连接、订阅并记录消息。生产处理器应替换 `handle_notification`，并避免将包含个人信息或业务正文的完整消息长期写入日志。

```python
import asyncio
import json
import logging
import os
import ssl

import nats


logger = logging.getLogger("notification_subscriber")


async def handle_notification(subject: str, event: dict) -> None:
    # 用 message_id 作为业务侧去重键；处理必须能安全重试。
    logger.info("received notification message_id=%s subject=%s", event["message_id"], subject)


async def main() -> None:
    tls_context = ssl.create_default_context(cafile=os.environ["NATS_TLS_CA_FILE"])
    client = await nats.connect(
        servers=[os.environ["NATS_URL"]],
        nkeys_seed_str=os.environ["NATS_NOTIFICATIONS_NKEY_SEED"],
        tls=tls_context,
        name="external-notification-subscriber",
    )

    async def on_message(message):
        try:
            event = json.loads(message.data.decode("utf-8"))
            if event.get("schema_version") != 1:
                raise ValueError(f"unsupported schema_version: {event.get('schema_version')!r}")
            await handle_notification(message.subject, event)
        except Exception:
            logger.exception("notification handling failed subject=%s", message.subject)

    await client.subscribe(os.getenv("NATS_SUBJECT", "bklite.notifications.>"), cb=on_message)
    await client.flush()
    logger.info("notification subscriber is ready")
    await asyncio.Event().wait()


asyncio.run(main())
```

## 交付与重试边界

当前通道是 Core NATS 发布：BK-Lite 返回成功表示 NATS 已接受发布请求，不表示外部订阅服务已经收到或完成处理。

因此订阅服务应：

1. 用 `message_id` 实现业务处理去重；
2. 为连接中断和进程重启准备重连与恢复策略；
3. 将业务处理失败记录为可观测错误，并由自身队列或存储实现补偿；
4. 若需要平台可验证的持久化、确认与重放语义，应单独设计 JetStream Stream/Consumer、授权范围和迁移方案，而不是假定当前主题具备这些能力。
