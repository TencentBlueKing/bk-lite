# RUM 部署清单（运维）

正式验收见 [ACCEPTANCE.md](./ACCEPTANCE.md)。本地夹具见 [compose.yaml](./compose.yaml)，不是生产编排；
`--profile dataplane` 下三个进程的完整启动参数可直接参照。

## 镜像

| 项 | 值 |
| --- | --- |
| Dockerfile | `deploy/rum/collector/Dockerfile`（构建上下文 `deploy/rum/collector`） |
| 构建 | `cd deploy/rum/collector && docker build -t <仓库>/bklite/rum-collector:<tag> .` |
| 默认 tag | `bklite/rum-collector:0.1.0-bklite.1`（生产用固定 tag，禁止 `latest`） |
| 构建参数 | `GO_IMAGE`（默认 `public.ecr.aws/docker/library/golang:1.26.8-alpine`）、`GOPROXY`（默认 `https://goproxy.cn,direct`） |
| 内容 | 一个镜像三个二进制，`/usr/local/bin/bklite-rum-{gateway,controller,maintainer}`；无 shell（scratch） |
| 运行用户 | `65532:65532`；密钥文件与队列目录须归该用户 |

镜像构建、推送与发布流水线由运维自有平台完成（同 APM）。

## 进程启动

三个进程用同一镜像，靠 entrypoint 区分；均为常驻进程，挂 `restart`。

| 进程 | entrypoint | 端口 | 挂载 |
| --- | --- | --- | --- |
| Gateway | `bklite-rum-gateway --config=/etc/bklite-rum/rum.gateway.yaml` | 4319 collect、4320 replay（经 Edge 公网）；13135 健康、8888 指标（仅内网） | `/run/secrets`（只读）、`/var/lib/core-rum`（持久卷，可写） |
| Controller | `bklite-rum-controller <flags>` | 无入站端口 | `/run/secrets`（只读） |
| Maintainer | `bklite-rum-maintainer <flags>` | 9090 指标（仅内网） | `/run/secrets`（只读） |

Gateway 用环境变量：`RUM_ADMISSION_REDIS_URL`、`RUM_SESSION_REDIS_URL`、`RUM_REPLAY_REDIS_URL`（URL 只带用户名，不带密码）、
`RUM_VICTORIA_LOGS_ENDPOINT`、`RUM_VICTORIA_TRACES_ENDPOINT`、`RUM_MINIO_ENDPOINT`、`RUM_MINIO_ACCESS_KEY`、
`RUM_MINIO_SECURE`、`RUM_IDENTITY_HMAC_CURRENT_VERSION`、`RUM_IDENTITY_HMAC_PREVIOUS_VERSION`。

Controller / Maintainer 用命令行参数，见 compose 中 `rum-controller` / `rum-maintainer` 的 `command`。
Maintainer 必填 `-replay-index-epoch`（RFC3339 格式的回放索引切换时刻，填首次上线时间，例如 `2026-10-10T00:00:00Z`）。

### 密钥文件（`/run/secrets/`，权限 0400/0600，属主 65532）

| 文件 | 使用方 | 要求 |
| --- | --- | --- |
| `rum_identity_hmac_current` | Gateway、Controller | ≥32 字节；两者必须同一个值 |
| `rum_identity_hmac_previous` | Gateway、Controller | 可为空文件；轮换时填旧值 |
| `rum_admission_redis_password` | Gateway | Redis 用户 `rum-admission` |
| `rum_sessionizer_redis_password` | Gateway | Redis 用户 `rum-sessionizer` |
| `rum_replay_exporter_redis_password` | Gateway | Redis 用户 `rum-replay-exporter` |
| `rum_gateway_minio_secret` | Gateway | MinIO secret key |
| `rum_controller_redis_password` | Controller | ≥16 字符；Redis 用户 `rum-controller` |
| `rum_maintainer_redis_password` | Maintainer | Redis 用户 `rum-maintainer` |
| `rum_replay_index_maintainer_redis_password` | Maintainer | Redis 用户 `rum-replay-index-maintainer` |
| `rum_maintainer_minio_secret` | Maintainer | MinIO secret key；access key 不能是 `minioadmin` |

生产 Controller 连 NATS 必须 `tls://` + NKey/creds，**去掉** `-nats-insecure`（仅本地夹具使用）。

### 启动成功判据

| 进程 | 判据 |
| --- | --- |
| Gateway | 日志 `Everything is ready`；`GET :13135/` 返回 200 |
| Controller | 日志 `bklite-rum-controller ready queue=rum-controller`；RUM 应用页不再提示控制面不可用 |
| Maintainer | 日志 `bklite-rum-maintainer ready`；`:9090/metrics` 中 `core_rum_operational_metrics_up 1` |

本地一键验证：`cd deploy/rum && make up-all`（构建镜像并拉起依赖 + 三个进程），`make down` 清理。

## 服务

| 服务 | 首发 | 说明 |
| --- | --- | --- |
| Redis（ACL） | 必须 | 准入 / session / 回放索引 / 控制态 |
| NATS | 必须 | Django ↔ Controller |
| VictoriaLogs | 必须 | 分析查询（擦除需 `-delete.enable`） |
| VictoriaTraces | 必须 | Trace（擦除需 `-delete.enable`） |
| MinIO（bucket `rum-replay`） | 回放/擦除要 | 回放对象 |
| `bklite-rum-gateway`（:4319 / :4320） | 必须 | 浏览器收数 |
| `bklite-rum-controller` | 必须 | 控制面；不起则应用目录不可达 |
| `bklite-rum-maintainer` | 擦除/长期回放要 | 擦除 + 对账 |
| Server（`INSTALL_APPS` 含 `rum`） | 必须 | 配下表变量 |
| Edge | 必须 | 公网只放行 `/rum/v1/collect`、`/rum/v1/replay` |

### 身份

| 组件 | 用户 / ACL |
| --- | --- |
| NATS | Server：`rum_ctl`（publish）；Controller：`rum_controller`（subscribe） |
| Redis | `rum-admission`、`rum-sessionizer`、`rum-replay-exporter`、`rum-controller`、`rum-maintainer`、`rum-replay-index-maintainer` |

## Server 变量

参考：`server/support-files/env/.env.rum.example`

| 变量 | 必要 | 说明 |
| --- | --- | --- |
| `RUM_NATS_URL` | 必须 | `nats://rum_ctl:***@nats:4222` |
| `RUM_VICTORIA_LOGS_URL` | 必须 | VictoriaLogs 地址 |
| `RUM_VICTORIA_TRACES_URL` | 必须 | VictoriaTraces 地址 |
| `RUM_COLLECT_URL` | 必须 | 公网 collect URL |
| `RUM_REPLAY_URL` | 必须 | 公网 replay URL |
| `RUM_SDK_CDN_URL` | 必须 | SDK 地址 |
| `RUM_REPLAY_SIGNING_SECRET` | 回放要 | ≥32 字符 |
| `RUM_REPLAY_INDEX_REDIS_URL` | 回放要 | 一般 Redis DB2 |
| `RUM_MINIO_ENDPOINT` | 回放要 | |
| `RUM_MINIO_ACCESS_KEY` | 回放要 | |
| `RUM_MINIO_SECRET_KEY` | 回放要 | |
| `RUM_MINIO_SECURE` | 建议 | 生产 `true` |
| `RUM_MINIO_BUCKET` | 可选 | 默认 `rum-replay` |
| `RUM_TENANT_ID` | 可选 | 默认 `core` |
| `RUM_NATS_TIMEOUT_SECONDS` | 可选 | 默认 `5` |
| `RUM_VICTORIA_ACCOUNT_ID` | 可选 | 默认 `0` |
| `RUM_VICTORIA_PROJECT_ID` | 可选 | 默认 `0` |
| `RUM_VICTORIA_TIMEOUT_SECONDS` | 可选 | 默认 `15` |

## 数据面进程配置（摘要）

| 进程 | 必要配置 |
| --- | --- |
| Gateway | HMAC（与 Controller 同源）、admission/session/replay Redis、VL/VT、MinIO、`RUM_QUEUE_DIR`；见 `collector/env/rum.gateway.dev.env.example` |
| Controller | NATS、`rum-controller` Redis、HMAC 文件+version、tenant；生产禁用 `nats-insecure`；见 `collector/env/rum.controller.dev.env.example` |
| Maintainer | maintainer Redis、replay-index Redis、`replay-index-epoch`、VL/VT、MinIO；见 `collector/env/rum.maintainer.dev.env.example` |
