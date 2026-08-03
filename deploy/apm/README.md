# BK-Lite APM 数据面

该目录是与 Django Server 启动解耦的 APM 运行期部署单元：

- `apm-edge` 对外提供 OTLP/HTTP `POST /v1/traces` 与 OTLP/gRPC
  `TraceService/Export`，两者都通过 Django 机器鉴权接口校验 Bearer Token；
- `apm-collector-queue-init` 以最小能力一次性初始化持久队列卷权限，完成后退出；
- `apm-otel-collector` 在内部提供 OTLP/gRPC 4317 与 OTLP/HTTP 4318；
- `apm-victoria-traces` 默认保存 7 天尾采样 Trace；
- Span Metrics 在尾采样前由全量 Span 生成，并写入既有 VictoriaMetrics。

## 启动

复制 `.env.example` 为部署环境变量来源，并保证 `APM_SERVER_UPSTREAM` 可从容器访问。
默认复用已有 VictoriaMetrics：

```bash
docker compose -f deploy/apm/compose.yaml up -d
```

本地契约测试可启用隔离的 VictoriaMetrics：

```bash
APM_VICTORIAMETRICS_WRITE_ENDPOINT=http://apm-victoriametrics:8428/api/v1/write \
  docker compose -f deploy/apm/compose.yaml --profile standalone-metrics up -d
```

应用使用创建/轮换时仅展示一次的 Token：

```text
Authorization: Bearer <token>
```

默认外部端点为 HTTP `:4318` 和 gRPC `:4317`，可分别用
`APM_OTLP_HTTP_BIND`/`APM_OTLP_HTTP_PORT` 与
`APM_OTLP_GRPC_BIND`/`APM_OTLP_GRPC_PORT` 覆盖。Collector 的内部 4317/4318
只在 Compose 网络暴露，不能绕过 edge 直接从宿主机访问。Collector 的 13133 健康端口
同样不映射到宿主机；edge 的 OTLP/HTTP 入口只读暴露 `/healthz/collector`，用于运行期探测。

边缘代理会移除客户端传入的 `X-BK-Ingest-Source-Id`；Collector 再删除客户端在
Resource、Scope、Span 和 Span Event 中提交的 `bk.*` 属性，并从鉴权结果注入
受信任的 `bk.ingest_source.id`。
正向鉴权结果只在 tmpfs 中缓存 8 秒，并保证撤销延迟不超过 10 秒；未缓存请求在鉴权服务不可用时返回 503。
Trace exporter 使用持久化有界队列；Prometheus Remote Write 使用内存有界队列，
避免后端长期不可用时 WAL 无上限占用磁盘。两条链路的重试最长均为 5 分钟。
Collector 始终以 `10001:10001` 非 root 身份运行；只有无网络、只读根文件系统的
一次性初始化容器拥有队列目录所需的 `CHOWN`、`DAC_OVERRIDE`、`FOWNER` 能力。

Django 运行期目录对账和 RED 查询默认复用 Server 已有的 `VICTORIAMETRICS_HOST`、
`VICTORIAMETRICS_USER`、`VICTORIAMETRICS_PWD` 与 TLS 校验配置；如 APM 需要独立查询入口，
可设置 `APM_VICTORIAMETRICS_QUERY_ENDPOINT`。该配置只在 Celery 对账任务或用户查询时
访问外部存储，不属于 `batch_init` 或 API 进程启动门禁。

Trace 搜索与详情默认查询 `http://127.0.0.1:10428`，可通过
`APM_VICTORIATRACES_QUERY_ENDPOINT` 指向独立 VictoriaTraces/vtselect。可选的
`APM_VICTORIATRACES_USER`、`APM_VICTORIATRACES_PASSWORD`、
`APM_VICTORIATRACES_VERIFY_TLS` 和 `APM_VICTORIATRACES_QUERY_TIMEOUT` 只在用户发起
Trace 查询时生效，同样不属于 Server 启动依赖。

APM 健康接口的 Collector/存储分项由 Celery beat 每分钟做一次 1 秒连接、2 秒响应的
有界运行期探测。Server 运行环境可设置 `APM_COLLECTOR_HEALTH_ENDPOINT`（本地 Compose
示例为 `http://127.0.0.1:4318/healthz/collector`）、
`APM_VICTORIATRACES_HEALTH_ENDPOINT` 和 `APM_VICTORIAMETRICS_HEALTH_ENDPOINT`；
Trace/Metric 未显式设置健康地址时会从查询入口派生同源 `/health`。未配置显示
`pending`，不可达显示 `degraded`，均不阻断 `batch_init` 或 Server 启动。

## 容器契约测试

测试会启动独立 Compose project，验证无/错 Token、10 秒撤销上限、鉴权不可用、
受信来源覆盖，以及采样前 Span Metrics 和尾采样 Trace 两条链路：

```bash
RUN_APM_CONTAINER_CONTRACT=1 \
  server/.venv/bin/python -m pytest -q deploy/apm/tests/test_data_plane_contract.py
```

测试结束会删除自身创建的容器、网络和卷，不操作已有 BK-Lite 服务。

## 边界

该 Compose 不属于 `batch_init` 或 Server Supervisor 依赖。Collector、Trace/Metric
存储不可用时只影响 APM 遥测链路，不阻断 Server 启动。现有 `/telegraf/api` 未被修改。
