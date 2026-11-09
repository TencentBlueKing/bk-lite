# 05 — RUM 网关生成聚合指标

Status: ready

Blocked by: 01 — 聚合层规则文档与 ADR

**What to build:** 网关收到事件后，2 分钟内聚合库出现 `rum_` 浏览、JS 错误计数和五个 Web Vitals 直方图，标签只有租户、
流量类型、应用、环境、聚合路由与固定分片；单个应用路由超过 100 条进入「其他」且多副本一致；聚合库不可达时网关接收接口
不失败、VictoriaLogs 不出现重复事件。

- [ ] 网关构建加入 v0.154.0 的 signal_to_metrics、forward、deltatocumulative、prometheusremotewrite、batch（如未有）
- [ ] 新增路由上限处理器：Redis 共享准入表（每应用最多 100）、进程内缓存、Redis 失败时记「其他」并计数；从不向上游返回错误
- [ ] 网关配置按 spec 增加 `forward → logs/rum_agg → signal_to_metrics`、`metrics/rum_agg: batch → deltatocumulative →
      prometheusremotewrite`；聚合专用路由字段不进入 VictoriaLogs；`shard` 与遥测 `service.instance.id` 来自 `RUM_AGG_SHARD`
- [ ] 浏览、JS 错误、各 vital 的判定条件与 Server 现有 LogsQL 一致；桶按 spec；`max_streams` 兜底且丢弃有指标
- [ ] 测试：标签集合与白名单、路由上限与多副本一致（两个处理器实例共享同一 Redis）、错误隔离（remote write 不可达时
      接收返回成功且 VictoriaLogs 无重复）、重启后 `increase()` 正确
- [ ] `deploy/rum` 的验收清单、部署说明、README 与 dev 配置同步；`make -C deploy/rum test validate` 通过；
      临时容器端口避开 8428/9428/10428，结束后清理

## Notes

- 不实现晚到过滤与 `rum_aggregate_late_events_total`（见 spec「不做晚到过滤」）。
- 概念验证的配置原型：agent store `aggregation-verification-2026-11-09/rum-poc-reference/`。
