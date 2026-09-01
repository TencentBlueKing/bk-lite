# Stargazer JetStream 生产实施手册

Date: 2026-08-28

适用范围：保留现有 `metrics.*` Subject 和数据格式，将 Stargazer 的发布方式从 Core NATS
灰度切换到方案 B 的 JetStream 异步 `PubAck` 发布窗口。本文面向实施人员，不涉及 Telegraf
ACK 改造或 Metric Ingester。

## 1. 上线结论

线上按以下顺序实施：

1. 检查 NATS 已启用 JetStream；
2. 查找当前覆盖 `metrics.*` 的 JetStream Stream，存在则直接复用；
3. 给一个 Stargazer 实例配置 JetStream 开关并滚动重启；
4. 完成一个真实采集周期的验证；
5. 再逐个放开剩余 Stargazer 实例。

本次不新增 Subject，Stargazer 仍发布 `metrics.network`、`metrics.sangforscp`、
`metrics.vmware` 等现有 Subject。优化来自 `publish_async + PubAck`，与 Subject 改名无关。
只有查不到任何覆盖 `metrics.*` 的 Stream 时才创建 `CMDB_METRICS`。Stargazer 不会自动创建或
修改 Stream，避免采集进程持有 NATS 管理权限。

> `PubAck` 只表示消息已被 JetStream 持久接纳，不代表 Telegraf 已经写入
> VictoriaMetrics。实施验收需要分别检查 JetStream 发布和最终实例数据。

## 2. 变更参数

Stargazer 必须配置：

```env
NATS_METRICS_JETSTREAM_ENABLED=true
NATS_JS_STREAM_NAME=<当前覆盖 metrics.* 的 Stream 名称>
PUBLISH_WORKERS=4
```

注意，正确的开关名是 `NATS_METRICS_JETSTREAM_ENABLED`，不是
`NATS_JS_PUBLISH_ENABLED`。未配置时默认启用；显式配置为 `false` 会触发启动配置校验失败，生产
不再提供 Core NATS metrics fallback。`NATS_JS_STREAM_NAME` 必须使用现场查询到的现有 Stream
名称；只有新建兜底 Stream 时才填写 `CMDB_METRICS`。

以下参数已有代码默认值，首期建议保持默认：

```env
NATS_JS_PUBLISH_MAX_PENDING=256
NATS_JS_PUBLISH_MAX_PENDING_BYTES=33554432
NATS_METRICS_PENDING_SIZE_BYTES=34603008
NATS_JS_PUBACK_TIMEOUT=30
NATS_JS_PUBLISH_MAX_ATTEMPTS=2
NATS_MAX_RECONNECT_ATTEMPTS=-1
NATS_METRICS_READINESS_TIMEOUT=2
NATS_DRAIN_TIMEOUT_SECONDS=5
```

`NATS_METRICS_PENDING_SIZE_BYTES` 不得小于 JetStream 字节窗口；当前默认额外保留 1 MiB 协议
余量。消息数和字节额度在创建 PubAck Task 前全局获取，`PUBLISH_WORKERS=4` 不会把 256 窗口放大
为 1024 个 Task。

不要通过不断增加 PubAck 超时或无限重试掩盖 NATS 磁盘、网络或集群故障。

## 3. 实施前检查

### 3.1 变更窗口和备份

- 确认至少保留一个未开启 JetStream 的 Stargazer 实例，作为灰度回退；
- 记录当前 Stargazer 镜像版本、环境变量和实例数；
- 记录 NATS 节点数、版本、可用磁盘、TLS/认证方式；
- 记录 Telegraf 当前 `metrics.*` 消费是否正常；
- 禁止把 NATS 用户名、密码、Token 或证书内容写进实施记录和命令历史。

### 3.2 选择 NATS 管理上下文

以下命令假设实施机已经配置了安全的 NATS CLI context：

```bash
nats context select <生产管理上下文>
nats context info
```

不要把密码直接写在 `--password` 参数中。若现场没有 NATS CLI context，应使用部署系统或
临时凭据文件注入认证信息，并在变更结束后回收。

### 3.3 检查 JetStream

```bash
nats account info
nats stream ls
```

验收点：

- 命令能返回 JetStream account/stream 信息；
- JetStream 存储目录可写且磁盘空间充足；
- 三节点集群应全部在线且无明显 replica lag；
- 单节点环境只能配置 1 个副本，三节点生产集群建议配置 3 个副本。

任何一项不满足都应停止上线，不要先开启 Stargazer 开关。

## 4. 查找并复用现有 Metrics Stream

### 4.1 查找当前归属

使用两个真实 Subject 样例查询，避免只根据 Stream 名称猜测：

```bash
nats stream find metrics.network
nats stream find metrics.sangforscp
nats stream ls
```

分支处理：

- 两个 Subject 都命中同一个 Stream：记录该 Stream 名称，进入 4.2；
- 只命中部分 `metrics.*` Subject：先补齐现有 Stream 的 subject 覆盖范围，再上线；
- 没有命中任何 Stream：进入 4.3，创建兜底的 `CMDB_METRICS`；
- 命中结果不唯一或存在重叠：停止操作，先解决 subject 归属，不能再创建重叠 Stream。

### 4.2 核对并复用现有 Stream

以下命令中的 `<现有 Stream 名称>` 必须替换为 4.1 的查询结果：

```bash
nats stream info <现有 Stream 名称>
nats stream info <现有 Stream 名称> --json
nats consumer ls <现有 Stream 名称>
```

复用条件：

| 配置 | 要求 |
|---|---|
| Subjects | 覆盖现有 `metrics.*` |
| Storage | `File` |
| Retention/Discard | 满足现场既有可靠性策略 |
| Duplicate Window | 建议不低于 10 分钟 |
| Replicas | 与现场节点数和容量规划一致 |
| Max Age/Max Bytes | 能覆盖峰值采集与允许的消费中断 |
| Consumers | 现有 Telegraf consumer 正常，无持续积压 |

满足上述条件时不要新建 `CMDB_METRICS`，后续直接配置：

```env
NATS_JS_STREAM_NAME=<现有 Stream 名称>
```

如果现有 Stream 的 duplicate window、容量或副本不满足要求，应由 NATS 管理员评估存量消费者后
调整原 Stream；不要由 Stargazer 自动修改，也不要创建第二个覆盖 `metrics.*` 的 Stream。

### 4.3 仅在不存在现有 Stream 时创建

只有 4.1 确认 `metrics.*` 没有被任何 Stream 覆盖时，才执行以下兜底命令。`<副本数>` 和
`<容量上限>` 必须按现场 NATS 拓扑和磁盘规划替换：

```bash
nats stream add CMDB_METRICS \
  --subjects='metrics.*' \
  --storage=file \
  --retention=limits \
  --discard=old \
  --dupe-window=10m \
  --max-age=24h \
  --replicas=<副本数> \
  --max-bytes=<容量上限>
```

建议：

- 单节点验证：`<副本数>` 使用 `1`；
- 三节点生产集群：`<副本数>` 使用 `3`；
- `<容量上限>` 至少覆盖“峰值每秒写入字节数 × 允许消费中断秒数 × 副本和安全余量”；
- 不清楚容量时应先完成容量评估，不要直接使用无限容量；
- `max-age=24h` 是首期建议，可按实际磁盘和允许中断时长调整；
- `duplicate_window` 不得小于 Stargazer 一次发布总预算和典型重连恢复时间，首期使用 10 分钟。

创建后再次执行 `nats stream find metrics.network` 和 `nats stream info CMDB_METRICS`，确认唯一
命中且配置正确。此时 `NATS_JS_STREAM_NAME` 才填写 `CMDB_METRICS`。

### 4.4 发布权限

无论复用还是新建，Stargazer 使用的 NATS 账号都需要：

- 发布 `metrics.*`；
- 接收发布请求的 `_INBOX.>` 响应；
- 使用 JetStream publish API 获得 PubAck。
- 读取配置 Stream 的 info，供 readiness 验证 Stream 存在且覆盖 `metrics.*`。

Stargazer 账号不需要创建、更新或删除 Stream 的管理权限。

## 5. 灰度配置 Stargazer

### 5.1 Docker Compose 示例

```yaml
services:
  stargazer:
    environment:
      NATS_METRICS_JETSTREAM_ENABLED: "true"
      NATS_JS_STREAM_NAME: "<现有 Stream 名称>"
      PUBLISH_WORKERS: "4"
```

使用项目现有的部署命令仅重建或滚动重启 Stargazer，不要同时重启 NATS、Telegraf 和
VictoriaMetrics。

### 5.2 Kubernetes 示例

```yaml
env:
  - name: NATS_METRICS_JETSTREAM_ENABLED
    value: "true"
  - name: NATS_JS_STREAM_NAME
    value: "<现有 Stream 名称>"
  - name: PUBLISH_WORKERS
    value: "4"
```

先只更新一个 Pod。该 Pod 就绪并完成第 6 节验证前，不要继续更新其他 Pod。

## 6. 灰度验证

### 6.1 基础健康检查

```bash
curl -fsS http://<Stargazer地址>:8083/health/
curl -fsS http://<Stargazer地址>:8083/health/ready
curl -fsS http://<Stargazer地址>:8083/health/stats
curl -fsS http://<Stargazer地址>:8083/health/metrics
```

要求 `/health/` 和 `/health/ready` 成功，采集运行时、Redis 和 NATS 没有持续异常。

### 6.2 执行小流量真实采集

先选择 1～10 台非关键网络设备和 1 个已知可正常采集的深信服目标，执行一次真实采集。不要先用
5000 台全量任务验证新配置。

采集过程中观察：

```bash
nats stream info <现有 Stream 名称>
nats consumer ls <现有 Stream 名称>
```

同时从 `/health/metrics` 检查下列 Prometheus 指标；在 `/health/stats` JSON 中，对应字段没有
`stargazer_collection_` 前缀：

- `stargazer_collection_nats_js_publish_confirmed_total` 持续增加；
- `stargazer_collection_nats_js_puback_timeout_total` 不增加；
- `stargazer_collection_nats_js_publish_rejected_total` 不增加；
- `stargazer_collection_nats_js_publish_retry_total` 正常情况下不增加；
- `stargazer_collection_nats_js_publish_pending_messages` 和
  `stargazer_collection_nats_js_publish_pending_bytes` 在采集结束后回落到 0；
- PubAck p95/p99 没有持续逼近 30 秒超时。

最后在 VictoriaMetrics/产品实例页面检查该批目标数据确实出现。JetStream 已确认但页面没有数据时，
继续检查 Telegraf consumer pending、Telegraf 格式解析和 VictoriaMetrics 写入日志，不能把问题归为
Stargazer 发布失败。

### 6.3 灰度通过标准

至少观察一个完整采集周期，并同时满足：

- Stargazer 发布失败数为 0；
- PubAck timeout/rejected 为 0；
- pending 在采集结束后归零；
- NATS Stream 无磁盘、replica lag 或资源限制告警；
- Telegraf consumer pending 能回落；
- 采集目标最终数据可查询，实例数量符合本次采集预期。

通过后逐个滚动更新剩余 Stargazer Pod，每次更新后重复健康检查。不要一次性重启全部实例。

## 7. 回滚

出现以下任一情况立即停止扩容并回滚灰度 Pod：

- `stream not found`、`no response from stream` 或 expected stream 不匹配；
- PubAck timeout/rejected 持续增加；
- pending 长时间不回落；
- NATS 磁盘空间、replica lag 或 CPU 出现风险；
- Stargazer 发布失败导致采集周期无法完成。

生产禁止把 `NATS_METRICS_JETSTREAM_ENABLED` 设为 `false` 回退 Core NATS。应滚动回退到上一版
已验证的 JetStream Adapter 镜像和对应配置，并确认 readiness、PubAck 与最终数据恢复。回滚时：

- 不删除或修改复用的现有 Metrics Stream；
- 不清空 Stream 消息；
- 不删除 Telegraf consumer；
- 不重启整个 NATS 集群；
- 记录失败时间、Stargazer 实例、采集任务 ID、PubAck 指标和 NATS Stream 状态。

## 8. 常见问题定位

| 现象 | 优先检查 | 处理 |
|---|---|---|
| `stream not found` | `NATS_JS_STREAM_NAME`、现有 `metrics.*` 归属 | 填写查询到的 Stream 名称，不要增加超时 |
| expected stream 不匹配 | 配置名称是否等于实际命中的 Stream | 修正名称或 subject 归属，不要创建重叠 Stream |
| PubAck timeout 增加 | NATS 磁盘、replica lag、RTT、CPU | 先处理 NATS 瓶颈，不要无限重试 |
| rejected 增加 | 权限、Stream 限额、消息大小 | 核对 NATS 账号权限和 Stream limits |
| PubAck 成功但实例无数据 | Telegraf consumer pending、格式解析、VM 写入 | 转查消费与入库链路 |
| pending 长时间满 256 | PubAck 延迟或 NATS 阻塞 | 同时检查 waiting 与 pending，必要时回滚，不能盲目放大窗口 |
| 只有部分目标失败 | 对应目标格式校验和 result ID 日志 | 修复数据格式或插件，避免重复全量重推 |

## 9. 实施记录模板

实施人员应在变更单记录以下内容，但不得记录凭据：

```text
实施时间：
实施人员：
Stargazer 版本/镜像：
灰度实例：
NATS 版本和节点数：
复用的 Metrics Stream 名称：
Stream subjects/replicas/max_age/max_bytes：
灰度采集任务 ID：
采集目标数：
PubAck confirmed/timeout/retry/rejected：
PubAck p95/p99：
Stream messages/bytes：
Consumer pending：
最终实例数量核对：
结果：通过 / 回滚
异常说明：
```

## 10. 相关材料

- 架构与参数：`jetstream-async-publish-window-plan-2026-08-28.md`；
- 5000 网络设备和深信服压测：`jetstream-publish-load-test-report-2026-08-28.md`；
- Stargazer 环境变量示例：`agents/stargazer/.env.example`。
