# APM 首次上线与回滚

本手册只适用于 BK-Lite APM 的首次生产上线。APM 从未正式部署，不存在历史 APM 数据面、
路由或 Trace 数据需要迁移；首次上线只创建本文列出的正式组件，不引入其他接收、派生指标或
采样链路。Monitor 的 VictoriaMetrics 服务、数据、环境变量和告警始终不在 APM 操作范围内。

首次上线的唯一正式链路是：

```text
OTel SDK / Agent
  -> 区域 Collector（OTLP/HTTP 4318；4317 仅手工兼容）
  -> NATS JetStream apm.traces.<cloud_region_id>
  -> 系统级 Collector
  -> VictoriaTraces
```

## 上线前门禁

1. 构建并推送 `deploy/apm/collector` 定义的固定版本镜像；受管区域代理引用的镜像 tag 必须
   已存在于生产镜像仓库，禁止使用 `latest`。
2. 按 `CAPACITY.md` 记录峰值 spans/s、平均 bytes/span、区域断连容忍时长、JetStream/VT
   容量、35 天保留期、副本和告警阈值。
3. 准备相互分离的 NATS 管理、区域发布和中心消费身份。区域发布 ACL 必须精确到
   `apm.traces.<自身区域>`；运行身份不得拥有 Stream/Consumer 管理权限。
4. 按 `server/support-files/env/.env.apm.example` 准备 Server 运行期查询与健康变量。所有外部
   endpoint 都是运行期可降级依赖，不能加入 `batch_init` 或 Server 进程启动等待。
5. 为每个云区域确认 NodeMgmt 受信代理地址。宿主机防火墙、安全组或等价网络策略必须把
   TCP 4318 限制为受信区域内网来源；公网、跨租户和其他不受信网络不得开放。
6. 在预发布环境运行 `make apm-test`、`make apm-validate` 和 `make apm-contract`，保存命令、
   镜像 digest 与结果。

## 首次上线顺序

1. **中心传输契约**：创建或核对有界 `APM_TRACES` Stream 与 `BKLITE_APM_SYSTEM` durable
   consumer，包括 max bytes/age/message、duplicate window、AckExplicit、ack wait、max
   deliver 和 max ack pending。声明过程必须幂等；若目标环境意外存在同名对象且配置不一致，
   停止上线并人工确认归属，不得把它视为旧 APM 部署直接复用。
2. **VictoriaTraces**：部署保留期至少 35 天且启用 `-servicegraph.enableTask=true` 的 VT，验证
   OTLP 写入、健康、查询、磁盘余量和保留期告警。
3. **系统级 Collector**：部署中心消费者，确认 VT 不可用时消息不 ACK、consumer pending
   增长，恢复后积压可排空。
4. **单区域 Collector**：先选一个非关键云区域，通过最新 NodeMgmt 代理安装包部署区域
   Collector、持久队列和 TCP 4318 映射。确认它使用独立随机 NATS 凭据，且只能发布本区域
   Subject。
5. **真实遥测验收**：使用 Server 生成的配置和真实 SDK 上报唯一测试 Trace，核对
   `service.namespace`、`service.name`、`service.instance.id`、`bk.cloud_region.id`、清洗结果和
   VictoriaTraces 查询。
6. **故障恢复演练**：依次断开区域 NATS、暂停系统级 Collector、暂停 VT；核对区域队列、
   Stream pending、NAK/重投、恢复排空和 RED/SLO 唯一 Span 统计。
7. **逐区域开放**：每次只增加一个区域，重复网络、ACL、健康和真实 Trace 验收；任一区域失败
   时停止扩展，不影响已验收区域。
8. **Server/Web 开放**：注入正式环境变量并发布接入与查询功能。数据面不可用时必须显示
   degraded/unavailable，API、Worker、Beat 和 Listener 仍能正常启动。

## 上线完成判定

- 所有区域的 4318 只在受信内网可达，普通接入页面只生成 OTLP/HTTP 端点。
- 区域发布、中心消费和管理身份权限相互分离，秘密未进入日志、Span 或仓库。
- NATS/中心/VT 故障演练与恢复符合至少一次、有界队列和显式 ACK 契约。
- Server 的目录、Trace、RED、端点、SLO、策略、告警与 dependencies 查询均来自 VT，查询失败
  不伪装为空数据。
- 生产组件清单中不存在 APM Edge、APM VictoriaMetrics、spanmetrics、tail sampling 或独立
  APM Gateway。

## 首次上线回滚

首次上线没有旧 APM 数据面可恢复。若任一门禁或验收失败：

1. 停止新增区域；对未验收区域关闭 4318 网络入口并停止区域 Collector，避免继续接收数据。
2. 若 Server/Web 已开放 APM，回退本次应用发布或关闭 APM 菜单/入口；不得让查询失败影响其他
  产品域。
3. 若问题来自新 Collector 镜像，只回退到本次上线过程中已验证的前一个候选 digest；没有已
   验证候选时停止对应 Collector，不得临时引入其他接收代理。
4. 保留已写入的 Stream、区域持久队列和 VictoriaTraces 数据，不清空、不手工重复发布；修复后
   由同一正式链路恢复消费。
5. Stream/Consumer、VT 卷和 Secret 的删除属于独立、显式审批的首次上线撤销动作，不由应用
   回滚脚本执行；任何缩短保留期也必须另行审批。
6. 记录失败区域、镜像 digest、首个失败指标、积压边界和回滚动作，通过同一上线门禁后再重试。

回滚的目标是安全关闭或回退本次首次上线版本，不得临时引入正式链路之外的组件。
