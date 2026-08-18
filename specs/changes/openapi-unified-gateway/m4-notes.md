# M4 实现备忘（部署侧，跨仓库）

部署侧改动落在 bklite-website 仓库（deploy 编排与 wxc 的所在地），
commit `8c054cc`（分支 claude/webhookd-traefik-openapi-gateway-14ea9d）。

## 落地内容

1. **Traefik（compose/infra.yaml）**：新增 `providers.http` 指向
   `http://server:8000/openapi/v1/_provider/traefik`，5s 轮询，
   `X-Provider-Token` 头鉴权（Traefik 3.6.24，v3 支持 providers.http.headers）。
2. **内部入口路由（compose/server.yaml labels）**：`PathPrefix(/openapi/v1)`
   priority 15 → 复用 sidecar 服务（server:8000）；`openapi-clear-inbound`
   中间件在第一跳清除入站 `X-BK-User` / `X-BK-Team` / `X-BK-Gateway-Auth`
   （安全红线 1）。外部服务路由与其专属中间件由 providers.http 动态下发，
   与静态路由互不依赖（无跨 provider 中间件引用）。
3. **server 环境变量**：`OPENAPI_PROVIDER_TOKEN`（bootstrap 新装随机生成 +
   存量 ensure 路径单独补写）、`OPENAPI_AUTH_ADDRESS`（compose 网络内回环
   到 server 自身 `_auth`）、`OPENAPI_BASEURL_ALLOWLIST`（缺省空 =
   拒绝一切外部条目，部署者按需配置，fail-closed）。
4. **wxc openapi 子命令组**（`deploy/wxc/cmd/openapi.go` +
   `internal/openapi/`，新增依赖 nats.go）：
   - `validate`：条目写前预检（与 server 渲染器同规则的结构校验；ref
     可解析性与允许清单由 server 权威判定，输出中明示）；
   - `register`：预检 → NATS KV 写入（TLS + 凭据，bucket 惰性创建）→
     `--probe host:port` 直连探测（红线 3「注册即封锁直连」的自动化验收，
     可达即输出告警）；
   - `list`：列出条目与本地预检状态。
   NATS 连接参数 flags 优先、env（NATS_URL / NATS_ADMIN_USERNAME /
   NATS_ADMIN_PASSWORD / NATS_CA_FILE）兜底。

## 真机验证（10.10.41.149，HA 主节点 /opt/bk-lite/deploy/docker-compose-ha）

- TLS + 管理凭据连接中心 NATS 成功；bucket `openapi_registry` 惰性创建；
- 条目写入、覆盖写、list 展示（含 enabled 与预检状态列）全部符合预期；
- 直连探测双向验证：可达端口（127.0.0.1:443）→ 告警；不可达端口 → 通过；
- 收尾：验证条目已覆盖为 `enabled: false`（渲染器对 disabled 条目静默跳过，
  零告警噪音），临时二进制与文件已清理。

## 遗留与待联调

1. **端到端联调**：.149 运行的是发布版 server 镜像（无 M1-M3 代码），
   provider 渲染端点与 `_auth` 尚不可用——traefik providers.http 在新版
   server 发布前会拉取失败（Traefik 行为：保留最后已知配置，仅日志告警，
   不影响既有路由）。bk-lite PR #4864 合入发版后做完整链路联调
   （KV 注册 → 动态路由生效 → ForwardAuth → 反代 ITSM）。
2. **Traefik errors 中间件**（429/502 同构 JSON envelope，冻结清单第 5 条
   的 Traefik 层承诺）：需 server 提供静态错误体端点后在 compose 配置，
   本期未落，列为发版联调时一并补齐。
3. **ITSM 真实接入**：.149 当前无 itsm 容器；正式接入时按 design.md 3.5.5
   配置 ITSM 侧身份处理中间件与共享密钥，`register --probe` 指向其真实端口。
4. CODEOWNERS owner 确认、design.md 3.8 错误码回填（TIMEOUT /
   BUSINESS_REJECTED）仍在待办（见 m1-notes.md / m3-notes.md）。
