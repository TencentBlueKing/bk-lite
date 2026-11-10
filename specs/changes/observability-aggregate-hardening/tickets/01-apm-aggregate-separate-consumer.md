# 01 — APM 聚合改为独立消费者与独立进程

Status: done

Blocked by: None

**What to build:** 新增 durable consumer `BKLITE_APM_AGGREGATE` 和聚合 Collector 进程 `apm-aggregate-collector`；
系统 Collector 只写 VictoriaTraces。VictoriaTraces 不可用期间写入的 Span，恢复后在聚合库只算一次。

- [x] `deploy/apm/compose.yaml` 的 `apm-nats-init` 幂等创建 `BKLITE_APM_AGGREGATE`（`--deliver new`、显式 ACK、过滤 `apm.traces.>`），
  重投次数与 ACK 等待使用独立变量并给出默认值；说明为什么这样取值
- [x] 新增 `apm-aggregate-collector` 服务与 `deploy/apm/otel/aggregate.yaml`、`aggregate-auth.yaml`；
  入口流水线顺序：`memory_limiter` → 入口过滤 → 资源收窄 → 按晚到条件分流到 `span_metrics` / `count/late`
- [x] 分流组件：先确认 v0.153 的 `routing` connector 能按 Span 级条件分流；需要加入构建时同步改 `builder-config.yaml`、
  镜像版本升到 `0.153.0-bklite.3`，并更新所有引用该 tag 的位置
- [x] `system.yaml` 删除聚合与晚到流水线和相关变量；删除 `system-traces.yaml`、`system-auth.yaml`，清理所有引用
- [x] 契约：VictoriaTraces 停止期间写入一批入口 Span，恢复后聚合请求数等于 Span 数；保留聚合库不可达不重复写明细、重启后 `increase()` 正确
- [x] 数据面配置契约：系统配置无聚合分支；聚合配置单条入口流水线、`memory_limiter` 在计数之前、不读取 `VICTORIAMETRICS_HOST`
- [x] 文档：`deploy/apm/README.md`、`deploy/apm/ACCEPTANCE.md`、`docs/operations/aggregate-metrics-store.md`、
  `docs/operations/apm-rum-query-performance-rollout.md`（进程清单、consumer 预建命令、变量归属、内存建议、回滚）
- [x] `make -C deploy/apm test validate` 通过；契约按需运行并记录结果

## Notes

- 聚合进程的内存建议单独给出（容器上限与 `memory_limiter` 取值），依据现有容量压测数据，不另做压测。
- 生产 NATS ACL 若按 consumer 名授权，在上线文档提醒补授权；仓库内 `nats-server.conf` 已是通配，不改。
- 只用独立 Compose project 和随机端口跑契约，不碰用户正在运行的 `bk-lite-apm-*` 容器，也不改 `deploy/apm/.env`。

## Completion evidence

分流用 v0.153 `routing` connector 的 Span 上下文。源码 `MoveSpansWithContextIf` 按条件把 Span 移走，资源和 scope 只复制一次，默认动作是 `move` 不是 `copy`。`aggregate.yaml` 只有一条 `nats_jetstream` 入口：`memory_limiter` → `filter/entry` → `transform/narrow_resource` → `routing`。表项 `context: span`，条件 `span.end_time_unix_nano < UnixNano(Now()) - 300000000000`，目标 `traces/late`；`default_pipelines` 是 `traces/aggregate`。晚到 Span 被移走，其余进 `span_metrics`，两条流水线不会各自克隆整批。`metrics/apm_late` 仍保留 `batch/late`，避免 count 的导出失败经 routing 退回接收器、把同一条消息里已经计入的新鲜 Span 再算一次。`otelcol validate` 会真正建流水线，空写入地址和空分片分别报 `invalid endpoint`、`empty key or value`，routing 条件能通过创建。

聚合消费者 `BKLITE_APM_AGGREGATE`：过滤 `apm.traces.>`，pull，显式 ACK，`--deliver new`，`--replay instant`。`APM_AGG_NATS_ACK_WAIT` 默认 `30s`，`APM_AGG_NATS_MAX_DELIVER` 默认 `3`，`max ack pending` 仍用 `APM_NATS_MAX_ACK_PENDING`（默认 256）。`deliver new` 只在首次创建时生效，已存在的同名消费者不被 `consumer info || consumer add` 改写，也不要删掉重建。ACK 等待短于系统侧 60s，因为聚合入口在内存里完成，不必盖住 VictoriaTraces 导出重试（`max_elapsed_time` 30s，系统 `downstream_timeout` 45s）。聚合配置里的 `downstream_timeout` 写死 20s，必须小于 ACK 等待，所以不要把 `APM_AGG_NATS_ACK_WAIT` 调到 20s 或更短。重投上限取 3：正常路径不把导出错误退回接收器，重投只覆盖崩溃或卡住的在途消息；取 1 会在每次重启丢掉已拉取未 ACK 的消息，取 8 会在崩溃循环里把计数放大。`nak_delay` 仍是 5s。两个 Collector 都用系统 NATS 账号。仓库 `nats-server.conf` 已是 `$JS.API.CONSUMER.*.APM_TRACES.*`，未改。文档写明生产若按 consumer 名授权，要给 `BKLITE_APM_AGGREGATE` 补 info、pull 和 ACK。

内存按容量压测里约 236 MiB 的聚合堆取值，没有新压测。`APM_AGG_COLLECTOR_MEMORY_LIMIT_MIB` 默认 512，`APM_AGG_COLLECTOR_MEMORY_SPIKE_MIB` 默认 128，软拒绝线 384 MiB。容器上限 `APM_AGG_COLLECTOR_CONTAINER_MEMORY_LIMIT` 默认 `640m`，CPU `APM_AGG_COLLECTOR_CPU_LIMIT` 默认 1.00。这些名字不复用聚合库容器的 `APM_AGG_MEMORY_LIMIT` / `APM_AGG_CPU_LIMIT`。系统 Collector 仍是 384 / 96 / 512。拒收发生在计数之前，只 NAK 聚合消费者；持续超限会在 3 次投递后丢掉该批，不把计数放大。

镜像 `bklite/apm-otel-collector:0.153.0-bklite.3`（`sha256:6f247abb765d85e45c3ef63567e017f0a6c874d649a4eedf21eddcdae80a7f33`）。builder 增加 `routingconnector v0.153.0`。删除 `deploy/apm/otel/system-traces.yaml` 和 `system-auth.yaml`。引用已从 README、ACCEPTANCE、DEVELOP、collector Makefile、容量文档和运行文档清掉。`specs/changes` 里已完成的历史规格未改。当前 `spec.md` 仍写明这两份文件要删除。`system.yaml` 只剩 VictoriaTraces 流水线。基础认证在 `aggregate-auth.yaml`，只在用户名和口令都设置时追加。

契约 project 是 `apm-agg-verify-<pid>-*` 和既有夹具的 `bk-lite-apm-contract-<pid>`，宿主端口随机并避开 8428、9428、10428、6379。没有操作 Compose project `bk-lite-apm`，也没有改 `deploy/apm/.env`。结束后这些 project 的容器、网络和卷都已删除。

- `make -C deploy/apm test validate`：退出码 0。三个 Go 包为 cached ok。`compose config --quiet` 通过。镜像构建后校验通过；聚合配置在写入地址为空时报 `invalid endpoint`，分片为空时报 external labels 为空。
- 配置契约：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb uv run pytest -q apps/apm/tests/test_data_plane_config.py --no-cov -o addopts= -p no:cacheprovider`：13 passed in 0.43s。改完 `contract` 目标后再跑同一命令：13 passed in 0.11s。本机 `server/.env` 的 `INSTALL_APPS` 不含 cmdb，不补这组变量时 Django 启动会在 `AutoRelationPending` 处失败，测试还没跑到断言。
- 第一次 `make -C deploy/apm contract`（同上 Django 变量，改 Makefile 之前）：退出码 2。数据面用例通过，随后 4 个聚合用例在 setup 报 `AttributeError: module 'django.core.mail' has no attribute 'outbox'`。数据面用例中途 `django.setup()`，pytest-django 的 mailbox fixture 在下一条用例执行，默认 SMTP 后端没有 `outbox`。聚合容器没有被这次失败拉起。
- 因此 `deploy/apm/Makefile` 的 `contract` 改为 `-p no:django --noconftest -o addopts=`。重跑 `make -C deploy/apm contract`（同样的 Django 变量，因为数据面用例自己会 `django.setup()`）：5 passed, 4 warnings in 261.97s。包含 VictoriaTraces 停止期间 4 条入口 Span 只计 4 次、恢复后明细 spans=rows=4 且计数仍是 4；聚合库不可达时两个 consumer 都 ACK 且明细不重复；重启聚合进程后 `increase()` 从 3 到 4；基数溢出和多实例合并仍在。

