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

## 对抗式审查修复（合并前）

四视角对抗式审查 23 条发现 → 17 confirmed（去重后 9 个真问题）→ 已修复如下：

| 项 | 严重度 | 问题 | 修复 |
| --- | --- | --- | --- |
| A1 | high | wxc 内嵌 compose 副本未同步源改动，`TestCommunityInSync` 漂移检测失败 | 跑 `internal/compose/sync.sh` 同步 |
| A2 | high | `OPENAPI_PROVIDER_TOKEN` 只写 common.env、未写 `.env`（compose 唯一插值源），事后任何 `docker compose up -d` 会把令牌插值成空 → provider 端点 503 → 外部路由永久不刷新 | bootstrap.sh 的 `.env` heredoc 补该变量与 `OPENAPI_BASEURL_ALLOWLIST` 占位 |
| A3 | medium | `base_url` 允许清单 `endswith` 无点边界，`evil-itsm-svc` 可绕过 `itsm-svc` | 改为点边界匹配 + 大小写归一，补 6 组参数化回归测试 |
| A4 | medium | `_provider`（渲染结果含下游明文密钥）与 `_auth` 经公网 websecure 入口可达 | Traefik 路由规则排除二者（消费方仅 traefik 自身，走 compose 内网直连） |
| C1 | medium | 冻结清单定义的 `TEAM_OUT_OF_SCOPE`(403) 永不产生，越权被降级为 `BUSINESS_REJECTED`(400) | dispatcher 识别组织越权类软错误映射 403，补正/反两向测试 |
| C2 | medium | `_me.anchor_scopes` 用无权限过滤的全子树展开，向第三方超报可见组织范围 | 改用与 cmdb 同源的 `get_user_authorized_child_groups`，补断言 |

测试：server 侧 79 项全部通过（新增 8 项回归）；wxc `go test ./internal/compose` 转绿、`go build`/`go vet` 干净。

## 新增遗留（审查提出，本期不修）

- **HA 栈（docker-compose-ha + wxc ha bundle）未接入网关**：`wxc ha` 部署的节点无 `/openapi/v1` 路由。与 M4「单机 compose 试点」scope 一致，作为独立事项跟进。
- `OPENAPI_INVOKE_TIMEOUT` 生产未配置且 settings 未接入该 env（README 列为运行期配置但当前为空操作）；开启后线程池 worker 的 DB 连接不随请求周期回收。试点为分页轻查询，发版前处理。
- 试点端点未声明 `permission`（团队决策：维持现状，team 组织自域约束已在）。
- `_me`/`_docs`/`_auth` 未捕获异常经 AppExceptionMiddleware 输出无 `code` 的 500；参数位置混用被静默忽略而非 `SCHEMA_INVALID`；`wxc openapi list` 将服务端会丢弃的条目显示为 ok。

## .149 HA 真机端到端验证（2026-08-18）

镜像：WeOpsx #295（checkout `1568377e` = PR #4864 合并提交），企业版 overlay 后含完整 openapi 包。

验证矩阵（全部经 Traefik 公网入口，HA 栈 bk-primary）：

| # | 场景 | 结果 |
| --- | --- | --- |
| 1 | 无凭据 → 401 `AUTH_INVALID` | ✅ |
| 2 | 错误令牌 → 401 | ✅ |
| 3 | `_me` 结构（user/domain/credential_type/groups/anchor_scopes/roles/services） | ✅ |
| 4 | 本组织 patch-mgmt 调用 → 200 + 真实数据（2 台主机） | ✅ |
| 5 | 越权他组织 → 403 `TEAM_OUT_OF_SCOPE` | ✅（C1 修复生效） |
| 6 | 伪造 `X-BK-User`/`X-BK-Team` → 仍按凭据判定，403 | ✅（红线 1/2） |
| 7 | 未注册端点 → 404 `NOT_FOUND` | ✅ |
| 8 | schema 未知字段 → 400 `SCHEMA_INVALID` | ✅ |
| 9 | `_docs` 聚合（cmdb/patch-mgmt 各 1 端点） | ✅ |
| 10 | `_provider` 经公网入口 → 404（已排除） | ✅（A4 修复生效） |
| 11 | `_provider` 内网：无令牌 401 / 有令牌 200 | ✅ |
| 12 | wxc `validate`/`register`/`list` 写 KV | ✅ |
| 13 | 未配置 secret 的条目被 fail-closed 跳过 | ✅ |
| 14 | 配置 secret 后渲染出 router/service/4 中间件 | ✅ |
| 15 | Traefik 消费动态路由（`openapi-v1-itsm@http` enabled） | ✅ |
| 16 | 端到端调外部服务：无凭据 401 / 有凭据穿透 200 | ✅ |

## 真机验证发现并修复的缺陷

**Traefik 拒绝空 map 导致 http provider 配置整份失效**（renderer.py）：
未注册任何外部服务时渲染器输出 `{"http": {"routers": {}, ...}}`，Traefik 报
`cannot decode configuration data: routers cannot be a standalone element`
并**拒绝整份配置**——连同其中合法的全局中间件一起失效（traefik API 确认
只剩 docker provider 条目）。未注册外部服务是首次部署的常态，故该缺陷在
任何新环境上线即触发，且仅表现为 traefik 日志告警。

修复：空小节一律省略；无路由时全局中间件无引用方，整份返回 `{"http": {}}`。
补专项回归测试（`test_empty_sections_are_omitted_not_empty_maps`）。测试 80 项全过。

## 验证环境遗留（需清理/注意）

- `.149` 的 `server:latest` 现指向验证 tag `openapi-gw-verify` 的镜像；registry
  `latest` 的解析在验证期间仍返回旧 digest（`f0e00057`，疑似 CDN/复制延迟），
  待其收敛后按常规流程重新 `docker pull` 即可。
- `.149` 上遗留：KV 中 `itsm` 测试条目（指向 stargazer）、`.env` 的
  `OPENAPI_BASEURL_ALLOWLIST=stargazer` 与 `ITSM_GW_SECRET`、
  `compose/server.yaml` 的 `ITSM_GW_SECRET` 透传行、验证用户 `gwverify` 及其令牌。
  正式使用前应清理或替换为真实 ITSM 配置。
- registry 中新增 tag `bklite/weopsx/server:openapi-gw-verify`（验证用，可删）。
