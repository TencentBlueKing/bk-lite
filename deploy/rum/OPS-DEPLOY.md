# RUM 部署清单

本文按流水线顺序写怎么做。过不过看 [ACCEPTANCE.md](./ACCEPTANCE.md)。
`compose.yaml` 只供本地验证，里面的 `-nats-insecure` 和写进口令的 URL 不能抄进生产。

## 边界

做这些：

- 新打一个镜像 `bklite/rum-collector`，跑 Gateway、Controller、Maintainer。
- 在平台现有 NATS、MinIO、Edge、Server 上追加 RUM 需要的账号、桶、路由和环境变量。

不做这些：

- 不另做 Server / Web 流水线。镜像仍是 `weopsx/server`、`weopsx/web`。
- 不改监控、日志、APM 的镜像、端口和启动顺序。
- 不把 Gateway 打进 `fusion-collector`，不另起一台 NATS，不新开域名。
- 不在 `batch_init` 或 `startup.sh` 里等待 NATS、Redis、VictoriaLogs 或 Gateway。数据面没就绪时页面显示不可用，Django 仍能启动。

发布失败时先关掉 Edge 上的两条 RUM 路由，再停三个进程。详细回滚见验收清单。

## 1. 构建镜像

| 项 | 值 |
| --- | --- |
| Dockerfile | `deploy/rum/collector/Dockerfile` |
| 构建上下文 | `deploy/rum/collector` |
| 默认 tag | `bklite/rum-collector:0.1.0-bklite.1` |
| 构建参数 | `GO_IMAGE` 默认 `public.ecr.aws/docker/library/golang:1.26.10-alpine`；`GOPROXY` 默认 `https://goproxy.cn,direct` |
| 镜像内容 | 三个二进制，以及 `/etc/bklite-rum/rum.gateway.yaml` |
| 运行用户 | `65532:65532`。镜像没有 shell，不能自己改目录属主 |

tag 必须固定，禁止 `latest`。记下 digest，回滚只回到上一个已验收的 digest。

```bash
docker build \
  -f deploy/rum/collector/Dockerfile \
  -t <仓库>/bklite/rum-collector:<tag> \
  deploy/rum/collector
```

## 2. 准备依赖

| 服务 | 要求 |
| --- | --- |
| Redis | 用平台现有实例，不另起。投影、会话、回放索引各用一个库号，不要和 `REDIS_CACHE_URL` 用同一个库号。密码沿用这台 Redis 的现有密码 |
| VictoriaLogs | `victoriametrics/victoria-logs:v1.38.0`，单独一台，不用日志产品那台。参数含 `-delete.enable`，监听 `:9428` |
| VictoriaTraces | `victoriametrics/victoria-traces:v0.9.4`，单独一台，不用 APM 那台。参数含 `-delete.enable`，监听 `:10428` |
| MinIO | 用平台现有实例，只新建桶 `rum-replay`。Gateway 的 access key 可写，Server 的 `MINIO_*` 可读 |

健康检查只走内网：VictoriaLogs 和 VictoriaTraces 都是 `GET /health`。

## 3. 新建 NATS 账号

用平台现有那一台 NATS，不另起。地址就是 Server 的 `NATS_SERVERS`。RUM 不用 JetStream。

新建两个用户，只给 RUM。不要复用 `NATS_USER`、管理员账号或其他应用的账号。两个口令分别新生成，不写进仓库，也不写进 URL。

| 用户 | 交给谁 | 可以发布 | 可以订阅 | 发布和订阅都拒绝 |
| --- | --- | --- | --- | --- |
| `rum_ctl` | Server，环境变量 `RUM_NATS_USER` / `RUM_NATS_PASSWORD` | 仅 `rum.v1.control.>` | 仅 `_INBOX.>` | `agents.v1.>`、`otel.v1.>`、`apm.>`，也不能订阅 `rum.v1.control.>` |
| `rum_controller` | Controller，口令放第 4 节的密码文件 | 仅 `_INBOX.>` | `rum.v1.control.>` 和 `_INBOX.>` | `agents.v1.>`、`otel.v1.>`、`apm.>` |

`rum_ctl` 只负责把控制命令发出去，不能听控制主题。`rum_controller` 只负责听这些命令并回复，不能用控制主题对外发布。两边都不能碰监控、日志、节点和 APM 的主题。

Controller 的 `-nats-url` 必须是 `tls://`，主机和端口与 `NATS_SERVERS` 相同，去掉里面的账号。平台 NATS 仍是明文时，先为它打开 TLS，再启动 Controller。生产不要加 `-nats-insecure`。私有 CA 用平台已有的 `NATS_TLS_CA_FILE`。

## 4. 写入密钥和目录

要新准备的只有两样：一把 HMAC，以及第 3 节新建的 `rum_controller` 口令。Redis 密码和 MinIO secret 用平台现有的，不要另造。`rum_ctl` 的口令只放进 Server 环境变量，不放文件。

文件多，是因为镜像里的配置写死了路径，进程不从环境变量读口令。同一份内容抄到下表对应的文件即可。全部放在 `/run/secrets/`，权限 `0400`，属主 `65532:65532`。镜像没有 shell，启动前写好。

| 实际内容 | 抄到这些文件 |
| --- | --- |
| 新生成的 HMAC，至少 32 字节。Gateway 和 Controller 必须是同一把 | `rum_identity_hmac_current` |
| 空文件。首发还没有上一版 HMAC，这个路径必须存在 | `rum_identity_hmac_previous` |
| 第 3 节新建的 `rum_controller` 口令 | `rum_controller_nats_password` |
| 平台 Redis 的现有密码。Gateway 要求这份内容为 16 到 256 个字符；更短时改这台 Redis 的密码，不另起实例 | `rum_admission_redis_password`、`rum_sessionizer_redis_password`、`rum_replay_exporter_redis_password`、`rum_controller_redis_password`、`rum_maintainer_redis_password`、`rum_replay_index_maintainer_redis_password` |
| 平台 MinIO 的现有 secret。access key 用平台现有的，不能是 `minioadmin`。Django 不用这些文件，它读已有的 `MINIO_SECRET_KEY` | `rum_gateway_minio_secret`、`rum_maintainer_minio_secret` |

另外准备 Gateway 的队列目录 `/var/lib/core-rum`。这是持久卷，权限 `0700`，属主 `65532:65532`。VictoriaLogs 暂时不可用时，上报先堆在这里。

进程 URL 里不写 Redis 或 NATS 口令。

## 5. 启动三个进程

三个进程用同一镜像，常驻并自动重启。内存可以按 Gateway 768Mi、Controller 256Mi、Maintainer 256Mi 起步。Redis 地址不写用户名，口令用第 4 节的文件。

### Gateway

```text
/usr/local/bin/bklite-rum-gateway --config=/etc/bklite-rum/rum.gateway.yaml
```

配置已在镜像里。环境变量：

| 变量 | 值 |
| --- | --- |
| `RUM_IDENTITY_HMAC_CURRENT_VERSION` | `v1` |
| `RUM_IDENTITY_HMAC_PREVIOUS_VERSION` | 首发留空 |
| `RUM_ADMISSION_REDIS_URL` | `redis://<redis>:6379/0` |
| `RUM_SESSION_REDIS_URL` | `redis://<redis>:6379/1` |
| `RUM_REPLAY_REDIS_URL` | `redis://<redis>:6379/2` |
| `RUM_VICTORIA_LOGS_ENDPOINT` | `http://<victoria-logs>:9428` |
| `RUM_VICTORIA_TRACES_ENDPOINT` | `http://<victoria-traces>:10428` |
| `RUM_MINIO_ENDPOINT` | `<minio>:9000` |
| `RUM_MINIO_ACCESS_KEY` | 可写 `rum-replay` 的 access key |
| `RUM_MINIO_SECURE` | 与平台 MinIO 是否走 TLS 一致 |

`4319` 收数，`4320` 回放，只给 Edge 内网访问。`13135` 健康和 `8888` 指标只留内网。

就绪：日志出现 `Everything is ready`，内网 `GET :13135/` 返回 200。容器没有 wget，探针用 HTTP。

### Controller

```text
/usr/local/bin/bklite-rum-controller \
  -nats-url=tls://<与 NATS_SERVERS 相同的主机:端口> \
  -nats-user=rum_controller \
  -nats-password-file=/run/secrets/rum_controller_nats_password \
  -nats-ca=<NATS_TLS_CA_FILE 在容器内的路径> \
  -redis-url=redis://<redis>:6379/0 \
  -redis-password-file=/run/secrets/rum_controller_redis_password \
  -identity-hmac-current-file=/run/secrets/rum_identity_hmac_current \
  -identity-hmac-current-version=v1 \
  -tenant-id=core
```

系统信任库里已有平台 CA 时，去掉 `-nats-ca`。首发不要传 previous 那两个 HMAC 参数。

没有入站端口。就绪：日志 `bklite-rum-controller ready queue=rum-controller`。

### Maintainer

```text
/usr/local/bin/bklite-rum-maintainer \
  -redis-url=redis://<redis>:6379/0 \
  -redis-password-file=/run/secrets/rum_maintainer_redis_password \
  -replay-index-redis-url=redis://<redis>:6379/2 \
  -replay-index-redis-password-file=/run/secrets/rum_replay_index_maintainer_redis_password \
  -replay-index-epoch=<首次上线时刻，RFC3339，例如 2026-10-14T00:00:00Z> \
  -victoria-logs-endpoint=http://<victoria-logs>:9428 \
  -victoria-traces-endpoint=http://<victoria-traces>:10428 \
  -minio-endpoint=<minio>:9000 \
  -minio-secure=<与平台 MINIO_USE_HTTPS 一致> \
  -minio-access-key=<可删除 rum-replay 对象的 access key> \
  -minio-secret-key-file=/run/secrets/rum_maintainer_minio_secret \
  -minio-bucket=rum-replay \
  -metrics-address=0.0.0.0:9090
```

`-replay-index-epoch` 必填，填第一次上线的时间，之后不要改。`:9090` 只留内网。

就绪：日志 `bklite-rum-maintainer ready`，指标 `core_rum_operational_metrics_up 1`。VictoriaLogs 或 VictoriaTraces 没有 `-delete.enable` 时，进程启动失败。

## 6. 发布 Server

用现有 Server 发布追加环境变量。模板是 `server/support-files/env/.env.rum.example`。不要新增 `RUM_NATS_URL` 或 `RUM_NATS_TLS_CA_FILE`。

`INSTALL_APPS` 为空时已经包含 `rum`。现场如果显式列出了应用，把 `rum` 加进去。迁移跟着现有 `migrate`，失败仍按原启动脚本停下。Web 不追加变量。

| 变量 | 必要 | 说明 |
| --- | --- | --- |
| `RUM_NATS_USER` | 是 | `rum_ctl`，必须和 `RUM_NATS_PASSWORD` 成对出现 |
| `RUM_NATS_PASSWORD` | 是 | `rum_ctl` 的口令 |
| `RUM_VICTORIA_LOGS_URL` | 是 | 例如 `http://<victoria-logs>:9428` |
| `RUM_VICTORIA_TRACES_URL` | 是 | 例如 `http://<victoria-traces>:10428` |
| `RUM_REPLAY_SIGNING_SECRET` | 回放要 | 至少 32 字符 |
| `RUM_REPLAY_INDEX_REDIS_URL` | 回放要 | Django 自己的回放索引连接串，DB2 |
| `RUM_PUBLIC_ORIGIN` | 否 | 只在收数域名和控制台不同时设置，见下一节 |
| `RUM_TENANT_ID` | 否 | 默认 `core`，必须与 Controller 的 `-tenant-id` 相同 |
| `RUM_NATS_TIMEOUT_SECONDS` | 否 | 默认 `5` |
| `RUM_VICTORIA_ACCOUNT_ID` | 否 | 默认 `0` |
| `RUM_VICTORIA_PROJECT_ID` | 否 | 默认 `0` |
| `RUM_VICTORIA_TIMEOUT_SECONDS` | 否 | 默认 `15` |

NATS 地址从 `NATS_SERVERS` 取主机，丢掉里面的账号。方案是 `tls://` 时，CA 用 `NATS_TLS_CA_FILE`。只配了用户名或只配了口令时，控制面不可用，Django 仍能启动。

回放对象用平台已有的 `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_USE_HTTPS`。不要给 Django 再配一套 `RUM_MINIO_*`。

## 7. 配置 Edge

用现有 Traefik 和现有证书，浏览器只访问控制台的 `443`。不要把 `4319`、`4320`、`13135`、`8888`、`9090` 公布到公网，也不要从这条入口发布 APM `:4318`。

两条路由必须比现有 `PathPrefix(/)` 更优先，否则请求会先落到 Web。不要套 OpenAPI 或登录校验。

| 公网路径 | 转到 |
| --- | --- |
| `/rum/v1/collect` | `http://<gateway>:4319` |
| `/rum/v1/replay` | `http://<gateway>:4320` |

下面只说明路由形态。流水线改现场配置，不改仓库里的 Edge 文件：

```yaml
http:
  routers:
    rum-collect:
      rule: PathPrefix(`/rum/v1/collect`)
      priority: 100
      entryPoints: [websecure]
      service: rum-gateway-collect
      tls: {}
    rum-replay:
      rule: PathPrefix(`/rum/v1/replay`)
      priority: 100
      entryPoints: [websecure]
      service: rum-gateway-replay
      tls: {}
  services:
    rum-gateway-collect:
      loadBalancer:
        servers:
          - url: http://<gateway>:4319
    rum-gateway-replay:
      loadBalancer:
        servers:
          - url: http://<gateway>:4320
```

`/rum/bklite-rum-sdk.js` 和 `/rum/bklite-rum-replay.js` 继续由 Web 返回。接入片段默认用操作员打开控制台的地址。收数放到另一个域名时，才设置 `RUM_PUBLIC_ORIGIN`（`https://主机`，不含路径），并在该域名的 `443` 上做同样两条转发。

内网冒烟通过后再保留这两条公网路由。

## 8. 冒烟

1. 内网 `GET :13135/` 返回 200。
2. 不带 Browser Key 的 `POST /rum/v1/collect` 被拒绝。
3. 在产品里创建一个应用，Origin 填控制台地址。用该 Browser Key 和这个 Origin 上报一次，VictoriaLogs 能查到。
4. RUM 应用页不再提示控制面不可用。Controller 没启动时，这里必须显示不可用，而不是空列表。
5. 公网扫不到 `:4319`、`:4320`、`:13135`、`:8888`、`:9090` 和 APM `:4318`。

## 以后升级

首次上线没有旧 RUM 数据，跳过本节。

应用配置的权威在业务库，Redis 只保留可重建投影。旧的 `ops:rum:v2:app:*` 不会被导入，因为 Browser Key 明文无法从摘要还原。

1. 先升级 Server 并执行迁移。旧 Redis 应用不会自动出现在产品里。
2. 按现网应用重新创建，拿到新的 Browser Key，并更新已部署页面的接入片段。
3. 再升级 Controller。它启动后把业务库投影写入 Redis。
4. 新应用能收数之后，再让对账清理旧键。业务库里还没有应用时，对账不会删除 Redis 投影。至少有一个应用后，对账删除业务库中不存在的 `ops:rum:v2:app:<name>` 及其 `:keys`、`:origins`、`:key_material`。
5. 应用已经全部删除时，对账不会清掉最后残留的键。确认没有流量依赖后，手工删除剩余的 `ops:rum:v2:app:*`。

数据库回滚后，Redis 里的 revision 可能比业务库更高。普通发布会跳过它；下一次对账用业务库的当前版本覆盖 Redis。
