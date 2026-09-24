# RUM 数据面验收清单

本文是给运维的**验收与约束清单**，不是发布流水线设计文档。RUM 从未在 BK-Lite
正式部署；首次上线没有旧 RUM 数据面可恢复。生产编排方式自选，但必须满足下列契约。

正式链路：

```text
Browser
  -> RUM public gateway (:4319 collect / :4320 replay)
  -> Redis admission (ops:rum:v2:*) + VictoriaLogs/Traces + MinIO
Django apps.rum
  -> NATS rum.v1.control.* -> bklite-rum-controller
  -> bklite-rum-maintainer (erase + replay reconcile)
```

契约夹具见 [README.md](./README.md)。本地/CI 可用 `cd deploy/rum && make up|validate|test`
证明语义，不能替代生产验收。**不得**把 APM OTLP 4318 暴露给浏览器。

## 上线前必须为真

1. 使用 `deploy/rum/collector` 构建的固定版本镜像（gateway / controller / maintainer）
   已进入生产镜像仓库；tag 存在且非 `latest`。
2. 已接受 ADR 0009（RUM 公网入口）与 ADR 0010（启用 RUM 时 Redis 硬依赖）。
3. Redis 已按身份拆分 ACL 用户（至少）：`rum-admission`、`rum-sessionizer`、
   `rum-replay-exporter`、`rum-controller`、`rum-maintainer`、
   `rum-replay-index-maintainer`；密钥未进仓库与日志。
4. NATS 控制面身份分离：BFF/ctl 仅可 publish `rum.v1.control.>` + inbox；
   controller 仅可 subscribe `rum.v1.control.>` + publish inbox；与 APM/agents
   subject 隔离。
5. Edge 仅公开发布 `/rum/v1/collect` 与 `/rum/v1/replay`（或等价路径）；APM 4318
   仍仅受信区域内网可达。
6. VictoriaLogs / VictoriaTraces / MinIO（`rum-replay` bucket）写入、健康与保留期
   告警可用；无 ClickHouse。
7. Server 已在 `INSTALL_APPS` 启用 `rum`，并注入运行期 NATS / 查询 endpoint；
   数据面不可用时 API 返回 `controlUnavailable` / `analyticsUnavailable`，不伪装空数据。
8. 预发布环境已保存 `make validate` / `make test`、镜像 digest 与一次 Browser Key
   冒烟（collect 401/403 拒收 + 合法 Origin 接受）结果。

## 就绪顺序（逻辑依赖，非流水线步骤）

1. **Redis + ACL 就绪**：`ops:rum:v2:*` 命名空间可写；各运行身份密码/文件注入完成。
2. **NATS 控制面就绪**：`rum.v1.control.*` subject ACL 生效；controller queue group
   `rum-controller` 可订阅。
3. **VictoriaLogs / VictoriaTraces / MinIO 就绪**：OTLP/HTTP insert 与对象读写可用。
4. **Gateway 就绪**：`:4319` / `:4320` 健康；admission 拒绝坏 Key/Origin；队列目录可写。
5. **Controller / Maintainer 就绪**：status.get 可达；erase / reconcile 循环可观测。
6. **真实浏览器验收**：应用创建 → snippet → Faro collect → VL 可查；可选 replay 段写入 MinIO。
7. **故障恢复验收**：断 Redis / 断 VL / 断 NATS；核对拒收、降级标志、积压与恢复后排空。
8. **Server/Web 开放**：15 个 `/rum/*` 路由与 `/api/v1/rum/*` 在控制面不可用时仍可启动并显示 degraded。

## 完成判定

- 公网仅 RUM collect/replay；APM 4318 未对浏览器开放。
- Redis / NATS 身份分离；秘密未进日志、Span 或仓库。
- 无 ClickHouse；分析走 VictoriaLogs，Trace 证据走 VictoriaTraces，Replay 走 MinIO。
- Compliance erase 以 Postgres `rum_erase_jobs` 为账本，并由 maintainer 执行数据面擦除。
- 故障演练下非法流量持续拒收；合法流量在依赖恢复后可继续摄入。

## 回滚约束

若任一门禁或验收失败：

1. 关闭 Edge 上 RUM collect/replay 发布；停止未验收的 gateway / controller / maintainer。
2. 若 Server/Web 已开放 RUM，回退本次应用发布或从 `INSTALL_APPS` 移除 `rum`；不得影响
   Monitor / Log / APM。
3. 组件问题只回退到本次已验证的前一个候选 digest；没有已验证候选时停止对应进程，
   **不得**临时把浏览器流量导向 APM 4318 或其他接收代理。
4. 保留 Redis `ops:rum:v2:*`、VictoriaLogs/Traces 已写数据与 MinIO replay 对象，
   不清空、不手工重复发布。
5. 删除 Redis 键空间、VL/VT 卷、MinIO bucket、NATS 凭据或缩短保留期须独立显式审批。
6. 记录失败组件、digest、首个失败指标与回滚动作，通过同一验收清单后再重试。

回滚目标是安全关闭或回退本次首次上线版本，不得临时引入正式链路之外的组件。
