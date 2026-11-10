# 02 — APM 中心 Collector 生成聚合指标

Status: done

Blocked by: 01 — 聚合层规则文档与 ADR

**What to build:** 中心 Collector 收到入口 Span 后，2 分钟内聚合库出现 `apm_` 计数和耗时直方图，标签只有命名空间、服务、
环境、入口操作、状态、`job`、`shard`；晚到 Span 只进晚到计数；聚合库不可达时调用链照常入库、接收器不 NAK、VictoriaTraces
不重复写入。

- [x] builder 加入 v0.153.0 的 spanmetrics、count、filter、deltatocumulative、prometheusremotewrite 及资源属性收窄所需处理器；
      核心版本不变；镜像能构建
- [x] 系统 Collector 配置按 spec 增加聚合分支与晚到分支；聚合分支不含 memory_limiter 等会回传错误的组件；
      remote write 写 `AGG_VICTORIAMETRICS_WRITE_URL`，`shard` 来自 `APM_AGG_SHARD`
- [x] 必验：同一服务多实例（不同 `service.instance.id`）只产生一组序列、无 `instance` 标签、数值为各实例之和
- [x] 必验：标签集合、带单位的桶、溢出序列、晚到不计入且 `apm_aggregate_late_spans_total`（经 deltatocumulative）可查、
      remote write 不可达时不 NAK 且 VictoriaTraces 不重复（spanmetrics 与 count 两条分支都测）、重启后 `increase()` 正确
- [x] `deploy/apm` 的验收清单、README、容量文档与本地 fixture（compose 可加一个临时聚合库服务用于本地验证）同步；
      `test_data_plane_config.py` 改为锁定新的聚合分支形状与约束；`DEVELOP.md`「APM 数据面」的回滚一行改为
      说明聚合分支可单独回退（去掉“不恢复 spanmetrics”的旧句）
- [x] `make -C deploy/apm test validate` 通过；容器级验证用临时容器，端口避开 8428/9428/10428，结束后清理

## Notes

- 环境字段名以 Server 现有 RED 查询使用的环境字段为准。
- 验证报告里的 `agg.yaml`、`e2e-ack.yaml`、`e2e-nak.yaml` 是可直接参考的配置原型。
- 复核决定（按推荐方案）：Collector 无法按空环境变量只停用一条流水线，所以接受“两份配置”的做法。
  挂 `system.yaml` 时必须配置写入地址和分片；聚合库未就绪时改挂 `system-traces.yaml`，明细不受影响。
  这一条已写进 `deploy/apm/README.md` 和验收清单。
- 已在 observability-followups/01 修复：`test_data_plane_contract.py` 末尾的 Python SDK 片段按探针下载地址契约生成并执行。

## Completion evidence

环境字段用 Server RED 查询里的 `deployment.environment`。写入地址或分片为空时，`system.yaml` 让整个系统 Collector 起不来；明细要保住就改挂 `otel/system-traces.yaml`。晚到计数在 `deltatocumulative` 之前把样本时间改成处理时刻，否则时间落在 Span 结束时间上，即时查询看不到。溢出序列只有 `otel.metric.overflow=true`，不再带服务名和操作名，`job` 仍是「命名空间/服务名」。

镜像标签是 `bklite/apm-otel-collector:0.153.0-bklite.2`，临时验证标签 `bklite-apm-collector:agg-verify`（同一镜像 `sha256:e04a3c62f2e5`）。用户栈正在用的 `0.153.0-bklite.1` 仍是 `sha256:a8b31c2d2186`。容器契约使用 project `apm-agg-verify-*` 和 `bk-lite-apm-contract-*`，宿主端口随机，没有写 8428、9428、10428。结束后这些 project 的容器、网络和卷都已删除。用户栈 `bk-lite-apm-apm-*` 仍在运行。

- `make -C deploy/apm test validate`：退出码 0。Go 测试三个包为 cached ok。`system.yaml` 在写入地址为空时报 `invalid endpoint`，分片为空时报 external labels 为空；`system-traces.yaml` 在这两个变量都空时可以通过校验。
- `RUN_APM_CONTAINER_CONTRACT=1 uv run pytest ../deploy/apm/tests/test_aggregate_contract.py`：3 passed in 70.49s。覆盖多实例合并（checkout 两条 SERVER 合成 1 条、值为 2、无 `instance`）、标签集合、12ms 落在 25ms 桶、基数上限 2 时保留 2 条合计 2 且溢出 1 条值为 3、晚到不进 `apm_calls_total` 且 `apm_aggregate_late_spans_total` 可查、remote write 指向容器内 `127.0.0.1:1` 时三条 Span（新的 SERVER、晚到 SERVER、CLIENT）全部 ACK 且 VictoriaTraces 为 spans=3 rows=3、重启后 `increase()` 从 3 到 4 并保持。
- `pytest apps/apm/tests/test_data_plane_config.py`：13 passed。
- `pytest apps/apm/tests`：11 failed, 825 passed, 2 skipped。失败项是 topology 8 项、deployments backfill 1 项、cross_database_guard 1 项、owned_alert_lifecycle 1 项，与已知 sqlite 基线一致。
- 原 `test_data_plane_contract.py` 的 Collector 与 VictoriaTraces 断言通过（ACK、断网补发、VT 停止后 NAK 再恢复、去重、servicegraph）。末尾 Python SDK 片段在 `render_snippet` 处失败：`snippets require a resolved probe_download_url`。该文件的服务端片段逻辑不在本次改动里。

