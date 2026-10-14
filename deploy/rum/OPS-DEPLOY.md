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

镜像构建、推送与发布流水线由运维自有平台完成（同 APM）。只新打这一个镜像。
Server / Web 仍走现有 WeOpsx，打 `weopsx/server` 与 `weopsx/web`。不要把 Gateway 打进 `fusion-collector`。

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
| `rum_admission_redis_password` | Gateway | Redis 密码；ACL 用户名可选 |
| `rum_sessionizer_redis_password` | Gateway | Redis 密码；ACL 用户名可选 |
| `rum_replay_exporter_redis_password` | Gateway | Redis 密码；ACL 用户名可选 |
| `rum_gateway_minio_secret` | Gateway | MinIO secret key |
| `rum_controller_redis_password` | Controller | ≥16 字符；ACL 用户名可选 |
| `rum_maintainer_redis_password` | Maintainer | 密码文件；ACL 用户名可选 |
| `rum_replay_index_maintainer_redis_password` | Maintainer | Redis 密码或密码文件；ACL 用户名可选 |
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
| Redis（单密码即可） | 必须 | 热路径投影、会话状态、回放索引；ACL / AOF 可选 |
| NATS | 必须 | Django ↔ Controller |
| VictoriaLogs | 必须 | 上游镜像 `victoriametrics/victoria-logs:v1.38.0`，单独一台，与日志那台分开；擦除需 `-delete.enable` |
| VictoriaTraces | 必须 | 上游镜像 `victoriametrics/victoria-traces:v0.9.4`，单独一台，与 APM 那台分开；擦除需 `-delete.enable` |
| MinIO（bucket `rum-replay`） | 回放/擦除要 | 用平台现有 MinIO，只新建 `rum-replay` 桶，不另起实例 |
| `bklite-rum-gateway`（:4319 / :4320） | 必须 | 浏览器收数 |
| `bklite-rum-controller` | 必须 | 控制面；不起则应用目录不可达 |
| `bklite-rum-maintainer` | 擦除/长期回放要 | 擦除 + 对账 |
| Server（`INSTALL_APPS` 含 `rum`） | 必须 | 配下表变量 |
| Edge | 必须 | 现有 Traefik；公网只放行 `/rum/v1/collect`、`/rum/v1/replay` |

### Edge

Edge 是平台现有的公网反向代理（Traefik），不是 RUM 要新打的镜像，也不进 `bklite/rum-collector`。浏览器只访问控制台域名的 `443`，证书沿用平台现有证书，不新开域名，也不把 `4319` / `4320` 直接公布到公网。

在现有 `443` 入口上加两条路由。它们必须比控制台的总路由更优先，否则请求会先落到 Web，到不了 Gateway。不要套 OpenAPI 的登录校验；Browser Key 和 Origin 由 Gateway 自己检查。

| 公网路径 | 转到 | 说明 |
| --- | --- | --- |
| `/rum/v1/collect` | Gateway 内网 `:4319` | 性能、错误、会话上报 |
| `/rum/v1/replay` | Gateway 内网 `:4320` | 会话回放分段 |

`/rum/bklite-rum-sdk.js` 和 `/rum/bklite-rum-replay.js` 不用单独配路由，由现有 Web 服务返回。接入片段默认使用操作员打开控制台的地址加上面的路径。只有收数故意放到另一个域名时，才设置 `RUM_PUBLIC_ORIGIN`，并让该域名的 `443` 做同样的两条转发。

健康检查 `:13135`、指标 `:8888`、VictoriaLogs、VictoriaTraces、Redis、NATS 只留在内网。APM 的 `:4318` 不从这条公网入口发布。

### 身份

| 组件 | 用户 / ACL |
| --- | --- |
| NATS | Server：`rum_ctl`（publish）；Controller：`rum_controller`（subscribe） |
| Redis | 默认同一个密码。需要 ACL 时再打开 `redis_require_acl_identity`，用户名用 `redis_acl_username`（默认仍是各组件原来的名字） |

## Server 变量

参考：`server/support-files/env/.env.rum.example`

| 变量 | 必要 | 说明 |
| --- | --- | --- |
| `RUM_NATS_URL` | 必须 | 生产使用 `tls://nats:4222`，URL 里不要写用户名和密码。不配置或格式不对时，控制面显示不可用，Django 仍能启动 |
| `RUM_NATS_INSECURE` | 仅本地 | 设为 `true` 才接受 `nats://`，以及本地把口令写在 URL 里的写法。生产不要打开 |
| `RUM_VICTORIA_LOGS_URL` | 必须 | VictoriaLogs 地址 |
| `RUM_VICTORIA_TRACES_URL` | 必须 | VictoriaTraces 地址 |
| `RUM_PUBLIC_ORIGIN` | 可选 | 浏览器上报使用的对外源（`https://主机`，不含路径）。不设时，接入片段用操作员打开控制台的地址，路径固定为 `/rum/v1/collect`、`/rum/v1/replay`、`/rum/bklite-rum-sdk.js`。Edge 把前两条转到 Gateway `:4319`、`:4320` |
| `RUM_REPLAY_SIGNING_SECRET` | 回放要 | ≥32 字符 |
| `RUM_REPLAY_INDEX_REDIS_URL` | 回放要 | 一般 Redis DB2 |
| `RUM_TENANT_ID` | 可选 | 默认 `core` |
| `RUM_NATS_TIMEOUT_SECONDS` | 可选 | 默认 `5` |
| `RUM_VICTORIA_ACCOUNT_ID` | 可选 | 默认 `0` |
| `RUM_VICTORIA_PROJECT_ID` | 可选 | 默认 `0` |
| `RUM_VICTORIA_TIMEOUT_SECONDS` | 可选 | 默认 `15` |

回放对象不另设 `RUM_MINIO_*`。Django 用平台 `MINIO_*` 读取 `rum-replay`。Gateway 和 Maintainer 仍用各自的 `RUM_MINIO_*`。

## 数据面进程配置（摘要）

| 进程 | 必要配置 |
| --- | --- |
| Gateway | HMAC（与 Controller 同源）、admission/session/replay Redis、VL/VT、MinIO、`RUM_QUEUE_DIR`；见 `collector/env/rum.gateway.dev.env.example` |
| Controller | NATS、`rum-controller` Redis、HMAC 文件+version、tenant；生产禁用 `nats-insecure`；见 `collector/env/rum.controller.dev.env.example` |
| Maintainer | maintainer Redis、replay-index Redis、`replay-index-epoch`、VL/VT、MinIO；见 `collector/env/rum.maintainer.dev.env.example` |

## 从旧投影升级

首次上线没有旧 RUM 数据面，跳过本节。

这一版起，应用配置的权威在业务库，Redis 只保留可重建投影。升级前 Redis 里的 `ops:rum:v2:app:*` 不会被导入：Browser Key 明文无法从摘要还原。

按这个顺序做：

1. 先升级 Server 并执行迁移。此时不要指望旧 Redis 应用自动出现在产品里。
2. 在产品里按现网应用重新创建，拿到新的 Browser Key，并更新已部署页面的接入片段。创建会先写入业务库和 outbox。
3. 再升级 Controller。它启动后发布 outbox，把业务库里的投影写入 Redis。
4. 确认新应用已经能收数之后，再让对账清理旧键。业务库目录为空时，对账不会删除 Redis 里的应用，避免升级瞬间把现网准入投影清掉。目录里至少有一个应用后，对账会删除业务库中不存在的 `ops:rum:v2:app:<name>` 及其 `:keys`、`:origins`、`:key_material`。
5. 若已经删掉全部应用，空目录不会再清理最后残留的 Redis 键。确认没有流量依赖后，手工删除剩余的 `ops:rum:v2:app:*`。

数据库回滚后，Redis 里的 revision 可能比业务库更高。普通发布会把它视为过期并跳过；下一次对账会用业务库的当前版本强制覆盖 Redis，并清掉旧的 `:key_material`。相等或更旧的普通发布仍然视为过期，不会回写。
