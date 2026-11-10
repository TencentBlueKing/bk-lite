# 05 — RUM 网关生成聚合指标

Status: done

Blocked by: 01 — 聚合层规则文档与 ADR

**What to build:** 网关收到事件后，2 分钟内聚合库出现 `rum_` 浏览、JS 错误计数和五个 Web Vitals 直方图，标签只有租户、
流量类型、应用、环境、聚合路由与固定分片；单个应用路由超过 100 条进入「其他」且多副本一致；聚合库不可达时网关接收接口
不失败、VictoriaLogs 不出现重复事件。

- [x] 网关构建加入 v0.154.0 的 signal_to_metrics、forward、deltatocumulative、prometheusremotewrite、batch（如未有）
- [x] 新增路由上限处理器：Redis 共享准入表（每应用最多 100）、进程内缓存、Redis 失败时记「其他」并计数；从不向上游返回错误
- [x] 网关配置按 spec 增加 `forward → logs/rum_agg → signal_to_metrics`、`metrics/rum_agg: batch → deltatocumulative →
      prometheusremotewrite`；聚合专用路由字段不进入 VictoriaLogs；`shard` 与遥测 `service.instance.id` 来自 `RUM_AGG_SHARD`
- [x] 浏览、JS 错误、各 vital 的判定条件与 Server 现有 LogsQL 一致；桶按 spec；`max_streams` 兜底且丢弃有指标
- [x] 测试：标签集合与白名单、路由上限与多副本一致（两个处理器实例共享同一 Redis）、错误隔离（remote write 不可达时
      接收返回成功且 VictoriaLogs 无重复）、重启后 `increase()` 正确
- [x] `deploy/rum` 的验收清单、部署说明、README 与 dev 配置同步；`make -C deploy/rum test validate` 通过；
      临时容器端口避开 8428/9428/10428，结束后清理

## Notes

- 不实现晚到过滤与 `rum_aggregate_late_events_total`（见 spec「不做晚到过滤」）。
- 概念验证的配置原型：agent store `aggregation-verification-2026-11-09/rum-poc-reference/`。
- 配置里的导出器类型用 `prometheus_remote_write`。`prometheusremotewrite` 在 v0.154.0 仍是别名，启动时会打弃用警告。

## Completion evidence

- `cd deploy/rum/collector && go test ./internal/rum/components/rumroutecap/ -count=1`：通过。覆盖 100 条后记「其他」、两个处理器实例共享同一 Redis、Redis 关闭后已缓存路由不变且新路由记「其他」并计数、下游错误不外传。
- `cd deploy/rum/collector && RUN_RUM_AGG_CONTRACT=1 go test ./internal/rum/aggregatecontract/ -count=1 -timeout 12m -run TestAggregateContract -v`：通过，106.98s。镜像为最终的 `bklite/rum-collector:0.1.0-bklite.2`。`labels_and_buckets` 32.10s，`remote_write_isolation` 8.01s，`restart_increase` 61.50s（`increase()` 3 后重启再记 1，结果为 4），`max_streams_drop_metric` 1.01s（`otelcol_deltatocumulative_datapoints` 带 `error="limit"`）。标签没有 `job`、`service_name`、用户、会话或原始 URL。独立网络 `rum-agg-verify-<pid>`，宿主端口随机且避开 6379、8428、9428、10428。
- `make -C deploy/rum test validate`：退出码 0。含 collector、controller、maintainer 单测，`docker compose config --quiet`，以及 `rum.gateway.dev.yaml` 校验。
- `./_build/bklite-rum-gateway components`：`signal_to_metrics` 的 `logs_to_metrics` 为 Alpha，`forward` 的 `logs_to_logs` 为 Beta，`deltatocumulative` 的 metrics 为 Alpha，`prometheus_remote_write` 的 metrics 为 Beta，`basicauth` 扩展为 Beta，`rumroutecap` 的 logs 为 Alpha。
- 镜像 `bklite/rum-collector:0.1.0-bklite.2`，没有覆盖 `0.1.0-bklite.1`。契约结束后 `docker ps` 没有 `bk-lite-rum-agg-verify` 容器或网络。
