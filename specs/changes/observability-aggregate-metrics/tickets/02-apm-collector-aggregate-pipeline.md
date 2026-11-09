# 02 — APM 中心 Collector 生成聚合指标

Status: ready

Blocked by: 01 — 聚合层规则文档与 ADR

**What to build:** 中心 Collector 收到入口 Span 后，2 分钟内聚合库出现 `apm_` 计数和耗时直方图，标签只有命名空间、服务、
环境、入口操作、状态、`job`、`shard`；晚到 Span 只进晚到计数；聚合库不可达时调用链照常入库、接收器不 NAK、VictoriaTraces
不重复写入。

- [ ] builder 加入 v0.153.0 的 spanmetrics、count、filter、deltatocumulative、prometheusremotewrite 及资源属性收窄所需处理器；
      核心版本不变；镜像能构建
- [ ] 系统 Collector 配置按 spec 增加聚合分支与晚到分支；聚合分支不含 memory_limiter 等会回传错误的组件；
      remote write 写 `AGG_VICTORIAMETRICS_WRITE_URL`，`shard` 来自 `APM_AGG_SHARD`
- [ ] 必验：同一服务多实例（不同 `service.instance.id`）只产生一组序列、无 `instance` 标签、数值为各实例之和
- [ ] 必验：标签集合、带单位的桶、溢出序列、晚到不计入且 `apm_aggregate_late_spans_total`（经 deltatocumulative）可查、
      remote write 不可达时不 NAK 且 VictoriaTraces 不重复（spanmetrics 与 count 两条分支都测）、重启后 `increase()` 正确
- [ ] `deploy/apm` 的验收清单、README、容量文档与本地 fixture（compose 可加一个临时聚合库服务用于本地验证）同步；
      `test_data_plane_config.py` 改为锁定新的聚合分支形状与约束；`DEVELOP.md`「APM 数据面」的回滚一行改为
      说明聚合分支可单独回退（去掉“不恢复 spanmetrics”的旧句）
- [ ] `make -C deploy/apm test validate` 通过；容器级验证用临时容器，端口避开 8428/9428/10428，结束后清理

## Notes

- 环境字段名以 Server 现有 RED 查询使用的环境字段为准。
- 验证报告里的 `agg.yaml`、`e2e-ack.yaml`、`e2e-nak.yaml` 是可直接参考的配置原型。
