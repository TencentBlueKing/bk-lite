# RUM 验收清单

本文只判定过不过。做法、命令和变量见 [OPS-DEPLOY.md](./OPS-DEPLOY.md)。
RUM 没有正式部署过，首次上线没有旧数据面可恢复。

本地夹具可以证明语义，不能代替本清单：

```bash
cd deploy/rum && make up && make validate && make test
```

## 链路

```text
浏览器
  -> Edge 443  /rum/v1/collect、/rum/v1/replay
  -> Gateway   :4319、:4320
  -> Redis 准入 + VictoriaLogs + VictoriaTraces + MinIO rum-replay

控制台
  -> Server apps.rum
  -> 平台 NATS  rum.v1.control.*
  -> Controller
  -> Maintainer 负责擦除和对账
```

APM `:4318` 只在受信内网，不进入这条公网链路。

## 门禁

编号与部署清单的步骤相同。每一条在预发布都要留下证据：命令或配置、镜像 digest、结果。

1. **镜像**。`deploy/rum/collector` 打出的固定 tag 已在生产仓库，不是 `latest`。digest 已记录。
2. **依赖**。用的是平台现有 Redis，带密码且可写，库号不与 `REDIS_CACHE_URL` 相同。VictoriaLogs `v1.38.0`、VictoriaTraces `v0.9.4` 都单独部署，都带 `-delete.enable`，`GET /health` 可用。平台 MinIO 上已有 `rum-replay`，Gateway 可写，Server 可读。没有 ClickHouse。
3. **NATS**。`rum_ctl` 和 `rum_controller` 是新建用户，加在平台现有 NATS 上，没有复用平台账号。权限与部署清单一致，碰不到 `agents.v1.>`、`otel.v1.>`、`apm.>`。Controller 使用 `tls://`，没有 `-nats-insecure`。口令不在 URL、日志和仓库里。
4. **密钥**。新准备的只有 HMAC 和 `rum_controller` 口令。Redis 密码、MinIO secret 用平台现有的。`/run/secrets` 权限 `0400`、属主 `65532`。Gateway 与 Controller 的当前 HMAC 是同一个值，且不少于 32 字节。队列目录 `/var/lib/core-rum` 持久、可写、属主正确。
5. **进程**。Gateway 日志出现 `Everything is ready`，`GET :13135/` 返回 200。Controller 日志出现 `bklite-rum-controller ready queue=rum-controller`。Maintainer 日志出现 `bklite-rum-maintainer ready`，`core_rum_operational_metrics_up 1`。`:13135`、`:8888`、`:9090` 只在内网。
6. **Server**。现有 Server 发布已带上 RUM 变量，`rum` 已安装。缺 NATS、VictoriaLogs 或 Controller 时，接口返回 `controlUnavailable` 或 `analyticsUnavailable`，不显示成空数据，也不挡住 Django 启动。
7. **Edge**。公网只有 `/rum/v1/collect` 和 `/rum/v1/replay`，且优先于控制台总路由。这两条没有登录校验。SDK 脚本仍由 Web 返回。`:4319`、`:4320` 和 APM `:4318` 都不能从公网直接访问。
8. **冒烟**。非法 Browser Key 或 Origin 被拒绝。合法 Origin 上报后，VictoriaLogs 能查到。应用页在 Controller 就绪后不再提示控制面不可用。

ADR 0009（公网入口与 APM 分开）和 ADR 0010（启用 RUM 后 Redis 是运行期硬依赖）保持有效。

## 故障演练

门禁通过后再做。任何一项失败都按回滚处理，不带病开放。

- 断开 Redis：新的非法和合法上报都被拒绝；恢复后合法流量可以继续进入。
- 断开 VictoriaLogs：Gateway 把数据留在 `/var/lib/core-rum`，恢复后积压排空。页面显示分析不可用，不显示成空数据。
- 断开 NATS 或停掉 Controller：应用页显示控制面不可用。Server、监控、日志、APM 仍可启动和使用。

## 完成判定

- 上面 8 条门禁和故障演练都有记录。
- 分析来自 VictoriaLogs，Trace 来自 VictoriaTraces，回放对象在 MinIO。
- 擦除以 Postgres `rum_erase_jobs` 为账本，由 Maintainer 删除数据面里的对应数据。
- 密钥没有出现在日志、Trace 或仓库里。

## 回滚

1. 去掉 Edge 上的两条 RUM 路由，停止未验收的 Gateway、Controller、Maintainer。
2. Server 已开放 RUM 时，回退这次应用发布，或从 `INSTALL_APPS` 去掉 `rum`。不动监控、日志、APM。
3. 只回退到上一个已验收的镜像 digest。没有已验收版本时，停掉对应进程。不要把浏览器流量改到 APM `:4318` 或其他接收端。
4. 保留 Redis `ops:rum:v2:*`、VictoriaLogs、VictoriaTraces 和 `rum-replay` 里已经写下的数据。不清空，也不手工重放。
5. 删除这些数据、NATS 账号，或缩短保留期，要单独审批。
6. 记下失败组件、digest、第一个失败现象和回滚动作。同一清单再次通过后才能重试。
