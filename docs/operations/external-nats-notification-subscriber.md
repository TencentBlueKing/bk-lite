# 外部服务订阅 BK-Lite 通知

BK-Lite 的 Event Publish 通道会把通知发布到 Core NATS。外部服务以部署时生成的通知 NKey 身份订阅通知主题，不需要加入 BK-Lite 的 Docker 网络。

## 接入前的准备事项

### 步骤一：创建 NATS 外部通知渠道

1. 进入“系统管理”，点击顶部导航栏的“通知渠道”。
2. 选择“NATS 通道”。
3. 点击右上角“添加”，进入 NATS 配置表单。
4. 将“通知投递目标”设为“发布给外部订阅方”，填写“通知主题标识”及其他必填项后，点击“确认”。
配置字段及跨模块列表投影契约见[《NATS 通道「支持通知人」配置契约》](../design/product-decisions/nats-channel-supports-notify-person.md)。


### 步骤二：在 BK-Lite 其他模块中接入该渠道

以监控模块举例
1. 进入“监控”，点击顶部导航栏的“事件”。
2. 选择“策略”。
3. 点击右上角添加，进入添加策略配置表单。
4. 完成前三步策略配置后，在第四步启用通知配置，并选择在步骤一创建的NATS通道，保存即可
业务模块选择该通道时，应按上述契约自行决定是否组装通知人；系统管理不会在发送侧强制校验。


## 接入前提

对接服务需要从 BK-Lite 部署环境取得以下连接信息。后文 Python 与 Docker Compose 示例用同名环境变量读取这些值，仅为便于对照；对接服务是用环境变量注入、配置文件，还是写在代码里，由对接服务开发人员自行决定。

以下路径以默认部署目录 `/opt/bk-lite` 为例；若部署时指定了其他目录，请将前缀替换为实际部署目录。

| 配置项 | 用途 | 在 BK-Lite 中的来源 |
| --- | --- | --- |
| `NATS_URL` | NATS 连接地址。 | 外部访问地址由 `/opt/bk-lite/.env` 中的 `HOST_IP` 与默认端口 `4222` 组成，即 `tls://<HOST_IP>:4222`。若使用域名替代 IP，该域名必须指向 NATS 宿主机并已写入服务端证书 SAN；加入 BK-Lite 容器网络时的内部地址见后文“部署参考”。 |
| `NATS_NOTIFICATIONS_NKEY_SEED` | 以通知 NKey 身份认证；这是私密凭据。 | 读取 `/opt/bk-lite/common.env` 中的 `export NATS_NOTIFICATIONS_NKEY_SEED=...`；部署生成的 `/opt/bk-lite/.env` 也会有同名值。使用 Seed 值本身，不要用公钥代替。 |
| `NATS_TLS_CA_FILE` | 用于验证 NATS 服务端证书的 CA。 | 文件位于 `/opt/bk-lite/conf/certs/ca.crt`。对接服务需要能读到这份 CA；若以文件路径方式使用，填写的是对接服务内部的绝对路径（例如 `/run/secrets/bk-lite-nats-ca.crt`），不是 BK-Lite 主机上的原路径。 |
| `NATS_SUBJECT` | 限定接收的通知范围。 | 默认使用 `bklite.notifications.>`，接收全部 BK-Lite 通知。若业务只接收某一通道，在 BK-Lite 的“系统管理 → 通知渠道”中创建 Event Publish 通道时记录必填的“通知主题标识”，设置为 `bklite.notifications.channel.<标识>`。 |

通知 NKey 的公钥 `NATS_NOTIFICATIONS_NKEY_PUB` 只用于 NATS 服务端授权配置，不是接入变量，也不能代替 Seed 建立客户端身份。默认部署会把该公钥写入 NATS 授权，允许该身份对 `bklite.notifications.>` 发布和订阅；因此对接服务默认订阅 `bklite.notifications.>` 即可接收全部 Event Publish 通知。

若 NATS 使用自签名或内部 CA，请一并安全分发 CA 证书。客户端连接地址必须与服务端证书的 SAN 匹配；不要通过关闭 TLS 证书校验来规避地址或证书配置问题。

## 订阅协议

### 主题

BK-Lite 的 Event Publish 通道使用以下主题：

```text
bklite.notifications.channel.<通知主题标识>
```

订阅全部通知：

```text
bklite.notifications.>
```

订阅一个特定通道：

```text
bklite.notifications.channel.customer-alerts
```

### 消息格式

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

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | 整数 | 协议版本，当前固定为 `1`。接收方应按版本选择解析逻辑。 |
| `message_id` | 字符串（UUID） | 单次发布标识，可用于关联 BK-Lite 调用返回值和订阅服务日志。同一业务事件重新发布会生成新值，不能单独作为跨发布重试的业务幂等键。 |
| `event_type` | 字符串 | 事件类型，默认值为 `notification`；接收方应允许后续增加其他值。 |
| `source` | 字符串 | 当前固定为 `bk-lite`，表示发布系统，不表示触发通知的内部模块。 |
| `channel_id` | 整数 | 发送该消息的 BK-Lite 通知渠道 ID。配置页测试消息的值为 `0`，正式消息为已保存渠道的实际 ID；该字段不参与 Subject 生成。 |
| `org_ids` | 整数数组 | 该通知渠道所属的组织 ID 列表；测试消息可能为空数组。 |
| `occurred_at` | 字符串 | BK-Lite 生成消息的 UTC 时间，使用带时区的 ISO 8601 格式。 |
| `title` | 字符串 | 调用方传入的通知标题；允许为空字符串。 |
| `body` | 字符串 | 从调用内容的 `message` 字段生成的通知正文。 |
| `data` | 对象 | 调用通道时传入的结构化内容。其内部字段取决于调用模块，接收方应只读取需要的字段，并忽略未识别字段。 |
| `test` | 布尔值 | `true` 表示由通道配置页的“测试”操作发出，不应触发生产业务动作。 |

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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("notification_subscriber")


async def handle_notification(subject: str, event: dict) -> None:
    # message_id 用于关联单次发布；跨发布重试需使用业务数据中的稳定标识。
    logger.info("received notification message_id=%s subject=%s", event["message_id"], subject)


async def main() -> None:
    async def on_disconnected() -> None:
        logger.warning("NATS connection lost; waiting for reconnect")

    async def on_reconnected() -> None:
        logger.info("NATS connection restored server=%s", client.connected_url)

    async def on_closed() -> None:
        logger.error("NATS connection closed")

    tls_context = ssl.create_default_context(cafile=os.environ["NATS_TLS_CA_FILE"])
    client = await nats.connect(
        servers=[os.environ["NATS_URL"]],
        nkeys_seed_str=os.environ["NATS_NOTIFICATIONS_NKEY_SEED"],
        tls=tls_context,
        name="external-notification-subscriber",
        disconnected_cb=on_disconnected,
        reconnected_cb=on_reconnected,
        closed_cb=on_closed,
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

## 接入验证

1. 按所选部署方式启动订阅服务。使用本文后续的 Docker Compose 示例时，执行 `docker compose up -d`。
2. 查看订阅服务日志，确认出现 `notification subscriber is ready`；这只表示连接和订阅已建立。使用 Docker Compose 时，可执行 `docker compose logs -f notification-subscriber`。
3. 在 BK-Lite 的“系统管理 → 通知渠道”中打开已配置的 Event Publish 通道，点击“测试”。
4. 确认页面提示测试成功，同时订阅服务日志出现 `received notification`。测试消息应满足以下条件：
   - Subject 为 `bklite.notifications.channel.<通知主题标识>`；
   - `schema_version` 为 `1`；
   - `test` 为 `true`；
   - 如需追踪单次测试，可在浏览器开发者工具的 Network 面板中查看测试请求响应，并确认其中的 `message_id` 与订阅服务日志一致。

仅出现 `notification subscriber is ready` 不能证明消息已经送达；页面提示测试成功也只表示 BK-Lite 已将消息发布给 NATS。必须同时观察到订阅服务的接收日志，才表示本次端到端测试通过。

## 部署参考

外部订阅服务的部署方式不限，可运行在容器、虚拟机或物理主机上；推荐使用 Docker Compose 部署，以下以 Docker Compose 为例。无论采用何种部署方式，均使用相同的 NKey、CA 和主题，区别只在网络可达性及 `NATS_URL`。

### 选择连接位置

| 部署方式 | 适用情况 | `NATS_URL` | 网络与运维影响 |
| --- | --- | --- | --- |
| 加入 BK-Lite 容器网络 | 订阅服务与 BK-Lite 运行在同一台 Docker 主机，且允许其成为平台内部服务。 | `tls://nats:4222` | 服务需加入 BK-Lite 的 `bklite-prod` 网络，可通过 NATS 服务名 `nats` 访问，无需使用宿主机 IP 或暴露额外端口。容器生命周期与网络配置需要随 BK-Lite 部署一起维护。 |
| 不加入 BK-Lite 容器网络 | 订阅服务运行在另一台主机、独立 Compose 网络，或希望与 BK-Lite 网络隔离。 | `tls://<HOST_IP>:4222`，其中 `HOST_IP` 读取自 `/opt/bk-lite/.env`。 | 通过宿主机已发布的 `4222` 端口访问；必须确认防火墙/安全组允许来源地址访问，并且 `<HOST_IP>` 或改用的域名在 NATS 服务端证书 SAN 中。此方式不依赖 BK-Lite 的 Docker 网络，推荐用于外部业务服务。 |

不要在已加入 `bklite-prod` 网络的容器中使用宿主机 IP，也不要在独立网络的容器中使用 `nats`：前者会绕开容器服务发现，后者无法解析 BK-Lite 内部服务名。

### 不加入 BK-Lite 容器网络（推荐）

外部订阅服务通常以独立 Docker 容器运行。以下示例采用推荐的“**不加入 BK-Lite 容器网络**”方式：将 `ca.crt` 放在与 `compose.yaml` 同级的 `certs/ca.crt`，并将 `/opt/bk-lite/.env` 中 `NATS_NOTIFICATIONS_NKEY_SEED` 的值复制到该部署目录的 `.env` 中。该 `.env` 仅用于部署环境注入，必须限制文件权限并加入 `.gitignore`。示例中的镜像应替换为实际业务服务镜像。

```dotenv
NATS_NOTIFICATIONS_NKEY_SEED=<复制 /opt/bk-lite/.env 中的同名值>
```

```yaml
services:
  notification-subscriber:
    image: your-registry/notification-subscriber:1.0.0
    restart: unless-stopped
    environment:
      NATS_URL: tls://<HOST_IP>:4222
      NATS_NOTIFICATIONS_NKEY_SEED: ${NATS_NOTIFICATIONS_NKEY_SEED:?必须配置通知 NKey Seed}
      NATS_TLS_CA_FILE: /run/bk-lite-nats/ca.crt
      NATS_SUBJECT: bklite.notifications.>
    volumes:
      - ./certs/ca.crt:/run/bk-lite-nats/ca.crt:ro
```

### 加入 BK-Lite 容器网络

只有订阅服务与 BK-Lite 运行在**同一台 Docker 主机**时，才可以加入该网络：将前一示例中的 `NATS_URL` 改为 `tls://nats:4222`，并在同一个 `compose.yaml` 中增加以下配置。`external: true` 表示复用 BK-Lite 已创建的网络，而不是创建同名的新网络。

```yaml
services:
  notification-subscriber:
    networks:
      - bklite-prod

networks:
  bklite-prod:
    external: true
    name: bklite-prod
```

执行 `docker compose up -d` 后，订阅容器会加入 `bklite-prod` 网络，因而可以通过服务名 `nats` 访问 BK-Lite NATS。服务显式配置 `networks` 后不会自动加入 Compose 的默认网络；若还需要访问自身部署中的其他容器，应将相应网络也列入该服务的 `networks`。若 `bklite-prod` 网络不存在，说明 BK-Lite 尚未启动或当前 Docker 主机不正确；不要手动新建该网络来替代。

## 运行与可靠性

### 常见失败

| 现象 | 检查项 |
| --- | --- |
| 无法解析 `nats` | 订阅容器没有加入 `bklite-prod`，或不应使用内部服务名；独立网络部署应改用 `tls://<HOST_IP>:4222`。 |
| 连接 `4222` 超时或被拒绝 | 检查 NATS 宿主机端口映射、防火墙和安全组是否允许订阅服务来源地址访问。 |
| TLS 提示证书对地址无效 | 检查 `NATS_URL` 中的 IP/域名是否存在于服务端证书 SAN，并确认挂载的是 BK-Lite 部署使用的 CA。不要关闭证书校验。 |
| NKey 认证失败或权限不足 | 确认注入的是 `NATS_NOTIFICATIONS_NKEY_SEED` 的 Seed 值，而非 `NATS_NOTIFICATIONS_NKEY_PUB`；同时确认订阅主题位于授权范围内。 |
| 已显示订阅就绪但收不到测试消息 | 核对通道的“通知主题标识”和 `NATS_SUBJECT`，并确认测试消息的 `test` 字段。 |

### 交付与重试边界

当前通道是 Core NATS 发布：BK-Lite 返回成功表示消息已写入当前 NATS 连接，不表示外部订阅服务已经收到或完成处理。当前没有 JetStream 持久化、消费者确认或平台侧重放机制；订阅服务离线或重连期间发布的消息不会在其恢复后自动补发。

因此订阅服务应：

1. 用 `message_id` 关联单次发布和防止同一消息被重复处理；若需要跨发布重试去重，应从 `data` 中选择或补充稳定的业务标识；
2. 监听连接中断、重连和关闭事件，并将连接状态接入自身健康检查和监控；自动重连只能恢复连接与订阅，不能找回离线期间的消息；
3. 在收到消息后先写入自身的持久队列或存储，再执行可能失败的业务动作；业务处理失败由订阅服务记录、重试和补偿；
4. 若需要平台可验证的持久化、确认与重放语义，应单独设计 JetStream Stream/Consumer、授权范围和迁移方案，而不是假定当前主题具备这些能力。
