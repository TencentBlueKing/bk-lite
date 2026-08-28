# OpenAPI 统一网关 · 接入指南

BK-Lite 统一网关把对外 API 收口到 `https://<平台地址>/openapi/v1/<服务名>/*`：调用方只面对一个入口、一种凭据，**认证与审计**由网关统一承担。

> 能力边界（先看这里，避免错误预期）：
> - **限流**目前只对外部服务生效（注册条目的 `rate_limit`），内部接口暂无限流；
> - **调用超时**当前未启用（`OPENAPI_INVOKE_TIMEOUT` 尚未接入配置，属已知遗留），慢接口不会被网关中断；
> - **API 令牌永不过期、无 scope**，令牌权限等于其生成账号的全部权限——务必用专属最小权限账号生成，详见 5.1；
> - 网关本身不做接口级细粒度授权，只有服务级（`required_roles`）与内部端点的权限位。

接入分两条路径，按被接入方形态选择：

| 路径 | 适用 | 面向 | 章节 |
| --- | --- | --- | --- |
| **外部服务接入** | 独立部署的 HTTP 服务（ITSM、审批系统、第三方 / 内网 API） | 平台运维 + 被接入方开发 | 第 1–7 节 |
| **内部接口接入** | BK-Lite 自身各应用（cmdb、monitor、patch_mgmt…）的已有函数 | bk-lite 后端开发 | 第 8 节 |

两者的对外契约一致（同一入口、同一凭据、同一错误码），差别只在注册方式：外部服务写 NATS KV（秒级生效、不发版），内部接口用装饰器声明（随版本发布）。

> 设计依据与契约冻结清单见 `specs/changes/openapi-unified-gateway/design.md`；
> 内部接入的代码级说明另见 `server/apps/core/openapi/README.md`。

---

---

# 第一部分 · 外部服务接入

## 1. 接入前置条件

| 条件 | 说明 |
| --- | --- |
| 服务可达 | 被接入服务与 BK-Lite 在同一 compose / K8s 网络内，Traefik 能以 `base_url` 直连 |
| 服务名 | 满足 `^[a-z][a-z0-9-]{0,31}$`；下划线开头为网关保留（`_me`、`_docs`、`_auth`、`_provider`） |
| 允许清单 | `base_url` 的主机必须落在 `OPENAPI_BASEURL_ALLOWLIST` 内，**缺省为空即拒绝一切**（fail-closed） |
| 身份传递方式 | 二选一，见第 3 节 |
| 网络封锁 | 接入后必须封锁该服务的直连端口，否则统一认证 / 审计 / 限流可被绕过 |
| 客户端工具 | 操作机需有 `docker compose`（v2 语法）、`jq`、`curl`；`wxc` 需为**含 `openapi` 子命令的版本**（`wxc openapi --help` 能出帮助即可），离线环境随部署包分发 |
| HA 环境 | 注册表**不随主备切换复制**，必须主备两端各注册一次，见步骤 3 的 HA 注意事项 |

---

## 2. 接入四步

### 步骤 1：配置允许清单与密钥（server 侧 env）

在部署目录的 `.env` 中配置，然后重建 server 容器：

```bash
cd /opt/bk-lite/deploy/docker-compose-ha   # 单机栈为 .../docker-compose

# 允许清单：逗号分隔的主机名或 IP；后缀匹配按点边界（itsm-svc 不会放行 evil-itsm-svc）
echo 'OPENAPI_BASEURL_ALLOWLIST=itsm-svc,10.10.24.11' >> .env

# 共享密钥（信任头模式用）。变量名自定，注册条目里以 env: 引用它
echo 'ITSM_GW_SECRET=<32位随机串>' >> .env
```

密钥必须能被 **server 容器**读到。若变量名不在 `compose/server.yaml` 的 `environment` 中，需要补一行透传并重新渲染：

```yaml
# compose/server.yaml
    environment:
      - ITSM_GW_SECRET=${ITSM_GW_SECRET:-}
```

该 `environment:` 必须落在 **server 服务**名下（`compose/server.yaml` 的第一个 `environment:` 即是）。

重渲染 `docker-compose.yaml` 时，**`-f` 片段清单必须与本环境一致**：它随部署形态与开关变化（HA 栈才有 `ha.yaml`；单机栈可能有 `mlflow.yaml`；`vllm.yaml` 仅 `VLLM_ENABLED=true` 时加入；外部数据库模式不含 `postgres.yaml`）。**照抄别处的清单会让服务定义丢失或直接报错**。可靠做法是从本机现有 `docker-compose.yaml` 反推：

```bash
# 0) 备份当前运行时编排，出问题可一键回滚
cp docker-compose.yaml docker-compose.yaml.bak-$(date +%s)

# 1) source 全部 env 文件（HA 栈的 COMPOSE_PROJECT_NAME 在 ha.env 里，漏 source
#    会让项目名变化、容器挂到全新空卷，等同数据丢失）
set -a; source common.env; [ -f ha.env ] && source ha.env; source .env; set +a

# 2) 按本机实际存在的片段拼装（与 bootstrap.sh 同源的条件逻辑）
FRAGS=""
for f in infra postgres mlflow monitor server web vllm log ha; do
  [ -f "compose/$f.yaml" ] && grep -q "^ *${f}:\|." "compose/$f.yaml" && FRAGS="$FRAGS -f compose/$f.yaml"
done
# 若本机启用了外部数据库或关闭了 vllm/opspilot，请据实删去对应片段后再执行

# 3) 先渲染到临时文件并 diff，确认只有本次预期的改动（尤其确认项目名与卷名未变）
docker compose $FRAGS config --no-interpolate > /tmp/dc-new.yaml
diff docker-compose.yaml /tmp/dc-new.yaml

# 4) 确认无误后落盘并重建
cp /tmp/dc-new.yaml docker-compose.yaml
docker compose up -d server
```

server 重建需约 1 分钟才就绪，**验证前必须等待**（只 sleep 几秒会得到 404 或 JSON 解析错误）：

```bash
# 容器名随 compose 项目名变化（HA 栈通常为 bk-primary-server-1，单机栈不同），
# 用 compose 自身解析，不要硬编码
SERVER_CID=$(docker compose ps -q server)
for i in $(seq 1 24); do
  docker logs --tail 3 "$SERVER_CID" 2>&1 | grep -q 'Application startup complete' && { echo "server 就绪"; break; }
  [ "$i" = 24 ] && { echo "server 4 分钟未就绪，检查日志：docker logs $SERVER_CID | tail -50"; }
  sleep 10
done
```

**重建失败怎么办**：`docker logs "$SERVER_CID" | tail -50` 看启动异常；配置类问题回滚编排（`cp docker-compose.yaml.bak-* docker-compose.yaml && docker compose up -d server`）；`.env` 改动可直接删除新增行后重跑本步骤。本步骤只重建 server，不影响其他容器与数据卷。

### 步骤 2：编写注册条目

```json
{
  "schema_version": 1,
  "type": "http",
  "base_url": "http://itsm-svc:8000",
  "strip_prefix": true,
  "paths": ["/tickets/*", "/approvals/*"],
  "auth_mode": "trusted-header",
  "shared_secret_ref": "env:ITSM_GW_SECRET",
  "required_roles": [],
  "rate_limit": { "average": 50, "burst": 100 },
  "doc_url": "http://itsm-svc:8000/swagger.json",
  "enabled": true
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `schema_version` | 否 | 固定 `1`，缺省按 1 处理 |
| `type` | 是 | 目前仅 `http` |
| `base_url` | 是 | 上游地址，须过允许清单；末尾斜杠会被去除 |
| `strip_prefix` | 否 | 默认 `true`：转发前去掉 `/openapi/v1/<服务名>` 前缀 |
| `paths` | 否 | 接口级白名单（`/x/*` 形式）；**省略表示该前缀下全部路径都被反代** |
| `auth_mode` | 是 | `trusted-header` 或 `service-token`，见第 3 节 |
| `shared_secret_ref` | 条件 | `trusted-header` 模式必填，形如 `env:VAR`，**只存引用不存明文** |
| `token_ref` | 条件 | `service-token` 模式必填，同上 |
| `required_roles` | 否 | 服务级粗粒度授权；**空数组 = 放行任意已认证身份** |
| `rate_limit` | 否 | `{average, burst}`，按调用方分桶 |
| `doc_url` | 否 | 该服务自身的接口文档地址，会出现在 `/openapi/v1/_docs` |
| `gateway_versions` | 否 | 挂载的网关契约版本，缺省挂载全部活跃版本 |
| `enabled` | 否 | 默认 `true`；置 `false` 即下线（一个拉取周期内生效） |

### 步骤 3：注册

```bash
cd /opt/bk-lite/deploy/docker-compose-ha
set -a; source common.env; set +a
export NATS_URL=tls://<本机IP>:4222
export NATS_CA_FILE=$PWD/conf/certs/ca.crt

wxc openapi validate -n itsm -f itsm.json      # 写前预检（结构与枚举）
wxc openapi register -n itsm -f itsm.json --probe itsm-svc:8000
wxc openapi list                                # 确认已写入
```

`--probe` 会从本机探测该服务的直连端口：**可达即告警**——注册进网关的服务必须同步封锁直连入口。

封锁直连的做法按部署形态选其一（网关经 compose 内网访问上游，不受影响）：

- **同栈 compose 服务**：移除该服务的宿主端口映射（`ports:`），只保留 `expose`，容器间仍可互通；
- **独立主机上的服务**：用防火墙 / 安全组只放行 Traefik 所在主机的来源 IP；
- 改完用 `wxc openapi register ... --probe <host:port>` 复测，输出应为 `✓ 直连探测：目标端口不可直达`。

> **`validate` 与 `list` 都只做本地结构校验**：`list` 的 `CHECKS` 列显示 `ok` 仅表示条目 JSON 结构合法，**不代表该条目已生效**——`base_url` 是否在允许清单内、`env:` 引用能否解析，由 server 渲染器判定。**唯一权威依据是第 6 节的两条命令**（provider 渲染输出中是否出现该 router、Traefik 是否已加载），不要凭 `list` 的 `ok` 判断接入成功。

> **HA 栈必读**：注册条目写入的是**当前所连节点**的 NATS JetStream，主备各自独立 domain；`openapi_registry` 未纳入复制清单（`HA_MIRROR_STREAMS`），**不随主备切换保留**。因此：
> - 注册 / 变更 / 下线都必须**在主备两端各执行一次**（`NATS_URL` 分别指向本机）；
> - 只在一端操作时，主备切换后新主注册表为空 → 全部外部服务路由静默消失（表现为 404，无告警）；只在一端下线则切换后旧路由会复活；
> - 根治方案（KV 专用复制流或改持久化存储）尚在评估，当前以两端各注册为准。

### 步骤 4：验证生效

```bash
TOKEN=<API 令牌>       # 在「系统管理 → API 密钥」页自助生成
BASE=https://<平台地址>:<端口>

# 目录里应出现该服务，kind=external
# 注意：刚注册后最迟约一个 TTL（默认 10 秒，可用 OPENAPI_REGISTRY_CACHE_TTL 调整，
# 0 为每次读同步回源）后的下一次请求出现；服务实际可调还取决于 Traefik 拉取路由，
# 以下面的实际调用连通为准
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/openapi/v1/_docs | jq '.data.services'

# 无凭据必须被网关挡回 401
curl -sk -o /dev/null -w '%{http_code}\n' $BASE/openapi/v1/itsm/tickets/list

# 带凭据应穿透到上游
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/openapi/v1/itsm/tickets/list
```

路由在**一个拉取周期（5 秒）**内生效。若未生效，见第 6 节排查。

---

## 3. 两种身份传递模式

> **先按上游是否自带鉴权选模式**：上游若有自己的 Bearer / API Key 认证（多数第三方
> API、LLM 服务属此类），必须用 `service-token`——网关会用 `token_ref` 的值覆盖
> `Authorization` 头。上游若能读 `X-BK-*` 身份头（与平台同用户体系），才用
> `trusted-header`。
>
> **错用 `trusted-header` 的症状**：该模式会把转发给上游的 `Authorization` **清空**，
> 因此自带鉴权的上游收到的是"无凭据"请求，通常返回 401 / "missing credentials"
> 一类错误（而非"令牌无效"）。看到上游报缺少认证信息，先检查模式是否选错。

### 信任头模式 `trusted-header`（推荐）

网关认证后向上游注入身份头，上游据此识别用户：

```http
POST /tickets/create HTTP/1.1
X-BK-Gateway-Auth: <shared_secret_ref 解引用后的共享密钥>
X-BK-User: zhangsan@domain.com
X-BK-Team: 2
```

- `X-BK-User`：`用户名@域`，ASCII 稳定标识；
- `X-BK-Team`：逗号分隔的组织 id。API 令牌为其绑定组织（单值）；登录态 JWT 为用户全部直属组织；
- `X-BK-Gateway-Auth`：网关与该服务之间的共享密钥，**上游的唯一信任根**。

网关同时会**清空转发给上游的 `Authorization` 头**：上游按身份头识别用户即可，不应看到
调用方的平台凭据（否则上游可凭其冒充调用方回调平台）。

适用：上游与平台用户体系已打通。

### 服务账号模式 `service-token`

网关注入上游自己颁发的服务令牌（`Authorization: Bearer <token_ref 解引用>`），上游按自身体系认证该服务账号；`X-BK-User` 仅作审计参考。

适用：用户体系未打通、或上游改不动。代价是上游侧无法做用户级授权。

**上游侧要做什么**：通常**什么都不用改**——上游照常用自己的鉴权校验那个服务令牌即可，
这正是该模式的价值。注意两点：

- **不要照搬第 4 节的中间件示例**：那是信任头模式的写法，该模式下上游不会收到
  `X-BK-Gateway-Auth`，照搬会导致自我拒绝（所有请求 401）；
- 若上游想记录真实调用人，可读 `X-BK-User` 头**仅用于审计**，不得用于鉴权判定
  （该头在此模式下不构成信任凭据）。

---

## 4. 上游服务侧如何处理身份（信任头模式）

```python
def gateway_identity_middleware(request):
    # 1. 共享密钥校验 —— 唯一信任根，常数时间比较；缺失或不符一律拒绝
    if not hmac.compare_digest(
        request.headers.get("X-BK-Gateway-Auth", ""), GW_SHARED_SECRET
    ):
        return reject_401()

    # 2. 解析身份
    user_id = request.headers["X-BK-User"]          # user@domain
    teams = [int(t) for t in request.headers.get("X-BK-Team", "").split(",") if t]

    # 3. 映射本地用户（同体系直查 / 首次自动建影子账号 / 拒绝，按集成策略定）
    local_user = resolve_or_provision(user_id)

    # 4. 以 teams 为本次请求的数据域边界，接入自身权限模型
    request.ctx = Context(user=local_user, teams=teams)

    # 5. 审计：X-On-Behalf-Of 仅记录并标注「自报、未经验证」，不参与鉴权
    audit_log(actor=user_id,
              on_behalf_of=request.headers.get("X-On-Behalf-Of"),
              on_behalf_verified=False)
```

**三条禁令**

1. 不得信任任何未通过 `X-BK-Gateway-Auth` 校验的 `X-BK-*` 头；
2. 不得把 `X-BK-*` 头继续透传给更下游系统（防止信任链被隐式延长）；
3. 不得以来源 IP 白名单代替密钥校验（网络拓扑一变即失效）。

---

## 5. 调用方须知

| 项 | 约定 |
| --- | --- |
| 入口 | `https://<平台地址>/openapi/v1/<服务名>/<上游路径>` |
| 凭据 | `Authorization: Bearer <API 令牌 或 登录态 JWT>`，**不接受 Cookie** |
| 令牌获取 | 「系统管理 → API 密钥」自助生成，绑定「用户 × 组织」，仅展示一次 |
| 内省 | `GET /openapi/v1/_me` 返回自身身份、授权组织、可用服务清单 |
| 目录 | `GET /openapi/v1/_docs` 返回接口目录（内部端点含 schema，外部服务给 `doc_url`） |

**响应格式**：内部应用统一为 `{"result": true, "data": ...}` / `{"result": false, "code": "...", "message": "..."}`；
**外部服务为透传**——上游返回什么，调用方拿到什么，网关只保证认证层面的统一。

错误码分两类来源，**响应体格式不同，客户端解析必须容错**：

| 状态码 | code | 含义 | 响应体 |
| --- | --- | --- | --- |
| 401 | `AUTH_INVALID` | 凭据无效或缺失 | JSON 包络 |
| 403 | `ROLE_REQUIRED` | 未满足该服务的 `required_roles` | JSON 包络 |
| 403 | `PERM_MISSING` / `TEAM_OUT_OF_SCOPE` | 内部接口权限位不足 / 组织越界 | JSON 包络 |
| 404 | `NOT_FOUND` | 服务未注册 / 路径不在 `paths` 白名单 / 端点不存在 | JSON 包络 |
| 400 | `SCHEMA_INVALID` | 参数不合法或含未声明字段（仅内部接口） | JSON 包络 |
| 500 | `INTERNAL_ERROR` | 内部接口未捕获异常 | JSON 包络 |
| 429 | — | 触发限流 | **Traefik 原生响应，非 JSON 包络；当前不带 `Retry-After`** |
| 502 | — | 上游不可达 | **Traefik 原生响应，非 JSON 包络** |

> 429/502 由 Traefik 直接产生，**不经过 server**，因此没有 `code` 字段。客户端不要假设所有
> 错误响应都能 `json.loads` 出 `code`——先判状态码，JSON 解析失败按状态码兜底处理。
> 另外**上游自身返回的 5xx 会原样透传**，与网关产生的 502 无法从状态码区分，需结合响应体判断。

**`GET /openapi/v1/_me` 响应结构**（对外冻结，仅新增字段）：

```json
{
  "result": true,
  "data": {
    "user": "zhangsan",
    "domain": "domain.com",
    "credential_type": "api_token",
    "groups": [{ "id": 2, "name": "华南" }],
    "anchor_scopes": [{ "anchor": 2, "cascaded_group_ids": [2, 4, 5] }],
    "roles": ["opspilot--admin"],
    "services": [
      { "name": "cmdb", "kind": "internal" },
      { "name": "itsm", "kind": "external" }
    ]
  }
}
```

- `groups`：直属组织；`anchor_scopes`：以各直属组织为锚点时级联可见的组织集合（锚点式接口用）；
- `services` 中的 **external 条目来自 server 各 worker 进程内的快照**，刚注册后可能缺失或在多次请求间不稳定；**不要用它判断某外部服务是否可用**，以实际调用为准。

### 5.1 凭据安全须知（务必转达客户安全评审）

1. **API 令牌永不过期、无 scope**：平台不提供过期与自动轮转，只能删除重建；建议按客户安全策略定期（如季度）手工轮转。401 不会因"令牌过期"产生——出现 401 只可能是令牌被删除、格式错误或未用 `Authorization: Bearer`。
2. **必须使用专属最小权限账号**：为每个集成方单独创建仅挂载所需权限的角色与账号，用它生成令牌。**禁止复用员工个人账号，尤其禁止用超管账号**——令牌继承生成者的全部权限位与超管标志。
3. **超管令牌会绕过服务级闸门**：注册条目的 `required_roles` 与内部端点的 `permission` 对超管身份直接放行，因此这两道闸门不能用于限制超管令牌。
4. **令牌泄漏的止损**：删除该令牌（系统管理 → API 密钥）即时失效（存在秒级缓存延迟）；审计日志可按 user / path 追溯调用记录。

---

## 6. 排查

**症状：注册成功但调用返回 404**

按顺序查（大部分问题在前两条）：

```bash
# 1. 条目是否被渲染器丢弃？——最常见原因：base_url 不在允许清单、env 引用解析不了
docker exec <server容器> sh -c \
  'curl -s -H "X-Provider-Token: $OPENAPI_PROVIDER_TOKEN" \
   http://127.0.0.1:8000/openapi/v1/_provider/traefik' | jq '.http.routers'

# 2. Traefik 是否消费到动态路由？
docker exec <traefik容器> wget -qO- http://127.0.0.1:8080/api/http/routers \
  | jq '[.[] | select(.provider=="http") | {name, status}]'

# 3. Traefik 拉取是否报错
docker logs --since 5m <traefik容器> 2>&1 | grep -i "provider error"
```

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 步骤 1 中 `routers` 为空 | 条目被跳过 | 查 server 日志中 `openapi_registry 条目 X 被跳过：<原因>` |
| 跳过原因 `base_url not in allowlist` | 允许清单未含该主机 | 补 `OPENAPI_BASEURL_ALLOWLIST` 并重建 server |
| 跳过原因 `shared_secret_ref unresolvable` | server 容器内没有该 env | 见步骤 1 的透传配置 |
| 步骤 2 中查不到 router | Traefik 未拉到配置 | 查步骤 3 的错误；注意 server 重启期间的 `connection refused` 属正常瞬时现象 |
| `provider error` 报连接被拒 | server 未就绪 | 等待 server 启动完成，Traefik 会自动重试 |
| **此前正常的外部服务突然全部 404** | 发生过 HA 主备切换，新主注册表为空 | 在新主执行 `wxc openapi list` 核对，缺失则重新 register（见步骤 3 的 HA 注意事项） |
| **全部外部服务同时 404 / 503，内部接口也异常** | server 不可用（重启、崩溃、发版） | 见下方「可用性耦合」；等待 server 恢复，Traefik 会自动重试 |
| 上游报"缺少认证信息 / 401" | 模式选错：自带鉴权的上游用了 `trusted-header`（该模式清空 Authorization） | 改用 `service-token`，见第 3 节 |
| `list` 显示 `ok` 但调用 404 | `CHECKS` 只是本地结构校验，不代表生效 | 用本节前两条命令确认渲染与路由 |

**可用性耦合（务必知悉）**：外部服务的业务流量虽不经过 server，但**每个请求的
ForwardAuth 认证都要回调 server**，且 Traefik 的动态路由也从 server 拉取。因此
**server 不可用时，全部外部服务的网关调用同时不可用**——"数据面不经过 server"不等于
可用性解耦。server 重启期间 Traefik 保留最后一次成功拉取的配置，恢复后自动重试；若需
在 server 长时间不可用时保障某外部服务，只能临时改 Traefik 静态配置绕过网关（应急手段，
会同时绕过认证与审计，须评估后使用）。

**症状：调用返回 401 但凭据正确** —— 确认用的是 `Authorization: Bearer`（不接受 Cookie）；确认令牌未被删除；令牌吊销存在缓存延迟。

**症状：上游收不到 `X-BK-*` 头** —— 确认注册条目是 `trusted-header` 模式；确认上游读的是网关注入的头而非自建认证。

---

## 7. 下线与变更

**下线**（顺序很重要：先确认路由已消失，再解除网络封锁）：

```bash
# 1) 把条目改为 enabled:false 后重新注册（HA 栈两端各做一次）
jq '.enabled = false' itsm.json > itsm-off.json
wxc openapi register -n itsm -f itsm-off.json

# 2) 等一个拉取周期后确认路由已消失（这才是权威确认，不是看 list）
sleep 8
docker exec "$(docker compose ps -q traefik)" wget -qO- http://127.0.0.1:8080/api/http/routers \
  | jq '[.[] | select(.provider=="http") | .name]'

# 3) 确认消失后，再解除该服务的网络封锁（如需）
```

**彻底删除误注册的条目**：`enabled:false` 只是停用，条目仍在注册表里。删除需直接操作 KV
（`wxc openapi` 目前不提供 delete 子命令）：

```bash
docker exec "$(docker compose ps -q nats)" nats kv del openapi_registry <服务名> --force \
  -s tls://127.0.0.1:4222 --tlsca /etc/nats/certs/ca.crt \
  --user "$NATS_ADMIN_USERNAME" --password "$NATS_ADMIN_PASSWORD"
```

**变更** `base_url` / `paths` / 限流 / 密钥引用：改条目重新 `register` 即可，一个拉取周期内生效，无需发版或重启（HA 栈仍需两端各做一次）。

**共享密钥 / 服务令牌轮转**（`shared_secret_ref`、`token_ref` 指向的 env 值）：轮转**不是**改 KV 条目就能完成的，它需要重建 server 并与上游协同，属于有停顿窗口的操作：

1. 与上游约定**双密钥并存窗口**（上游同时接受新旧两个密钥），无此能力则须安排停机窗口；
2. 改 `.env` 中该变量的值；
3. 重建 server（步骤 1 的重渲染流程，约 1 分钟不可用）；
4. 确认新密钥生效后，上游再停止接受旧密钥。

若上游无法并存双密钥，第 2–3 步之间该服务的调用会因密钥不匹配而失败，需安排窗口。

---

---

# 第二部分 · 内部接口接入

## 8. 内部接口接入规范

把 BK-Lite 某个应用的已有函数暴露为对外 API。与外部服务不同，内部接口的暴露是
**代码级声明**：随版本发布，受编译期（启动期）校验与 CI 门禁约束。

### 8.1 基本原则

1. **默认全关，显式 opt-in**：未声明 `@openapi_expose` 的函数一律不可经网关调用（返回 404）。不存在"批量暴露"开关。
2. **fail-closed**：契约声明不完整时**在 server 启动阶段直接报错**（`ImproperlyConfigured`），不会带病上线。
3. **schema 即契约**：对外暴露的字段名与类型一经发布即冻结，内部重构不得波及。
4. **暴露 ≠ 免鉴权**：网关只解决"谁在调用"，数据可见范围仍由函数自身的组织过滤逻辑负责——这是暴露方的责任，见 8.5。

### 8.2 四步接入

**① 写暴露专用 serializer**（`apps/<app>/openapi_serializers.py`）

```python
from rest_framework import serializers
from apps.core.openapi.serializers import PaginatedRequestSerializer

class ModuleDataQuerySerializer(PaginatedRequestSerializer):
    module = serializers.ChoiceField(choices=["patch_target"])
    group_id = serializers.IntegerField(min_value=1)
```

- **禁止复用内部业务 serializer**：内部迭代改字段会静默破坏对外契约；
- 禁止 `fields = "__all__"`：新增字段会意外外泄；
- 基类已内建：未知字段拒绝（客户端身份字段无从混入）、分页钳制（`page` 1-based、`page_size` 默认 20 / 上限 500、越限钳制而非报错）。

**选哪个基类**：分页查询继承 `PaginatedRequestSerializer`；**非分页查询与写接口继承
`OpenAPIRequestSerializer`**（同样拒绝未知字段，但不带 page/page_size）。写接口的字段
放在 JSON body，`method` 声明为 `POST`/`PUT`/`DELETE`。

**schema 字段名必须与函数形参名对齐**（或用 `param_map` 显式映射）：注册时**不校验**二者
是否匹配，错配会在真实调用时抛 `TypeError` 并被兜底成 `500 INTERNAL_ERROR`，报错信息
不指向根因。首次暴露后务必真实调用一次。

**多分支函数只暴露安全分支**：若函数按 `module`/`type` 参数走多个分支、而只有部分分支做了
组织过滤（cmdb 的 `get_cmdb_module_data` 即如此），**用 serializer 的 `ChoiceField` 把
`choices` 收窄到已做过滤的分支**，其余分支自然被 400 拒绝。这是当前唯一能安全暴露此类函数的做法。

**② 叠加装饰器**（与 `@nats_client.register` 共存，不影响原有 NATS 调用）

```python
@nats_client.register
@openapi_expose(
    path="patch-mgmt/module-data",     # service/sub-path，发布后永久固定
    method="GET",                       # GET 走 query string；写方法走 JSON body
    schema=ModuleDataQuerySerializer,   # 必填
    inject="team_list",                 # 或 "user_info"，见 8.3
    permission="patch_target-View",     # 可选；须与 permission_app 配对，取值来源见 8.2 表下说明
    permission_app="patch",
    summary="…（须写明组织口径：是否级联子组织）",
)
def get_patch_mgmt_module_data(module, child_module, page, page_size, group_id, *, team=None):
    ...
```

其余可选参数：`param_map`（schema 字段 → 函数形参的显式映射，用于内部重命名形参而不动契约）、`team_free`（见 8.4）。

**`path` 的 service 段命名规则同样适用于内部接口**：`^[a-z][a-z0-9-]{0,31}$`，**不能带下划线**。
应用目录名多含下划线，暴露时须转写为连字符（`patch_mgmt` → `patch-mgmt`、`node_mgmt` → `node-mgmt`），
写错会在启动时报错。

**`permission` / `permission_app` 取值来源**（写错会让非超管用户全量 403）：

- `permission_app` **不是应用目录名**，而是该应用菜单定义里的 `client_id`
  （见 `server/support-files/system_mgmt/menus/<app>.json`）。多数不一致：
  `patch_mgmt` → `patch`、`alerts` → `alarm`、`system_mgmt` → `system-manager`、
  `node_mgmt` → `node`、`job_mgmt` → `job`、`console_mgmt` → `ops-console`、
  `operation_analysis` → `ops-analysis`；cmdb / monitor / log 等则与目录名相同；
- `permission` 取该 json 内的 `<菜单id>-<操作>`，与视图上 `@HasPermission(...)` 用的是同一套值
  （如 `patch_target-View`）；
- 声明 `permission` 却漏 `permission_app` 会在注册时报错（已加 fail-closed 校验），
  但**取值填错不会报错**——超管账号测试也发现不了（超管直通），只有非超管调用才会暴露为
  全量 `403 PERM_MISSING`。**务必用非超管账号实测一次**。

**③ 写双租户测试并登记**（合并的硬性门禁）

用 `apps/core/openapi/testing.py` 的基建构造两个组织身份，断言读隔离与写归属，然后登记到 `apps/core/openapi/tests/tenant_coverage.py`：

```python
TENANT_ISOLATION_COVERAGE = {
    "patch-mgmt/module-data": [
        "apps.core.openapi.tests.test_gateway::test_tenant_cannot_read_other_org",
    ],
}
```

未登记或引用失效时 `test_governance.py` 失败，**CI 拒绝合并**。

当前测试基建的两点限制，写测试前先知悉：

- `testing.py` 只提供 **API 令牌**身份的构造 helper，没有 JWT 身份 helper。锚点式
  （`user_info`）端点在 JWT 凭据下的行为（锚点由客户端指定、可级联子组织）**无法用现成
  helper 覆盖**，需自行构造 `system_mgmt.User` 并签发 JWT（参考 `test_gateway.py` 的
  `make_jwt_tenant`）；
- API 令牌路径下锚点被强制覆盖为绑定组织，因此只用令牌身份测不出"锚点选错"类问题。

**④ 过命名与契约评审**（见 8.6 checklist）

### 8.3 两种身份注入协议

按被暴露函数**已有的**组织参数形态选择，无需改造函数：

| `inject` | 函数期待 | 网关注入 | 语义 |
| --- | --- | --- | --- |
| `team_list` | `*, team=None` | API 令牌 → `[绑定组织]`；JWT → 用户全部直属组织 | 函数按注入集合做精确成员校验（**不级联**子组织） |
| `user_info` | `user_info=None`，实际收到 `{user, domain, team, include_children}` | 注入认证身份，**并把 serializer 中字面名为 `team` / `include_children` 的字段抽取合并进同一个 user_info dict** | 函数自查 `group_list` 并**级联展开**子组织 |

锚点式有两条容易踩的硬约束：

- **serializer 必须声明字面名为 `team` 的锚点字段**（`include_children` 可选）。命名成
  `group_id` 等其它名字，网关不会把它当锚点——JWT 调用方会永久收到
  `400 team (organization anchor) is required` 且无法补传。**该约束在注册时即校验**，
  声明错误会让 server 启动报错，不会带到线上；
- 被抽取的 `team` / `include_children` **不会**再作为独立参数传给函数，它们只出现在
  `user_info` 里——函数不要另外声明同名形参去接。

两点必须写进 `summary` 并对调用方讲清：

- **可见范围口径不同**：同一用户经两类接口能看到的组织范围可能不同（历史实现差异，非有意的权限模型）；
- **锚点式的锚点必须是调用者的直属组织**：传入真实存在但非直属的子组织 id 会**静默返回空结果**而非报错。

API 令牌为单组织收窄凭据：锚点式下网关**强制覆盖**客户端传入的锚点为令牌绑定组织。

### 8.4 `team_free` 的适用与约束

仅用于**不含任何组织维度数据**的公共元信息接口（如枚举字典、版本信息）。声明后网关不注入任何组织上下文，因此：

- 必须附带"响应不含组织相关字段"的断言测试；
- 须经安全评审签字（注：仓库的 `.github/CODEOWNERS` 目前是**注释状态、尚未启用**，
  该评审当前靠人工流程保障，没有工具强制）；
- 审计日志对此类调用打标。

`team_free=True` 与 `inject` 互斥（同时声明会启动报错）。

### 8.5 暴露方的数据域责任（最容易出事的一条）

网关能保证"注入的身份不可伪造"，**不能保证"函数用了这个身份"**。一个签名完全合规、却在函数体里 `Model.objects.all()` 的函数，会安静地跨租户泄漏数据——请求返回 200，无任何报错。

因此：

- 每条查询必须经过组织过滤（`build_json_membership_query` 等既有 helper），写操作必须校验目标对象归属；
- 越权应返回明确拒绝（网关会将组织越权类软错误映射为 `403 TEAM_OUT_OF_SCOPE`）；
- **双租户测试是唯一能验证"注入被真正使用"的手段**，故列为准入门槛而非建议。

### 8.6 评审 checklist

`@openapi_expose` 与暴露 serializer 的任何变更须经 API 设计责任人评审：

- [ ] schema 字段命名与全平台一致（组织概念统一字段名，不把内部 NATS 字段名直接透传为对外契约）；
- [ ] 每条查询经过组织过滤，写操作校验目标归属；
- [ ] 已发布字段未被改名 / 收紧 / 删除——**破坏性变更必须以新 path（或新版本段）发布**；请求 schema 只能新增可选字段，响应只能新增字段；
- [ ] 函数短耗时、强制分页；长任务已拆为「提交 + 查询」两个接口；
- [ ] 双租户测试已登记；`team_free` 有豁免理由与断言测试；
- [ ] `summary` 写明组织口径。

### 8.7 发布后不可变的契约面

以下一经发布即冻结（详见设计文档第 8 章冻结清单）：`path` 字符串、serializer 字段名与类型、响应结构、`inject` 形状与组织口径、错误码语义。内部实现（函数名、形参名、内部 serializer、调用链）可自由重构——前提是经 `param_map` 与暴露专用 serializer 与契约解耦。

### 8.8 自检与排查

```bash
# 已暴露的内部端点清单（含 schema 内省）
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/openapi/v1/_docs | jq '.data.services[] | select(.kind=="internal")'
```

| 现象 | 原因 |
| --- | --- |
| server 启动即报 `ImproperlyConfigured` | 装饰器声明不完整：缺 schema / 缺 inject / 身份参数缺失 / path 非法 / 重复注册。错误信息直指函数名与缺失项 |
| 调用返回 404 | 该函数未声明 `@openapi_expose`，或 path / method 不匹配 |
| 返回 400 `SCHEMA_INVALID` | 请求含 schema 未声明的字段（含试图传 `team`、`user_info` 等身份字段——设计如此） |
| 返回 403 `PERM_MISSING` | 未满足 `permission`；**先核对 `permission_app` 是否为菜单 `client_id`**（填错即全量 403，超管测不出，见 8.2） |
| 返回 403 `TEAM_OUT_OF_SCOPE` | 业务组织参数越出注入的授权集合 |
| 返回 500 `INTERNAL_ERROR`，日志有 `TypeError` | schema 字段名与函数形参不匹配（注册时不校验），见 8.2 |
| JWT 调用恒 400 `team is required`，API 令牌却正常 | 锚点式 serializer 未声明 `team` 字段（新版本已在注册时拦截） |
| GET 请求把参数放在 body / POST 放在 query | **参数被静默忽略**（不报错），表现为"参数没生效"；GET 走 query、写方法走 JSON body |
| 慢接口长时间不返回 | 网关强制超时当前**未启用**（已知遗留），函数需自行控制耗时 |
| CI 报未登记双租户测试 | 补测试并登记到 `tenant_coverage.py` |

---

## 附：完整接入示例（内网 LLM API，已实测通过）

把内网 LLM 服务 `http://10.10.24.11:3000` 接入为 `llmapi`。该上游**自带 Bearer 鉴权**，
因此用 `service-token` 模式注入它自己的 key：

```bash
cd /opt/bk-lite/deploy/docker-compose-ha

# 1. 允许清单 + 上游自己的 API key
echo 'OPENAPI_BASEURL_ALLOWLIST=10.10.24.11' >> .env
echo 'LLMAPI_UPSTREAM_TOKEN=<上游的 API key>' >> .env
# compose/server.yaml 的 server 服务 environment 补一行：
#   - LLMAPI_UPSTREAM_TOKEN=${LLMAPI_UPSTREAM_TOKEN:-}

set -a; source common.env; source ha.env; source .env; set +a
docker compose -f compose/infra.yaml -f compose/postgres.yaml -f compose/monitor.yaml \
  -f compose/server.yaml -f compose/web.yaml -f compose/log.yaml -f compose/ha.yaml \
  config --no-interpolate > docker-compose.yaml
docker compose up -d server
for i in $(seq 1 24); do
  docker logs --tail 3 bk-primary-server-1 2>&1 | grep -q 'Application startup complete' && break
  sleep 10
done

# 2. 注册条目
cat > llmapi.json <<'EOF'
{
  "schema_version": 1,
  "type": "http",
  "base_url": "http://10.10.24.11:3000",
  "strip_prefix": true,
  "auth_mode": "service-token",
  "token_ref": "env:LLMAPI_UPSTREAM_TOKEN",
  "required_roles": [],
  "enabled": true
}
EOF

export NATS_URL=tls://10.10.41.149:4222 NATS_CA_FILE=$PWD/conf/certs/ca.crt
wxc openapi validate -n llmapi -f llmapi.json
wxc openapi register -n llmapi -f llmapi.json --probe 10.10.24.11:3000
wxc openapi list

# 3. 验证（TRAEFIK_WEB_PORT 见 .env）
BASE=https://10.10.41.149:${TRAEFIK_WEB_PORT}
curl -sk -o /dev/null -w '%{http_code}\n' $BASE/openapi/v1/llmapi/v1/models   # 期望 401
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/openapi/v1/llmapi/v1/models  # 期望模型列表
```

调用方此后即可用**平台令牌**访问该 LLM 服务，无需持有上游 key——上游 key 只存在于
server 的环境变量中，由网关注入。
