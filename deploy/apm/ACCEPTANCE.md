# APM 数据面验收清单

本文是给运维的**验收与约束清单**，不是发布流水线设计文档。APM 从未正式部署；
首次上线没有旧 APM 数据面可恢复。生产编排、镜像流水线、容量扩缩与值班体系由运维自有平台完成，
但必须满足下列契约与判定。Monitor 的 VictoriaMetrics 始终不在 APM 操作范围内。

正式链路：

```text
OTel SDK / Agent
  -> 区域 Collector（OTLP/HTTP 4318；4317 仅手工兼容）
  -> NATS JetStream apm.traces.<cloud_region_id>
  -> 系统级 Collector
  -> VictoriaTraces
```

契约夹具与组件说明见 [README.md](./README.md)。本地/CI 可用 `cd deploy/apm && make test|validate|contract`
证明语义，不能替代生产验收。

## 上线前必须为真

1. 使用 `deploy/apm/collector` 构建的固定版本镜像已进入生产镜像仓库；受管区域代理引用的
   tag 存在且非 `latest`。
2. 已按 [CAPACITY.md](./CAPACITY.md) 填入峰值、断连容忍、保留期、副本与告警阈值，并据此
   配置 Stream/队列/VT 磁盘下界。
3. NATS 管理、区域发布、中心消费身份分离；区域 publish ACL 精确到
   `apm.traces.<自身区域>`；运行身份无 Stream/Consumer 管理权限。
4. Server 已按 `server/support-files/env/.env.apm.example` 注入运行期查询/健康变量；上述
   endpoint 不得加入 `batch_init` 或进程启动等待。
5. 每个云区域的 NodeMgmt 受信代理地址已确认；TCP 4318 仅受信区域内网可达（ADR 0008）。
6. 预发布环境已保存契约夹具 `make test` / `make validate` / `make contract` 的命令、镜像
   digest 与结果。

## 就绪顺序（逻辑依赖，非流水线步骤）

下列是依赖就绪的逻辑顺序；运维用自有流水线实现，但不得跳过验收点。

1. **传输契约就绪**：有界 `APM_TRACES` Stream 与 `BKLITE_APM_SYSTEM` durable consumer
   （max bytes/age/message、duplicate window、AckExplicit、ack wait、max deliver、max ack
   pending）。同名对象配置不一致时停止并人工确认归属，不得当作旧 APM 直接复用。
2. **VictoriaTraces 就绪**：保留期 ≥ 35 天，`-servicegraph.enableTask=true`；OTLP 写入、
   健康、查询与磁盘/保留期告警可用。
3. **系统级 Collector 就绪**：VT 不可用时不 ACK、pending 增长，恢复后积压可排空。
4. **单区域 Collector 就绪**：非关键区域；持久队列 + 受信内网 4318；独立 NATS 凭据且只能
   发布本区域 Subject。
5. **真实遥测验收**：Server 生成配置 + 真实 SDK；核对 namespace/name/instance、
   `bk.cloud_region.id`、清洗结果与 VT 查询。
6. **故障恢复验收**：断开区域 NATS / 暂停系统 Collector / 暂停 VT；核对排队、pending、
   NAK/重投、排空与 RED/SLO 唯一 Span 统计。
7. **逐区域扩展**：每次一区域；失败则停止扩展，不影响已验收区域。
8. **Server/Web 开放**：数据面不可用时 APM 显示 degraded/unavailable；API/Worker/Beat/Listener
   仍可启动。

## 完成判定

- 所有区域 4318 仅受信内网可达；接入页只生成 OTLP/HTTP 端点。
- 区域发布、中心消费、管理身份权限分离；秘密未进日志、Span 或仓库。
- 故障演练符合至少一次投递、有界队列与显式 ACK。
- 目录、Trace、RED、端点、SLO、策略、告警与 dependencies 查询均来自 VT；失败不伪装空数据。
- 生产组件清单中不存在 APM Edge、APM VictoriaMetrics、spanmetrics、tail sampling 或独立
  APM Gateway。

## 回滚约束

若任一门禁或验收失败：

1. 停止新增区域；对未验收区域关闭 4318 并停止区域 Collector。
2. 若 Server/Web 已开放 APM，回退本次应用发布或关闭入口；不得影响其他产品域。
3. Collector 问题只回退到本次已验证的前一个候选 digest；没有已验证候选时停止对应
   Collector，**不得临时引入其他接收代理**。
4. 保留 Stream、区域持久队列和 VictoriaTraces 已写数据，不清空、不手工重复发布。
5. 删除 Stream/Consumer、VT 卷、Secret 或缩短保留期须独立显式审批，不由应用回滚脚本执行。
6. 记录失败区域、digest、首个失败指标、积压边界与回滚动作，通过同一验收清单后再重试。

回滚目标是安全关闭或回退本次首次上线版本，不得临时引入正式链路之外的组件。
