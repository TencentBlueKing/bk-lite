# BK-Lite RUM 数据面契约夹具

本目录**不是**生产编排手册。它只提供：

1. **硬契约**：公开 Faro/Replay 入口、Redis ACL 身份、NATS `rum.v1.control.*`、VictoriaLogs/Traces、MinIO replay；
2. **产品自有组件**：`collector/` 中的 `bklite-rum-{gateway,controller,maintainer}`；
3. **可重复验证**：本地/CI 用 Compose 拉起依赖，并用 Makefile 证明二进制与配置可构建。

正式链路：

```text
Browser (Faro 2.8.2 / bklite-rum-sdk)
  -> POST :4319/rum/v1/collect  (Browser Key + Origin + Redis Lua admission)
  -> POST :4320/rum/v1/replay
  -> rumsession / rum_victoria / rum_replay
  -> VictoriaLogs + VictoriaTraces + MinIO + Redis ops:rum:v2:*

Django apps.rum
  -> NATS rum.v1.control.*
  -> bklite-rum-controller -> Redis
  -> bklite-rum-maintainer (erase + replay reconcile)
```

RUM 公网入口独立于 APM ADR 0008（4318 受信内网）。见
[ADR 0009](../../docs/adr/0009-rum-public-gateway.md)、
[ADR 0010](../../docs/adr/0010-rum-requires-redis.md)。

## 目录

| 路径 | 归属 | 说明 |
| --- | --- | --- |
| `collector/` | 研发（产品组件） | Go 数据面（gateway / controller / maintainer） |
| `collector/Dockerfile` | 研发（产品组件） | 单镜像 `bklite/rum-collector`，内含三个二进制与生产 gateway 配置 |
| `collector/otel/rum.gateway.yaml` | 研发（契约参考配置） | 生产 gateway 配置，已打进镜像 `/etc/bklite-rum/` |
| `packages/bklite-rum-sdk` | 研发 | 浏览器 Faro transport（由上游 `core-rum-sdk` 重命名） |
| `compose.yaml` + `.env.example` | 契约夹具 | 本地依赖（Redis ACL、NATS、VL、VT、MinIO）；`dataplane` profile 追加三个进程 |
| `redis/` / `nats/` | 契约夹具 | 本地最小权限示例，**不是**生产凭据 |
| `OPS-DEPLOY.md` | 运维 | 服务、镜像、进程参数、密钥文件、Server 变量清单 |
| `ACCEPTANCE.md` | 运维 | 上线验收与回滚约束 |
| `Makefile` | 契约夹具 | `up` / `up-all` / `down` / `validate` / `test` / `image` |

## 本地验证

```bash
cd deploy/rum
make up          # 仅拉起依赖夹具（宿主机跑二进制时用）
make up-all      # 构建镜像并拉起依赖 + gateway / controller / maintainer
make validate    # compose config + gateway validate-config + builds
make test        # collector unit tests
make image       # 仅构建 bklite/rum-collector 镜像
make down
```

`up-all` 会占用宿主机 4319 / 4320 / 13135；本机已有 gateway 进程时先停掉，或用
`RUM_GATEWAY_COLLECT_PORT` 等变量改端口（见 `.env.example`）。

通过夹具不等于完成生产上线。生产编排、镜像流水线、容量与值班由运维自有平台落地，但必须满足 [ACCEPTANCE.md](./ACCEPTANCE.md)。
