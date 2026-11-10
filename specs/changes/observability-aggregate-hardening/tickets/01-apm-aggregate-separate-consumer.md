# 01 — APM 聚合改为独立消费者与独立进程

Status: ready

Blocked by: None

**What to build:** 新增 durable consumer `BKLITE_APM_AGGREGATE` 和聚合 Collector 进程 `apm-aggregate-collector`；
系统 Collector 只写 VictoriaTraces。VictoriaTraces 不可用期间写入的 Span，恢复后在聚合库只算一次。

- [ ] `deploy/apm/compose.yaml` 的 `apm-nats-init` 幂等创建 `BKLITE_APM_AGGREGATE`（`--deliver new`、显式 ACK、过滤 `apm.traces.>`），
  重投次数与 ACK 等待使用独立变量并给出默认值；说明为什么这样取值
- [ ] 新增 `apm-aggregate-collector` 服务与 `deploy/apm/otel/aggregate.yaml`、`aggregate-auth.yaml`；
  入口流水线顺序：`memory_limiter` → 入口过滤 → 资源收窄 → 按晚到条件分流到 `span_metrics` / `count/late`
- [ ] 分流组件：先确认 v0.153 的 `routing` connector 能按 Span 级条件分流；需要加入构建时同步改 `builder-config.yaml`、
  镜像版本升到 `0.153.0-bklite.3`，并更新所有引用该 tag 的位置
- [ ] `system.yaml` 删除聚合与晚到流水线和相关变量；删除 `system-traces.yaml`、`system-auth.yaml`，清理所有引用
- [ ] 契约：VictoriaTraces 停止期间写入一批入口 Span，恢复后聚合请求数等于 Span 数；保留聚合库不可达不重复写明细、重启后 `increase()` 正确
- [ ] 数据面配置契约：系统配置无聚合分支；聚合配置单条入口流水线、`memory_limiter` 在计数之前、不读取 `VICTORIAMETRICS_HOST`
- [ ] 文档：`deploy/apm/README.md`、`deploy/apm/ACCEPTANCE.md`、`docs/operations/aggregate-metrics-store.md`、
  `docs/operations/apm-rum-query-performance-rollout.md`（进程清单、consumer 预建命令、变量归属、内存建议、回滚）
- [ ] `make -C deploy/apm test validate` 通过；契约按需运行并记录结果

## Notes

- 聚合进程的内存建议单独给出（容器上限与 `memory_limiter` 取值），依据现有容量压测数据，不另做压测。
- 生产 NATS ACL 若按 consumer 名授权，在上线文档提醒补授权；仓库内 `nats-server.conf` 已是通配，不改。
- 只用独立 Compose project 和随机端口跑契约，不碰用户正在运行的 `bk-lite-apm-*` 容器，也不改 `deploy/apm/.env`。

## Completion evidence

