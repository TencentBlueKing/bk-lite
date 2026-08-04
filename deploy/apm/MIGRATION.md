# APM NATS / VictoriaTraces-only 升级与回滚

本手册只迁移 APM。Monitor 的 VictoriaMetrics 服务、数据、环境变量和告警不在操作范围内。
升级脚本不删除旧卷、Stream 或 Trace；任何删除和缩短保留期都必须由运维另行审批。

## 升级前检查

1. 记录旧 APM Edge 路由、Collector 镜像与配置、APM 专用 Span Metrics 写入端点和 Server 读路径，
   保存至少一个发布窗口；确认哪些 VictoriaMetrics 资源是 APM 专用，不能按名称猜测。
2. 按 `CAPACITY.md` 填写生产容量输入。创建或核对 `APM_TRACES` Stream、
   `BKLITE_APM_SYSTEM` durable consumer、区域精确 Subject ACL、中心消费 ACL 和告警。
3. 部署保留期至少 35 天且启用 `-servicegraph.enableTask=true` 的 VictoriaTraces，再部署系统级
   Collector。确认 VT 不可用时 consumer pending 增加且消息不 ACK。
4. 为 Server 注入运行期健康 endpoint 与实际 `APM_TRACE_RETENTION`；启动和 `batch_init` 不得
   依赖这些 endpoint。

## 分区切流

1. 每次只选一个云区域，部署区域 Collector 到新的受控地址，验证 OTLP HTTP/gRPC、清洗、
   publish ACK、Stream backlog 和中心写入。
2. 把该云区域受信 envconfig 的 `APM_OTLP_HTTP_ENDPOINT` / `APM_OTLP_GRPC_ENDPOINT` 切到新入口。
   旧 Edge 与新 Collector 不能同时绑定同一宿主端口；使用负载均衡后端切换或隔离端口。
3. 观察至少一个区域故障恢复演练：断开 NATS 后本地队列增长并恢复；暂停中心消费者后 Stream
   积压并恢复；暂停 VT 后消息不 ACK，恢复后不产生 RED/SLO 双计数。
4. 所有区域完成后切换 Server 到 `VictoriaTracesTelemetryStore`，核对目录、Trace、RED、端点、
   SLO、策略、告警和 dependencies 拓扑。查询失败必须显示 unavailable，不能触发恢复事件。

## 停止旧路径

按以下顺序停止，不立即删除：

1. 停止旧 Collector 的 APM spanmetrics 写入；
2. 确认 Server 已无 APM VictoriaMetrics 读取后，停止 APM 专用 VM profile/健康探测；
3. 从流量入口移除 APM Edge，再停止 Edge 容器；
4. 保留旧镜像、Edge 配置、Collector 配置及 APM 专用 VM 卷的只读快照至少一个发布窗口。

可删除物仅包括确认属于 APM 的旧 Edge service/route、旧 tail-sampling/spanmetrics 配置、APM
专用 VM profile 与 APM VM 环境变量。不得删除共享或 Monitor VictoriaMetrics。清理卷前必须有
可验证快照；Stream 和 VT 数据不由应用升级清理。

## 回滚

如果区域发布、中心消费或 VT 查询任一验收失败：

1. 停止继续切流，但保留 NATS/VT 中已写数据；
2. 把受影响区域 envconfig/负载均衡后端恢复到已保存的旧 Edge；
3. 恢复旧 Collector 镜像和 APM Span Metrics 写入，再恢复上一版 Server 读路径；
4. 不清空区域本地队列或 Stream。若旧链路无法消费这些消息，保持隔离并在修复后由新中心链路
   回放；避免把同一批消息手工重复发布；
5. 记录回滚时间、区域、首个失败指标和积压边界，再决定重试升级或扩大容量。

Server 回滚只恢复上一版本二进制；Django 领域模型与本变更兼容且无破坏性迁移。应用组织同步
是事务操作，不需要数据回滚。
